#!/usr/bin/env python3
"""
TowerWitch - GPS-Enhanced Tower Locator (Tkinter Version)
A comprehensive amateur radio repeater and emergency services tower locator
with GPS integration, multiple band support, and enhanced visual interface.

This tkinter version provides better control over styling and colored tabs.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import configparser
import os
import sys
import json
import csv
# The single-instance lock, on whichever platform this is. fcntl is POSIX
# and does not exist on Windows, and importing it unconditionally is what
# stopped the Tk build running on a laptop at all - it died on line 17,
# before a window could appear, which reads as "TowerWitch is broken"
# rather than "this module is for the Pi". Windows has its own byte-range
# lock in msvcrt, so the protection is kept rather than dropped: see
# acquire_single_instance_lock().
try:
    import fcntl
    msvcrt = None
except ImportError:                 # Windows
    fcntl = None
    import msvcrt
import tempfile
from datetime import datetime
from math import radians, cos, sin, asin, sqrt, atan2, degrees, tan
import threading
import time
import subprocess
from urllib import request, parse
from urllib.error import URLError
import xml.etree.ElementTree as ET

# Try to import GPS libraries
try:
    import gpsd
    GPS_AVAILABLE = True
except ImportError:
    GPS_AVAILABLE = False
    print("WARNING: GPS libraries not available - GPS functionality disabled")

# For direct gpsd JSON socket access (fallback)
import socket
import json

UDP_CONFIG = {
    'port': 12345,
    'armer_tower_count': 2   # closest ARMER sites carried in each broadcast
}


class RadioReferenceAPI:
    """Radio Reference API client for fetching repeater data"""
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.cache_dir = os.path.join(os.path.expanduser("~"), ".towerwitch_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.base_url = "https://api.radioreference.com/soap2"

    def get_repeaters_near_location(self, lat, lon, radius=50, mode='FM'):
        """Get repeaters near a location using Radio Reference API
        
        Args:
            lat, lon: GPS coordinates
            radius: Search radius in miles
            mode: Repeater mode (FM, DMR, DSTAR, etc.)
        Returns:
            List of repeater dictionaries
        """
        if not self.api_key or self.api_key == 'your_api_key_here':
            print("[INFO] No valid Radio Reference API key - using static data")
            return []
        
        try:
            # Radio Reference uses SOAP API - construct the request
            soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" 
               xmlns:ns="http://api.radioreference.com/soap2">
  <soap:Body>
    <ns:searchProxFreq>
      <appKey>{self.api_key}</appKey>
      <lat>{lat}</lat>
      <lon>{lon}</lon>
      <range>{radius}</range>
      <mode>{mode}</mode>
    </ns:searchProxFreq>
  </soap:Body>
</soap:Envelope>"""
            
            headers = {
                'Content-Type': 'text/xml; charset=utf-8',
                'SOAPAction': 'http://api.radioreference.com/soap2/searchProxFreq'
            }
            
            req = request.Request(self.base_url, data=soap_body.encode('utf-8'), headers=headers)
            
            with request.urlopen(req, timeout=10) as response:
                xml_data = response.read().decode('utf-8')
                
                # Debug: Save raw response to check for issues
                if os.getenv('DEBUG_API'):
                    debug_file = os.path.join(self.cache_dir, 'last_api_response.xml')
                    with open(debug_file, 'w') as f:
                        f.write(xml_data)
                    print(f"[DEBUG] Saved API response to {debug_file}")
                
                # Parse XML response
                repeaters = self._parse_repeater_response(xml_data)
                
                if not repeaters:
                    print(f"[INFO] Radio Reference returned no repeaters for location {lat:.4f}, {lon:.4f}")
                else:
                    print(f"[OK] Fetched {len(repeaters)} repeaters from Radio Reference")
                
                # Cache the results
                cache_key = f"{lat:.4f}_{lon:.4f}_{radius}"
                self.save_to_cache('repeaters', cache_key, repeaters)
                
                return repeaters
                
        except Exception as e:
            print(f"[WARN] Radio Reference API error: {e}")
            # Try to load from cache as fallback
            cache_key = f"{lat:.4f}_{lon:.4f}_{radius}"
            cached = self.load_from_cache('repeaters', cache_key)
            if cached:
                print("[INFO] Using cached repeater data")
                return cached
            return []

    def _parse_repeater_response(self, xml_data):
        """Parse XML response from Radio Reference API"""
        repeaters = []
        try:
            root = ET.fromstring(xml_data)
            
            # Check for SOAP fault/error first
            fault = root.find('.//{http://schemas.xmlsoap.org/soap/envelope/}Fault')
            if fault is not None:
                faultstring = fault.findtext('.//{http://schemas.xmlsoap.org/soap/envelope/}faultstring', 'Unknown error')
                print(f"[ERROR] Radio Reference API error: {faultstring}")
                return []
            
            # Parse the SOAP response (namespace handling)
            # Try multiple possible element names/namespaces
            freq_elements = (root.findall('.//{http://api.radioreference.com/soap2}Frequency') or
                           root.findall('.//Frequency') or
                           root.findall('.//{http://api.radioreference.com/soap2}freq'))
            
            if not freq_elements:
                # Check if response has any data at all
                if len(xml_data) < 500:  # Short response might be an error
                    print(f"[INFO] Radio Reference returned empty or short response (likely no data for this location)")
                else:
                    print(f"[WARN] Could not find Frequency elements in response")
                return []
            
            for freq in freq_elements:
                try:
                    repeater = {
                        'call': freq.findtext('callsign', freq.findtext('.//callsign', 'N0CALL')),
                        'location': freq.findtext('location', freq.findtext('.//location', 'Unknown')),
                        'output': freq.findtext('freq', freq.findtext('.//freq', '0.0')),
                        'input': freq.findtext('input', freq.findtext('.//input', '0.0')),
                        'tone': freq.findtext('tone', freq.findtext('.//tone', '')),
                        'lat': float(freq.findtext('lat', freq.findtext('.//lat', '0.0'))),
                        'lon': float(freq.findtext('lon', freq.findtext('.//lon', '0.0')))
                    }
                    repeaters.append(repeater)
                except (ValueError, TypeError) as e:
                    print(f"[WARN] Skipping malformed repeater entry: {e}")
                    continue
                    
        except ET.ParseError as e:
            print(f"[ERROR] XML Parse Error: {e}")
            print(f"[ERROR] First 500 chars of response: {xml_data[:500]}")
        except Exception as e:
            print(f"[ERROR] Error parsing Radio Reference response: {e}")
        return repeaters

    def get_skywarn_repeaters(self, lat, lon, radius=100):
        """Get Skywarn repeaters - filtered from general search"""
        print(f"[INFO] Searching for Skywarn/ARES repeaters within {radius} miles...")
        all_repeaters = self.get_repeaters_near_location(lat, lon, radius)
        
        if not all_repeaters:
            print("[INFO] No repeaters returned from API for Skywarn search")
            return []
        
        # Filter for SKYWARN or ARES keywords
        skywarn = []
        for r in all_repeaters:
            location = r.get('location', '').upper()
            call = r.get('call', '').upper()
            if ('SKYWARN' in location or 'ARES' in location or 
                'RACES' in location or 'EMERGENCY' in location or
                'SKYWARN' in call or 'ARES' in call):
                skywarn.append(r)
        
        print(f"[INFO] Found {len(skywarn)} Skywarn/ARES repeaters out of {len(all_repeaters)} total")
        return skywarn

    def get_amateur_repeaters(self, lat, lon, radius=50):
        """Get amateur repeaters (all FM/analog repeaters in area)"""
        print(f"[INFO] Searching for amateur repeaters within {radius} miles...")
        repeaters = self.get_repeaters_near_location(lat, lon, radius, mode='FM')
        print(f"[INFO] Found {len(repeaters)} amateur repeaters")
        return repeaters

    def save_to_cache(self, data_type, location_key, data):
        """Save data to cache"""
        cache_file = os.path.join(self.cache_dir, f"{data_type}_{location_key}.json")
        try:
            with open(cache_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"[WARN] Could not save cache: {e}")

    def load_from_cache(self, data_type, location_key):
        """Load cached data"""
        cache_file = os.path.join(self.cache_dir, f"{data_type}_{location_key}.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return None

class GPSWorker:
    """GPS worker with robust error handling and demo fallback"""
    def __init__(self, callback, send_demo_on_failure=True, status_callback=None):
        self.callback = callback
        # Hears how the wait for a fix is going while there is no position
        # to send: a dict with 'state' of 'waiting' (with mode and satellite
        # counts), 'silent' (receiver not reporting) or 'unreachable' (gpsd).
        self.status_callback = status_callback
        self.running = False
        self.thread = None
        self.gps_connected = False
        self.connection_attempts = 0
        self.max_attempts = 12  # 4 methods × 3 tries
        self.no_fix_warned = False
        self.use_json_fallback = False
        # When False, skip the Minneapolis demo callback if gpsd is unreachable
        # — caller already seeded the UI with a saved last-known position.
        self.send_demo_on_failure = send_demo_on_failure

    def start(self):
        """Start GPS monitoring. The JSON-socket path uses raw sockets and
        does not require the optional `gpsd` Python module — try it first."""
        self.running = True
        print("[INFO] Attempting to connect to gpsd via JSON socket...")
        self.use_json_fallback = True
        self.thread = threading.Thread(target=self._gps_loop_json, daemon=True)
        self.thread.start()

    def _ask_elmer(self):
        """A position from ELMER, when there is no gpsd on this machine.

        The receiver is on the Pi in the vehicle and the laptop on the desk
        has none, which used to mean the laptop showed a demo position in
        Minneapolis. ELMER is on that desk, it has the inputs for typing a
        QTH into, and it already ranks every source it knows of - its own
        receiver, a phone, another ELMER on the network - so it is asked
        rather than guessed at. See elmer_link.py, which has been able to
        do this for a while and was never called.

        A borrowed position is marked as borrowed. It is not this program's
        fix and is not broadcast as one: TowerWitch's UDP packet carries a
        position only when the position is its own, or the suite would hand
        ELMER's own answer back to it as though it were news.

        Returns a payload for the callback, or None. Never raises - a bench
        with no ELMER on it is the ordinary case, not a fault.
        """
        try:
            got = elmer_link.position(timeout=2.0)
        except Exception as exc:        # a borrowed link must not stop the loop
            print(f"[WARN] could not ask ELMER for a position: {exc}")
            return None
        if not got:
            return None
        common = {'time': datetime.now().isoformat(), 'satellites_used': 0,
                  'source': 'elmer', 'demo': False}
        if got.get("located") and got.get("lat") is not None:
            where = got.get("from") or "ELMER on this machine"
            print(f"[OK] position from ELMER: {got['lat']:.4f}, {got['lon']:.4f} ({where})")
            return dict(common, lat=float(got["lat"]), lon=float(got["lon"]),
                        alt=got.get("alt"), mode=int(got.get("mode") or 2),
                        elmer_words=where)
        qth = got.get("qth") or {}
        if qth.get("lat") is not None:
            # The typed QTH. Mode nought on purpose: it is a place somebody
            # named, not a fix, and nothing downstream should treat it as
            # one - it cannot drift, so it must not trigger a drift refresh.
            grid = qth.get("grid") or ""
            print(f"[OK] position from ELMER's QTH: {qth['lat']:.4f}, "
                  f"{qth['lon']:.4f}{' (' + grid + ')' if grid else ''}")
            return dict(common, lat=float(qth["lat"]), lon=float(qth["lon"]),
                        alt=qth.get("alt"), mode=0,
                        elmer_words=f"ELMER's QTH{' ' + grid if grid else ''}")
        return None

    def _send_demo_data(self):
        """Send demo GPS data - Minneapolis coordinates"""
        # Minneapolis elevation is ~260 meters (~853 feet MSL)
        self.callback({
            'lat': 44.9778,
            'lon': -93.2650,
            'alt': 260.0,  # meters
            'time': datetime.now().isoformat(),
            'mode': 0,  # 0 = Demo mode (not a real fix)
            'satellites_used': 0,
            'demo': True
        })

    # With no fix yet, say how the wait is going this soon after connecting
    # and then this often; a receiver that has not reported in this long is
    # called silent. A dropped gpsd connection is retried this often.
    FIRST_WAIT_REPORT_SECONDS = 10
    WAIT_REPORT_SECONDS = 30
    RECONNECT_SECONDS = 5
    GPSD_ADDRESS = ('localhost', 2947)

    # How often ELMER is asked for a position while there is no gpsd here.
    # Often enough that moving the QTH in ELMER moves TowerWitch within a
    # minute - which is how somebody tests another location from a desk -
    # and rarely enough that a machine with no ELMER on it is not knocking
    # on localhost every five seconds for nothing.
    ELMER_EVERY_SECONDS = 60

    def _gps_loop_json(self):
        """Direct JSON socket connection to gpsd - bypasses library caching.

        Stays up for the life of the program: if gpsd goes away (restarted by
        restart_gps.sh, say) or refuses the connection, wait and try again
        rather than leaving the display frozen on the last position until
        TowerWitch is relaunched."""
        print("[INFO] Using direct JSON socket to gpsd...")
        first_attempt = True
        asked_elmer_at = 0.0
        while self.running:
            connected = self._gps_session_json()
            if not connected:
                # ELMER first, and again every minute for as long as there is
                # no receiver here: the QTH typed into it is the answer for a
                # laptop on the desk, and following it means somebody can move
                # the station in ELMER and watch TowerWitch follow.
                now = time.time()
                borrowed = None
                if now - asked_elmer_at >= self.ELMER_EVERY_SECONDS:
                    asked_elmer_at = now
                    borrowed = self._ask_elmer()
                if borrowed:
                    self.callback(borrowed)
                elif first_attempt:
                    if self.send_demo_on_failure:
                        print("[WARN] No gpsd and no ELMER - falling back to DEMO mode")
                        self._send_demo_data()
                    else:
                        print("[INFO] Keeping last-known saved location on display")
            first_attempt = False
            if not self.running:
                break
            self._report_status({'state': 'unreachable'})
            print(f"[INFO] Reconnecting to gpsd in {self.RECONNECT_SECONDS}s...")
            self._sleep_unless_stopped(self.RECONNECT_SECONDS)

    def _gps_session_json(self):
        """One connection to gpsd, held until it drops or stop() is called.
        Returns whether the connection was ever made; the caller retries."""
        try:
            sock = socket.create_connection(self.GPSD_ADDRESS, timeout=5.0)
        except OSError as e:
            print(f"[ERROR] Could not establish JSON socket: {e}")
            return False
        sock.settimeout(2.0)
        print("[OK] Connected to gpsd via JSON socket")
        self.gps_connected = True

        buffer = b''
        mode = 0             # last TPV fix mode: 1 none, 2 = 2D, 3 = 3D
        sats_used = 0        # from SKY: in the solution / in view
        sats_seen = 0
        have_fix = False
        last_tpv = None      # when the receiver last reported at all
        connected_at = time.monotonic()
        next_report = connected_at + self.FIRST_WAIT_REPORT_SECONDS
        try:
            # Enable watch mode and request JSON
            sock.sendall(b'?WATCH={"enable":true,"json":true}\n')

            while self.running:
                try:
                    data = sock.recv(4096)
                    if not data:
                        print("[ERROR] GPS socket closed by gpsd")
                        return True
                    buffer += data
                except socket.timeout:
                    pass
                except OSError as e:
                    print(f"[ERROR] JSON socket error: {e}")
                    return True

                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode('utf-8'))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    cls = msg.get('class')

                    if cls == 'DEVICE':
                        # A receiver coming or going. gpsd keeps our socket
                        # open through an unplug, so this is the only sign.
                        state = 'activated' if msg.get('activated') else 'removed'
                        print(f"[INFO] gpsd device {state}: {msg.get('path', '?')} "
                              f"({msg.get('driver', 'unknown driver')})")
                    elif cls == 'DEVICES':
                        paths = [d.get('path', '?') for d in msg.get('devices', [])]
                        print(f"[INFO] gpsd devices: {', '.join(paths) or 'none'}")
                    elif cls == 'SKY':
                        satellites = msg.get('satellites', [])
                        sats_seen = len(satellites)
                        sats_used = sum(1 for s in satellites if s.get('used', False))
                    elif cls == 'TPV':
                        last_tpv = time.monotonic()
                        mode = msg.get('mode', 0)
                        lat = msg.get('lat')
                        lon = msg.get('lon')
                        # No fix: gpsd omits lat/lon, some receivers send 0,0
                        no_position = (lat is None or lon is None
                                       or (lat == 0.0 and lon == 0.0))
                        if no_position or mode < 2:
                            if have_fix:
                                have_fix = False
                                print(f"[WARN] GPS fix lost: mode={mode}, "
                                      f"satellites {sats_used}/{sats_seen}")
                                next_report = last_tpv  # report on this pass
                            continue
                        if not have_fix:
                            have_fix = True
                            print(f"[OK] GPS fix via JSON socket! Position: {lat:.6f}, {lon:.6f}")
                            print(f"[OK] Mode {mode}, altitude: {msg.get('alt', 0):.1f}m, "
                                  f"satellites: {sats_used}/{sats_seen}")
                        self.callback({
                            'lat': lat,
                            'lon': lon,
                            'alt': msg.get('alt', 0.0),
                            # m/s and degrees true, as gpsd reports them; the
                            # display converts. track is absent when the
                            # receiver has no heading (standing still) and
                            # the display shows ---° for None.
                            'speed': msg.get('speed', 0.0),
                            'track': msg.get('track'),
                            'time': msg.get('time', datetime.now().isoformat()),
                            'mode': mode,
                            'satellites_used': sats_used,
                            'demo': False
                        })

                # Still no fix: say how the wait is going, on the display and
                # in the log, so a cold start under no sky and a receiver that
                # is stuck or unplugged stop looking the same.
                now = time.monotonic()
                if not have_fix and now >= next_report:
                    next_report = now + self.WAIT_REPORT_SECONDS
                    silent = int(now - (last_tpv if last_tpv is not None else connected_at))
                    if silent >= self.FIRST_WAIT_REPORT_SECONDS:
                        print(f"[WARN] No report from the receiver in {silent}s "
                              "- unplugged, or gpsd has no device?")
                        self._report_status({'state': 'silent', 'silent_seconds': silent})
                    else:
                        print(f"[INFO] GPS waiting for fix: mode={mode}, "
                              f"satellites {sats_used}/{sats_seen}")
                        self._report_status({'state': 'waiting', 'mode': mode,
                                             'satellites_used': sats_used,
                                             'satellites_seen': sats_seen})
        finally:
            self.gps_connected = False
            sock.close()
        return True

    def _report_status(self, info):
        """Tell the display how the wait for a fix is going. Optional; the
        position callback is unaffected."""
        if self.status_callback:
            self.status_callback(info)

    def _sleep_unless_stopped(self, seconds):
        deadline = time.monotonic() + seconds
        while self.running and time.monotonic() < deadline:
            time.sleep(0.2)

    def _gps_loop(self):
        """GPS monitoring loop - reads actual GPS data from gpsd"""
        # Try to connect to gpsd with retries and multiple methods
        connection_methods = [
            ("Default", {}),
            ("Explicit localhost", {"host": "localhost"}),
            ("127.0.0.1", {"host": "127.0.0.1"}),
            ("localhost:2947", {"host": "localhost", "port": 2947}),
        ]
        
        while self.running and not self.gps_connected and self.connection_attempts < self.max_attempts:
            for method_name, kwargs in connection_methods:
                try:
                    self.connection_attempts += 1
                    print(f"[INFO] Connecting to gpsd using {method_name} (attempt {self.connection_attempts}/{self.max_attempts})...")
                    gpsd.connect(**kwargs)
                    time.sleep(0.5)  # Give connection time to establish
                    
                    # Flush initial stale data - read and discard several packets
                    for flush_attempt in range(5):
                        test_packet = gpsd.get_current()
                        if test_packet.lat != 0.0 or test_packet.lon != 0.0:
                            # Got real data
                            self.gps_connected = True
                            print(f"[OK] Connected to gpsd successfully using {method_name}!")
                            print(f"[INFO] GPS Mode: {test_packet.mode}, Lat: {test_packet.lat}, Lon: {test_packet.lon}, Sats: {getattr(test_packet, 'sats', 0)}")
                            break
                        elif flush_attempt < 4:
                            if flush_attempt == 0:
                                print(f"[INFO] Flushing stale GPS cache...")
                            time.sleep(0.5)
                    
                    if self.gps_connected:
                        break
                    else:
                        print(f"[WARN] Connected but still getting 0,0 coords using {method_name}, trying next method...")
                        # Disconnect and try next method
                        try:
                            gpsd.disconnect()
                        except:
                            pass
                        continue
                except Exception as e:
                    print(f"[ERROR] Could not connect using {method_name}: {e}")
                    if self.connection_attempts >= self.max_attempts:
                        print("[WARN] All library connection methods failed - trying direct JSON socket...")
                        self.use_json_fallback = True
                        self._gps_loop_json()
                        return
                    time.sleep(0.5)  # Wait before next method
            
            if self.gps_connected:
                break
        
        if not self.gps_connected:
            return
        
        # Main GPS reading loop - use streaming interface for fresh data
        print("[INFO] Starting GPS data stream...")
        
        # First, clear any stale data by reading multiple packets
        print("[INFO] Flushing stale GPS data...")
        for _ in range(3):
            try:
                gpsd.get_current()
                time.sleep(0.3)
            except:
                pass
        
        packet_count = 0
        while self.running:
            try:
                # Read next GPS packet - this forces fresh data
                # Call get_current() which will block briefly for new data
                packet = gpsd.get_current()
                packet_count += 1
                
                # Skip invalid 0,0 coordinates (stale cache from gpsd startup)
                if packet.lat == 0.0 and packet.lon == 0.0:
                    if packet_count < 10:  # Try 10 times to get fresh data
                        print(f"[INFO] Skipping stale 0,0 coordinates (attempt {packet_count}/10)...")
                        time.sleep(1)
                        continue
                    else:
                        print("[WARN] GPS appears stuck on 0,0 - gpsd may need restart")
                        print("       Run: sudo systemctl restart gpsd")
                        self._send_demo_data()
                        return
                
                # Build GPS data packet
                gps_data = {
                    'lat': packet.lat,
                    'lon': packet.lon,
                    'alt': packet.alt if hasattr(packet, 'alt') and packet.alt is not None else 0.0,
                    'time': packet.time if hasattr(packet, 'time') else datetime.now().isoformat(),
                    'mode': packet.mode,
                    'satellites_used': packet.sats if hasattr(packet, 'sats') else 0,
                    'demo': False
                }
                
                # Only update with valid 2D/3D fix
                if packet.mode >= 2:
                    if not self.no_fix_warned:
                        print(f"[OK] GPS fix acquired! Position: {packet.lat:.6f}, {packet.lon:.6f}")
                        print(f"[OK] GPS Mode: {packet.mode}, Satellites: {gps_data['satellites_used']}")
                        self.no_fix_warned = True  # Set to true so we don't spam this message
                    self.callback(gps_data)
                else:
                    # No fix - show status only once
                    if packet_count == 1 or packet_count % 30 == 0:  # Show every 30 seconds
                        print(f"[INFO] GPS connected but waiting for fix (mode={packet.mode}, sats={gps_data['satellites_used']})")
                        print(f"[INFO] Current position: {packet.lat:.6f}, {packet.lon:.6f}")
                
                time.sleep(1)  # Update every second
            except Exception as e:
                print(f"[ERROR] GPS read error: {e}")
                self.gps_connected = False
                print("[WARN] GPS connection lost - falling back to DEMO mode")
                self._send_demo_data()
                return

    def stop(self):
        """Stop GPS monitoring"""
        self.running = False

# Known Minnesota city/town coordinates, town centres, used to put a
# repeater somewhere on the map when its source names a place but no
# position - which is every RadioReference county export.
MN_TOWNS = {
    # Crow Wing County, from the ctid_1327 export
    'pequot lakes': (46.6027, -94.3092),
    # Metro Area
    'minneapolis': (44.9778, -93.2650), 'saint paul': (44.9537, -93.0900),
    'st paul': (44.9537, -93.0900), 'bloomington': (44.8408, -93.2985),
    'plymouth': (45.0105, -93.4555), 'maple grove': (45.0725, -93.4557),
    'edina': (44.8897, -93.3500), 'coon rapids': (45.1200, -93.2878),
    'burnsville': (44.7677, -93.2778), 'eden prairie': (44.8547, -93.4708),
    'blaine': (45.1608, -93.2350), 'lakeville': (44.6497, -93.2428),
    'maple plain': (45.0033, -93.6588), 'ham lake': (45.2503, -93.2044),
    'maplewood': (44.9531, -92.9952), 'ramsey': (45.2611, -93.4500),
    'white bear lake': (45.0847, -93.0098),
    
    # Crow Wing & Cass Counties
    'brainerd': (46.358, -94.201), 'baxter': (46.345, -94.263),
    'crosslake': (46.660, -94.107), 'pequot': (46.603, -94.312),
    'crosby': (46.484, -93.957), 'nisswa': (46.521, -94.289),
    'aitkin': (46.533, -93.717), 'pine river': (46.718, -94.397),
    'pillager': (46.344, -94.482), 'walker': (47.101, -94.587),
    
    # Northern Minnesota
    'duluth': (46.7867, -92.1005), 'superior': (46.7208, -92.1042),
    'hibbing': (47.4271, -92.9377), 'virginia': (47.5232, -92.5366),
    'grand rapids': (47.2368, -93.5302), 'bemidji': (47.4736, -94.8803),
    'international falls': (48.6011, -93.4105), 'thief river falls': (48.1169, -96.1812),
    'cloquet': (46.7216, -92.4594), 'two harbors': (47.0227, -91.6707),
    'ely': (47.9032, -91.8671), 'grand marais': (47.7505, -90.3343),
    'grand portage': (47.9650, -89.6824), 'tofte': (47.5810, -90.8496),
    'cook': (47.8191, -92.6885), 'aurora': (47.5299, -92.2374),
    'silver bay': (47.2955, -91.2526), 'proctor': (46.7477, -92.2224),
    'coleraine': (47.2888, -93.4269), 'isabella': (47.6158, -91.4932),
    'big falls': (48.2000, -93.8000), 'kelliher': (47.9375, -94.4533),
    'lengby': (47.5219, -95.6906), 'wannaska': (48.6572, -95.7253),
    'warroad': (48.9053, -95.3133), 'roosevelt': (48.7942, -95.2036),
    'angle inlet': (49.3489, -95.0708),
    
    # Central Minnesota  
    'saint cloud': (45.5579, -94.1632), 'st cloud': (45.5579, -94.1632),
    'sartell': (45.6219, -94.2069), 'sauk rapids': (45.5953, -94.1617),
    'little falls': (45.9764, -94.3628), 'avon': (45.6080, -94.4508),
    'collegeville': (45.5944, -94.3633), 'paynesville': (45.3794, -94.7122),
    'willmar': (45.1219, -95.0433), 'litchfield': (45.1275, -94.5281),
    'hutchinson': (44.8883, -94.3708), 'silver lake': (44.9044, -94.1933),
    'darwin': (45.0939, -94.4094), 'foley': (45.6647, -93.9097),
    
    # Southeast Minnesota
    'rochester': (44.0219, -92.4635), 'owatonna': (44.0838, -93.2261),
    'austin': (43.6666, -92.9746), 'albert lea': (43.6480, -93.3683),
    'red wing': (44.5625, -92.5338), 'winona': (44.0499, -91.6393),
    'la crescent': (43.8233, -91.3004), 'waseca': (44.0783, -93.5061),
    'faribault': (44.2950, -93.2688), 'northfield': (44.4583, -93.1616),
    'kasson': (44.0297, -92.7502), 'byron': (44.0333, -92.6474),
    'stewartville': (43.8558, -92.4877), 'chatfield': (43.8452, -92.1888),
    'wykoff': (43.7086, -92.2713), 'dennison': (44.4100, -93.0200),
    'glenville': (43.5669, -93.2780), 'racine': (43.8100, -92.5200),
    'lemond': (43.8000, -93.3000), 'medford': (44.1658, -93.2438),
    
    # Southwest Minnesota
    'mankato': (44.1636, -94.0033), 'new ulm': (44.3125, -94.4608),
    'marshall': (44.4469, -95.7883), 'worthington': (43.6200, -95.5956),
    'fairmont': (43.6519, -94.4608), 'jackson': (43.6200, -95.0100),
    'pipestone': (44.0000, -96.3169), 'luverne': (43.6539, -96.2125),
    'tracy': (44.2297, -95.6189), 'slayton': (43.9875, -95.7581),
    'windom': (43.8658, -95.1153), 'fulda': (43.8711, -95.6025),
    'blue earth': (43.6386, -94.1016), 'saint peter': (44.3236, -93.9575),
    'st peter': (44.3236, -93.9575), 'le sueur': (44.4600, -93.9122),
    'le center': (44.3886, -93.7302), 'ellendale': (43.8614, -93.2983),
    'gaylord': (44.5539, -94.2208), 'arlington': (44.6089, -94.0806),
    'green isle': (44.6708, -94.0069), 'wabasso': (44.4072, -95.2508),
    'tyler': (44.2786, -96.1342),
    
    # West Central Minnesota
    'moorhead': (46.8738, -96.7678), 'fergus falls': (46.2830, -96.0776),
    'detroit lakes': (46.8172, -95.8453), 'alexandria': (45.8852, -95.3775),
    'morris': (45.5861, -95.9142), 'breckenridge': (46.2636, -96.5892),
    'wheaton': (45.8064, -96.5000), 'ortonville': (45.3050, -96.4431),
    'montevideo': (44.9458, -95.7231), 'granite falls': (44.8097, -95.5453),
    'clara city': (44.9539, -95.3653), 'dawson': (44.9322, -96.0539),
    'madison': (45.0089, -96.1953), 'perham': (46.5944, -95.5728),
    'dalton': (46.1700, -95.9100), 'bertha': (46.2694, -95.0683),
    'sebeka': (46.6264, -95.0864), 'deer creek': (46.3897, -95.2967),
    'twin valley': (47.2683, -96.2542), 'east grand forks': (47.9297, -97.0242),
    'crookston': (47.7741, -96.6081), 'warren': (48.1958, -96.7731),
    'karlstad': (48.5733, -96.5181),
    
    # South Central Minnesota
    'mankato': (44.1636, -94.0033), 'north mankato': (44.1775, -94.0336),
    'saint james': (43.9869, -94.6275), 'madelia': (44.0525, -94.4200),
    'mountain lake': (43.9369, -94.9297),
    
    # Counties & Towns
    'isanti': (45.4900, -93.2478), 'cambridge': (45.5728, -93.2244),
    'north branch': (45.5111, -92.9808), 'mora': (45.8747, -93.2908),
    'milaca': (45.7553, -93.6539), 'princeton': (45.5697, -93.5819),
    'elk river': (45.3038, -93.5672), 'big lake': (45.3319, -93.7458),
    'monticello': (45.3055, -93.7927), 'buffalo': (45.1719, -93.8744),
    'delano': (45.0411, -93.7886), 'howard lake': (45.0600, -94.0733),
    'annandale': (45.2608, -94.1244), 'clearwater': (45.4169, -94.0486),
    'cold spring': (45.4558, -94.4269), 'richmond': (45.4575, -94.5133),
    'melrose': (45.6747, -94.8133), 'sauk centre': (45.7375, -94.9511),
    'long prairie': (45.9758, -94.8633), 'staples': (46.3558, -94.7947),
    'wadena': (46.4425, -95.1361), 'park rapids': (46.9253, -95.0586),
    'menahga': (46.7536, -95.0975), 'nevis': (46.9678, -94.8400),
    'akeley': (47.0000, -94.7333),
}


# --- TowerWitch -> OP25 sidecar wiring ---
import armer_state_store
import elmer_link
import frequency_store
import radioreference
import repeaterbook
import talkgroup_store
import tw_theme
import hallpass_link
from op25_client import Op25Client

OP25_SIDECAR_URL = "http://192.168.1.31:8080/"   # fallback when [OP25] url is not set
OP25_LOCAL_URL   = "http://localhost:8080/"      # tried first: op25 on this machine
ARMER_CSV_PATH   = os.path.join(os.path.dirname(__file__), "trs_sites_3508.csv")
ARMER_STATE_JSON = os.path.join(os.path.dirname(__file__), "data", "armer_state.json")
# The other half of a RadioReference export - what is said on the towers.
TALKGROUPS_JSON  = os.path.join(os.path.dirname(__file__), "data", "talkgroups.json")
COUNTY_JSON      = os.path.join(os.path.dirname(__file__), "data", "county_frequencies.json")
REPEATERBOOK_CSV = os.path.join(os.path.dirname(__file__), "data", "repeaterbook.csv")
OP25_IMPORT_PATH = "/tw/import"
# --- end op25 wiring ---

class TowerWitchTkinter:
    """Main application class using tkinter"""

    def __init__(self, root):
        self.root = root
        self.p = tw_theme.DAY   # the palette in use; NIGHT after the toggle
        # Hide the window until __init__ finishes so the user doesn't see the
        # default 1024x600 frame flash before saved geometry is applied.
        self.root.withdraw()
        self.root.title("TowerWitch by KC9SP - GPS-Enhanced Tower Locator")
        self.root.geometry("1024x600")

        # Application icon (window title bar / taskbar). Kept as an attribute so
        # Tk doesn't garbage-collect the image after __init__ returns.
        try:
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "towerwitch_64.png")
            self.app_icon = tk.PhotoImage(file=icon_path)
            self.root.iconphoto(True, self.app_icon)
        except Exception as e:
            print(f"[WARN] Could not set window icon: {e}")

        # Handle window close button (X)
        self.root.protocol("WM_DELETE_WINDOW", self.quit_application)

        # Configuration
        self.config_file = os.path.join(os.path.dirname(__file__), "towerwitch_config.ini")
        self.state_file = os.path.join(os.path.dirname(__file__), "towerwitch_state.json")
        self.load_configuration()

        # Initialize APIs
        self.radio_api = RadioReferenceAPI(self.api_key)

        # Load saved state (position, town, etc.) - prevents Minneapolis default API calls
        saved_state = self.load_state()
        self.has_saved_state = bool(saved_state)

        # Bootstrap ARMER state JSON (idempotent; preserves prior observations)
        try:
            armer_state_store.bootstrap_from_csv(ARMER_CSV_PATH, ARMER_STATE_JSON)
            print(f"[OK] ARMER state bootstrapped at {ARMER_STATE_JSON}")
        except Exception as e:
            print(f"[WARN] ARMER state bootstrap failed: {e}")

        # Background poller for the op25 HTTP terminal. Same machine first,
        # then the configured address; the Send button follows its answer.
        self.armer_loaded = False
        self.op25_client = Op25Client(
            url=[OP25_LOCAL_URL, self.config.get('OP25', 'url', fallback=OP25_SIDECAR_URL)],
            on_update=lambda st: armer_state_store.update_from_op25(ARMER_STATE_JSON, st),
            on_status=lambda reachable, url: self.root.after(0, self._update_op25_button),
            log_fn=lambda msg: print(f"[OP25] {msg}"),
        )
        self.op25_client.start()


        # GPS data - use saved state or fall back to Minneapolis
        self.last_lat = saved_state.get('last_lat', 44.9778)
        self.last_lon = saved_state.get('last_lon', -93.2650)
        self.gps_worker = None
        self.nearest_town = saved_state.get('nearest_town', "Minneapolis, MN")
        self.last_geocode_time = 0  # Rate limiting for geocoding (60 sec intervals)
        self.last_tower_update = 0  # Rate limiting for tower distance updates
        self.update_counter = 0  # Counter for staggered updates

        # Position at which local CSV data was last loaded. Used to detect when
        # the GPS has drifted far enough that data is "out of sync" and the
        # Refresh button should flash to prompt the user.
        self.data_lat = self.last_lat
        self.data_lon = self.last_lon
        # This far from where the lists were loaded they are stale. With
        # auto_refresh on they reload themselves there; off, the Refresh
        # button flashes and waits for a hand.
        self.stale_threshold_miles = self.config.getfloat('GPS', 'refresh_miles', fallback=5.0)
        self.auto_refresh = self.config.getboolean('GPS', 'auto_refresh', fallback=True)
        self._refresh_running = False
        self._flash_after_id = None
        self._flash_on = False
        self._last_gps_heartbeat = 0.0

        # Restore window geometry if saved
        if 'window_geometry' in saved_state:
            try:
                self.root.geometry(saved_state['window_geometry'])
            except:
                pass

        # Amateur radio data
        self.amateur_2m_data = []
        self.amateur_70cm_data = []
        self.amateur_simplex_data = []

        # Night mode state (starts in day mode)
        self.night_mode_on = False

        # Where the position came from. A saved or default position is not
        # this program's own and is never broadcast as one: ELMER would take
        # it as a live fix from TowerWitch. 'gps' once the receiver has a
        # real lock in this session.
        self.position_source = 'none'
        # Where a borrowed position came from, in words, for the wall and the
        # status line: "ELMER's QTH EN34jv", or the name of the ELMER that
        # had a fix of its own.
        self.elmer_words = ''
        self.last_speed = None
        self.is_vehicle_speed = False
        # The closest ARMER sites as plain dicts, snapshotted on the main
        # thread when the table is filled, so the broadcast thread never
        # touches a Tk widget.
        self._armer_closest = []

        # Create the interface
        self.create_widgets()
        self.setup_keyboard_shortcuts()

        # Tell the network where the station is: the position broadcast
        # ELMER listens for on udp/12345, and the greeting HallPass puts on
        # its wall. Nothing is configured at either end.
        self.setup_udp()
        self.hello = hallpass_link.Hello(self.describe_for_room).start()
        
        # Load static data with saved position
        if saved_state:
            print(f"[OK] Restored last position: {self.last_lat:.6f}, {self.last_lon:.6f}")
            print(f"[OK] Restored nearest town: {self.nearest_town}")
            print("[INFO] Displaying saved data - click 'Refresh Data' to update for current location")

        self.load_static_data()
        print("[DEBUG] Static data loaded")

        # Seed the GPS display with the saved location so the user sees their
        # last-known position immediately on startup, not a blank or DEMO label.
        # First-time users (no state file) still get DEMO via GPSWorker fallback.
        if self.has_saved_state:
            self.update_gps_display({
                'lat': self.last_lat,
                'lon': self.last_lon,
                'alt': 0.0,
                'time': datetime.now().isoformat(),
                'mode': 0,
                'satellites_used': 0,
            })
            self.gps_status.config(text="GPS: Last Known (waiting for fix)", foreground=self.p.amber)

        print("[DEBUG] About to start GPS...")
        self.start_gps()
        print("[DEBUG] GPS started")
        
        # Manual refresh mode - performance optimization for Raspberry Pi
        print("[INFO] Running in MANUAL REFRESH mode for optimal performance")
        print("  - GPS position: Continuous tracking")
        print("  - GPS display: Updates automatically") 
        print("  - Tower/Repeater data: Use 'Refresh Data' button to update")
        print("  - Nearest town: Updates with manual refresh")
        print("[TIP] Click 'Refresh Data' after moving to a new location")

        # Update datetime
        self.update_datetime()

    def load_configuration(self):
        """Load configuration from INI file"""
        self.config = configparser.ConfigParser()

        if os.path.exists(self.config_file):
            self.config.read(self.config_file)
            print(f"[OK] Loaded configuration from {self.config_file}")
        else:
            # Create default config
            self.config['API'] = {
                'radio_reference_key': 'your_api_key_here',
                'force_refresh_cache': 'false'
            }
            self.config['GPS'] = {
                'refresh_miles': '5',
                'auto_refresh': 'true'
            }

            with open(self.config_file, 'w') as f:
                self.config.write(f)
            print(f"[OK] Created default configuration at {self.config_file}")

        # Get API key
        self.api_key = self.config.get('API', 'radio_reference_key', fallback=None)
        if self.api_key and self.api_key != 'your_api_key_here':
            print("[OK] Radio Reference API key found")
        else:
            print("[WARN] No Radio Reference API key configured")

    def load_state(self):
        """Load saved application state (last position, window geometry, etc.)"""
        if not os.path.exists(self.state_file):
            return {}
        
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
                print(f"[OK] Loaded saved state from {self.state_file}")
                return state
        except Exception as e:
            print(f"[WARN] Could not load state file: {e}")
            return {}
    
    def save_state(self):
        """Save current application state for next session"""
        try:
            state = {
                'last_lat': self.last_lat,
                'last_lon': self.last_lon,
                'nearest_town': self.nearest_town,
                'window_geometry': self.root.geometry(),
                'timestamp': datetime.now().isoformat()
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            print(f"[OK] Saved application state to {self.state_file}")
        except Exception as e:
            print(f"[WARN] Could not save state: {e}")

    def create_widgets(self):
        """Create the main interface widgets"""
        self.style = ttk.Style()
        tw_theme.apply(self.style, self.root, self.p)

        # Top bar, edge to edge on its own panel with a hairline under it,
        # as ELMER's: the mark and its sub-line left, the state chips right.
        header_frame = ttk.Frame(self.root, style='Topbar.TFrame', padding=(14, 8))
        header_frame.pack(fill=tk.X)
        ttk.Separator(self.root, orient='horizontal').pack(fill=tk.X)

        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Logo to the left of the mark. Kept as an attribute so Tk doesn't
        # garbage-collect the image once create_widgets returns.
        try:
            logo_path = os.path.join(os.path.dirname(__file__), "assets", "towerwitch_48.png")
            self.header_logo = tk.PhotoImage(file=logo_path)
            logo_label = ttk.Label(header_frame, image=self.header_logo, style='Topbar.TLabel')
            logo_label.pack(side=tk.LEFT, padx=(0, 10))
        except Exception as e:
            print(f"[WARN] Could not load header logo: {e}")

        brand = ttk.Frame(header_frame, style='Topbar.TFrame')
        brand.pack(side=tk.LEFT)
        ttk.Label(brand, text="TOWERWITCH", style='Brand.TLabel').pack(anchor='w')
        ttk.Label(brand, text="GPS-ENHANCED TOWER LOCATOR  \u00b7  KC9SP",
                  style='BrandSub.TLabel').pack(anchor='w', pady=(2, 0))

        self.datetime_label = ttk.Label(header_frame, text="", style='Topbar.TLabel',
                                        font=tw_theme.font(12))
        self.datetime_label.pack(side=tk.RIGHT, padx=(10, 4))

        # GPS state as a chip; its colour is set with the state.
        self.gps_status = ttk.Label(header_frame, text="GPS: Starting...", style='Chip.TLabel')
        self.gps_status.pack(side=tk.RIGHT, padx=6)

        # Control buttons frame
        controls_frame = ttk.Frame(main_frame)
        controls_frame.pack(fill=tk.X, pady=(0, 10))

        # Night mode toggle - larger for touch
        self.night_mode_var = tk.BooleanVar()
        night_mode_btn = ttk.Checkbutton(controls_frame, text="Night Mode",
                                        variable=self.night_mode_var,
                                        command=self.toggle_night_mode)
        night_mode_btn.pack(side=tk.LEFT, padx=5, pady=5)

        # Refresh button. Plain at rest; while the lists are stale it flashes
        # to the accent (Stale.TButton in tw_theme), the colour that asks.
        self.refresh_btn = ttk.Button(controls_frame, text="Refresh Data",
                                command=self.refresh_all_data)
        self.refresh_btn.pack(side=tk.LEFT, padx=10, pady=5, ipadx=15, ipady=8)

        # Fullscreen toggle button - for touch screen access
        fullscreen_btn = ttk.Button(controls_frame, text="⛶ Fullscreen",
                                   command=self.toggle_fullscreen)
        fullscreen_btn.pack(side=tk.LEFT, padx=10, pady=5, ipadx=15, ipady=8)

        # Exit button — clean shutdown of all background threads
        exit_btn = ttk.Button(controls_frame, text="\u2715 Exit", style='Danger.TButton',
                              command=self.quit_application)
        exit_btn.pack(side=tk.RIGHT, padx=10, pady=5, ipadx=15, ipady=8)


        # Create main notebook (tabbed interface)
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Create tabs
        self.create_gps_tab()
        self.create_grid_tab()
        self.create_armer_tab()
        self.create_interop_tab()
        self.create_aviation_tab()
        self.create_skywarn_tab()
        self.create_noaa_weather_tab()
        self.create_amateur_tab()
        self.create_fusion_tab()
        self.create_dmr_dstar_tab()
        tw_theme.dress(self.root)

    def setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts for common operations"""
        # Ctrl+Q - Quit (Linux/Unix standard)
        self.root.bind('<Control-q>', lambda e: self.quit_application())
        
        # Ctrl+C - Interrupt/Quit (Terminal standard)
        self.root.bind('<Control-c>', lambda e: self.quit_application())
        
        # F11 - Toggle fullscreen
        self.root.bind('<F11>', lambda e: self.toggle_fullscreen())
        
        # F12 - Toggle night mode
        self.root.bind('<F12>', lambda e: self.toggle_night_mode_key())
        
        print("[OK] Keyboard shortcuts enabled: Ctrl+Q, Ctrl+C, F11 (fullscreen), F12 (night mode)")

    def quit_application(self):
        """Cleanly exit the application.

        Every line of this used to be taken on trust, and shutdown is the
        one place where that does not hold: the state file may sit on a
        card gone read-only, a socket may already be gone, a worker may
        never have started because its section of the config was off.
        Tkinter catches whatever a WM_DELETE_WINDOW handler raises,
        reports it, and then leaves the window up - so a failure in here
        does not read as a crash, it reads as a window that will not
        close and a process that stays resident with its threads. On a Pi
        at the end of a coax run that is a leak nobody is watching for.

        So each step is taken on its own and a failure is named rather
        than ending the teardown, and the window comes down either way.
        """
        print("[OK] Shutting down TowerWitch...")

        def stop_op25():
            client = getattr(self, 'op25_client', None)
            if client is not None:
                client.stop()

        def close_hello():
            hello = getattr(self, 'hello', None)
            if hello is not None:
                hello.close()

        def stop_udp():
            # The socket was never closed on the way out before this; a
            # daemon thread dying with the process hid it, but the handle
            # is ours to give back.
            stop = getattr(self, '_udp_stop', None)
            if stop is not None:
                stop.set()
            sock = getattr(self, 'udp_socket', None)
            if sock is not None:
                sock.close()

        def stop_gps():
            worker = getattr(self, 'gps_worker', None)
            if worker is not None:
                worker.stop()

        for what, step in (("saving state", self.save_state),
                           ("stopping the op25 client", stop_op25),
                           ("closing the HallPass hello", close_hello),
                           ("stopping the UDP broadcast", stop_udp),
                           ("stopping the GPS worker", stop_gps)):
            try:
                step()
            except Exception as e:      # no one step may strand the window
                print(f"[WARN] shutting down, {what}: {e}")

        try:
            self.root.quit()
            self.root.destroy()
        except tk.TclError as e:
            # Already torn down - a second Exit, or the window manager got
            # here first. Nothing left to close, and saying so beats a
            # traceback that looks like a fault.
            print(f"[INFO] window was already closed: {e}")
        finally:
            print("[OK] TowerWitch is down")
            sys.exit(0)

    # ------------------------------------------------------------ the network
    # The same packet TowerWitch-P sends, from the same [UDP] settings, so
    # ELMER and anything else listening see one TowerWitch whichever build
    # is on screen.

    def setup_udp(self):
        """Read the [UDP] settings and start the position broadcast."""
        self._udp_stop = threading.Event()
        self.udp_socket = None
        self.udp_enabled = self.config.getboolean('UDP', 'enabled', fallback=True)
        self.udp_port = self.config.getint('UDP', 'port', fallback=UDP_CONFIG['port'])
        self.udp_broadcast_ip = self.config.get('UDP', 'broadcast_ip', fallback='255.255.255.255')
        self.udp_send_interval = self.config.getint('UDP', 'send_interval', fallback=25)
        self.udp_sent = 0
        if not self.udp_enabled:
            print("[INFO] UDP broadcasting is off in the config")
            return
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except OSError as e:
            print(f"[WARN] UDP setup failed: {e}")
            self.udp_enabled = False
            return
        threading.Thread(target=self._udp_run, daemon=True, name="towerwitch-udp").start()
        print(f"[OK] UDP broadcasting to {self.udp_broadcast_ip}:{self.udp_port} every {self.udp_send_interval}s")

    def _udp_run(self):
        while not self._udp_stop.is_set():
            try:
                self.send_udp_armer_data()
            except Exception as e:      # reads GUI state; must never take the GUI down
                print(f"[WARN] UDP send error: {e}")
            self._udp_stop.wait(self.udp_send_interval)

    def send_udp_armer_data(self):
        """One broadcast: the position when it is this program's own, and
        the closest ARMER sites. The position is left out until the receiver
        has a real fix - a packet without one is tower data and nothing more."""
        if not self.udp_enabled or not self.udp_socket:
            return
        ours = self.position_source in ('gps', 'manual')
        udp_data = {
            'timestamp': datetime.now().isoformat(),
            'source': 'TowerWitch',
            'gps_lat': self.last_lat if ours else None,
            'gps_lon': self.last_lon if ours else None,
            'speed_mps': self.last_speed,
            'is_vehicle_speed': self.is_vehicle_speed,
            'closest_armer_towers': list(self._armer_closest),
        }
        message = json.dumps(udp_data).encode('utf-8')
        # The limited broadcast leaves by one interface only; each
        # interface's own broadcast reaches its segment regardless.
        targets = [self.udp_broadcast_ip]
        if self.udp_broadcast_ip == '255.255.255.255':
            targets = hallpass_link.broadcast_targets() + ['127.0.0.1']
        for target in targets:
            try:
                self.udp_socket.sendto(message, (target, self.udp_port))
            except OSError as e:
                print(f"[WARN] UDP to {target}: {e}")
        self.udp_sent += 1
        if self.udp_sent == 1:
            print(f"[OK] UDP broadcasting started - {len(self._armer_closest)} towers, "
                  f"position {'included' if ours else 'withheld until the GPS has a fix'}")

    def describe_for_room(self):
        """TowerWitch's line on HallPass's wall: where the station is and how
        it knows, and the nearest town. Read on the greeting's own thread from
        plain attributes, never from a widget."""
        if self.position_source == 'none':
            state = "waiting for a position"
        else:
            try:
                grid = self.lat_lon_to_maidenhead(self.last_lat, self.last_lon)
            except Exception:
                grid = "%.3f, %.3f" % (self.last_lat, self.last_lon)
            # How it knows, and not always "GPS": a position borrowed from
            # ELMER is somebody else's answer and the wall should say so,
            # or the room reads it as a receiver that is not there.
            if self.position_source == 'elmer':
                state = "%s (%s)" % (grid, self.elmer_words or "from ELMER")
            else:
                state = "%s (GPS)" % grid
            if self.nearest_town:
                state += " · " + self.nearest_town
        if self._armer_closest:
            state += " · nearest ARMER " + self._armer_closest[0]['site_name']
        return {"state": state, "version": "tk", "alarm": None, "url": ""}

    def toggle_fullscreen(self):
        """Toggle between fullscreen and windowed mode"""
        current_state = self.root.attributes('-fullscreen')
        self.root.attributes('-fullscreen', not current_state)
        if not current_state:
            print("[OK] Fullscreen mode enabled (press F11 to exit)")
        else:
            print("[OK] Windowed mode enabled")

    def _update_op25_button(self):
        """Send to OP25 is live when ARMER sites are loaded and an op25 is
        answering; otherwise greyed, saying which is missing."""
        btn = getattr(self, 'op25_btn', None)
        if btn is None:
            return
        client = getattr(self, 'op25_client', None)
        if not self.armer_loaded:
            text, state = "Send to OP25 \u2014 no ARMER data", 'disabled'
        elif not (client and client.reachable):
            text, state = "Send to OP25 \u2014 op25 not found", 'disabled'
        else:
            text, state = "\U0001F4E1 Send to OP25", 'normal'
        try:
            btn.config(text=text, state=state)
        except Exception as e:
            print(f"[WARN] Could not update Send to OP25 button: {e}")

    def send_to_op25(self):
        """Hand off the selected ARMER site to a running op25 instance.

        Reads the enriched site record from armer_state.json (which has any
        WACN/SYSID picked up by the op25 client thread) and POSTs an overlay
        fragment to the op25 sidecar's /tw/import endpoint.
        """
        import urllib.request, urllib.error
        selection = self.armer_tree.selection()
        if not selection:
            messagebox.showwarning("Send to OP25", "Select an ARMER site first.", parent=self.root)
            return
        iid = selection[0]
        try:
            rfid_str, stid_str = iid.split("-", 1)
            rfid, stid = int(rfid_str), int(stid_str)
        except ValueError:
            messagebox.showerror("Send to OP25", f"Could not parse site key: {iid}", parent=self.root)
            return

        site = armer_state_store.get_site(ARMER_STATE_JSON, rfid, stid)
        if site is None:
            messagebox.showerror("Send to OP25", f"Site {iid} not found in state file.", parent=self.root)
            return

        chan_entry = {
            "sysname": "ARMER",
            "site_id": site["site_id_key"],
            "site_description": site["description"],
            "control_channel_list": ",".join(f"{hz/1e6:.6f}" for hz in site["cc_freqs_hz"]),
        }
        for k in ("nac", "wacn", "sysid"):
            if site.get(k):
                chan_entry[k] = site[k]

        payload = {
            "_source": "towerwitch",
            "_sent_at": datetime.now().isoformat(),
            "_gps": {"lat": self.last_lat, "lon": self.last_lon},
            "_confidence": site["confidence"],
            "trunking": {"chans": [chan_entry]},
        }

        url = self.op25_client.url.rstrip("/") + OP25_IMPORT_PATH
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                resp_body = json.loads(resp.read().decode())
            messagebox.showinfo(
                "Send to OP25",
                f"Sent {chan_entry['sysname']}\n"
                f"Confidence: {site['confidence']}\n"
                f"Response: {resp_body}",
                parent=self.root,
            )
        except urllib.error.URLError as e:
            messagebox.showerror(
                "Send to OP25",
                f"Could not reach op25 sidecar at {url}\n\n{e.reason}\n\n"
                "Is multi_rx.py running on the op25 Pi?",
                parent=self.root,
            )
        except Exception as e:
            messagebox.showerror("Send to OP25", f"Error: {e}", parent=self.root)

    def apply_tab_colors(self):
        """Apply colors using tkinter's Frame-based approach"""
        # Since ttk tab styling is limited, let's use a simpler visual approach
        # with colored frames and better organization
        print("[OK] Tkinter tab coloring - using improved visual organization")

        # Update tab text with better colored indicators
        self.update_tab_indicators()

    def update_tab_indicators(self):
        """Update tab text with clear indicators"""
        try:
            # Main tabs with clear text labels - must match actual tab order!
            main_tabs = [
                ("GPS", "GPS Data"),
                ("Grids", "Grid Systems"),
                ("ARMER", "ARMER Sites"),
                ("InterOp", "Interoperability"),
                ("Aviation", "Aviation Frequencies"),
                ("Skywarn", "Weather Emergency"),
                ("NOAA", "NOAA Weather Radio"),
                ("Amateur", "Amateur Radio")
            ]

            # Update main tab labels
            for i, (text, tooltip) in enumerate(main_tabs):
                if i < self.notebook.index("end"):
                    self.notebook.tab(i, text=text)
                    print(f"[OK] Updated main tab {i}: {text}")

            # Update amateur sub-tabs
            amateur_tabs = [
                "10m Band",
                "6m Band",
                "2m Band",
                "1.25m Band",
                "70cm Band",
                "Simplex",
                "Fusion",
                "DMR/D-Star"
            ]

            for i, tab_text in enumerate(amateur_tabs):
                if i < self.amateur_notebook.index("end"):
                    self.amateur_notebook.tab(i, text=tab_text)
                    print(f"[OK] Updated amateur tab {i}: {tab_text}")

        except Exception as e:
            print(f"[ERROR] Error updating tab indicators: {e}")

    def create_gps_tab(self):
        """Create GPS data tab with navigation dashboard"""
        gps_frame = ttk.Frame(self.notebook)
        self.notebook.add(gps_frame, text="GPS")

        # GPS Navigation Dashboard - visual status panel
        dashboard_frame = ttk.LabelFrame(gps_frame, text="GPS Navigation Dashboard", padding=10)
        dashboard_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        # Create dashboard grid (3 columns)
        dashboard_grid = ttk.Frame(dashboard_frame)
        dashboard_grid.pack(fill=tk.X)
        
        # Column 1: Fix Status
        col1 = ttk.Frame(dashboard_grid)
        col1.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=5)
        ttk.Label(col1, text="FIX STATUS", style='Title.TLabel').pack()
        self.nav_fix_status = ttk.Label(col1, text="NO FIX", font=tw_theme.font(15, 'bold', mono=True), foreground=self.p.red)
        self.nav_fix_status.pack()
        
        # Column 2: Satellites
        col2 = ttk.Frame(dashboard_grid)
        col2.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=5)
        ttk.Label(col2, text="SATELLITES", style='Title.TLabel').pack()
        self.nav_satellites = ttk.Label(col2, text="0", font=tw_theme.font(15, 'bold', mono=True))
        self.nav_satellites.pack()
        
        # Column 3: Speed
        col3 = ttk.Frame(dashboard_grid)
        col3.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=5)
        ttk.Label(col3, text="SPEED", style='Title.TLabel').pack()
        self.nav_speed = ttk.Label(col3, text="0.0 mph", font=tw_theme.font(15, 'bold', mono=True))
        self.nav_speed.pack()
        
        # Second row: Heading and Altitude
        dashboard_grid2 = ttk.Frame(dashboard_frame)
        dashboard_grid2.pack(fill=tk.X, pady=(10, 0))
        
        # Column 4: Heading
        col4 = ttk.Frame(dashboard_grid2)
        col4.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=5)
        ttk.Label(col4, text="HEADING", style='Title.TLabel').pack()
        self.nav_heading = ttk.Label(col4, text="---°", font=tw_theme.font(15, 'bold', mono=True))
        self.nav_heading.pack()
        
        # Column 5: Altitude
        col5 = ttk.Frame(dashboard_grid2)
        col5.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=5)
        ttk.Label(col5, text="ALTITUDE", style='Title.TLabel').pack()
        self.nav_altitude = ttk.Label(col5, text="--- ft", font=tw_theme.font(15, 'bold', mono=True))
        self.nav_altitude.pack()
        
        # Column 6: Last Update
        col6 = ttk.Frame(dashboard_grid2)
        col6.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=5)
        ttk.Label(col6, text="LAST UPDATE", style='Title.TLabel').pack()
        self.nav_last_update = ttk.Label(col6, text="--:--:--", font=tw_theme.font(15, 'bold', mono=True))
        self.nav_last_update.pack()

        # GPS detailed info label
        info_label = ttk.Label(gps_frame, text="Detailed GPS Information",
                              font=(tw_theme.SANS, 14, 'bold'))
        info_label.pack(pady=(10, 5))

        # GPS data tree
        columns = ('Property', 'Value', 'Unit')
        self.gps_tree = ttk.Treeview(gps_frame, columns=columns, show='headings', height=10)

        # Define column headings and widths (percentage-based)
        available_width = 980
        for col in columns:
            self.gps_tree.heading(col, text=col)
            if col == 'Property':
                width = int(available_width * 0.35)
            elif col == 'Value':
                width = int(available_width * 0.40)
            else:  # Unit
                width = int(available_width * 0.25)
            self.gps_tree.column(col, width=width, stretch=True)

        # Add scrollbar
        gps_scroll = ttk.Scrollbar(gps_frame, orient=tk.VERTICAL, command=self.gps_tree.yview)
        self.gps_tree.configure(yscrollcommand=gps_scroll.set)

        # Pack GPS tree and scrollbar
        self.gps_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 0))
        gps_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Initialize GPS data
        self.update_gps_display()

    def create_grid_tab(self):
        """Create grid systems tab"""
        grid_frame = ttk.Frame(self.notebook)
        self.notebook.add(grid_frame, text="Grids")

        info_label = ttk.Label(grid_frame, text="Location Grid Systems & Coordinates",
                              font=(tw_theme.SANS, 16, 'bold'))
        info_label.pack(pady=15)

        # Grid data tree
        columns = ('Grid System', 'Value', 'Info')
        self.grid_tree = ttk.Treeview(grid_frame, columns=columns, show='headings', height=8)

        # Define column widths (percentage-based)
        available_width = 980
        for col in columns:
            self.grid_tree.heading(col, text=col)
            if col == 'Grid System':
                width = int(available_width * 0.35)
            elif col == 'Value':
                width = int(available_width * 0.40)
            else:  # Info
                width = int(available_width * 0.25)
            self.grid_tree.column(col, width=width, stretch=True)

        self.grid_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Initialize grid display
        self.update_grid_display()

    def create_armer_tab(self):
        """Create ARMER tab"""
        armer_frame = ttk.Frame(self.notebook)
        self.notebook.add(armer_frame, text="ARMER")

        # Header bar: tab title left, Send-to-OP25 button right.
        # Acts as a tab-local action affordance now that the button is
        # contextually scoped to the ARMER view.
        armer_header = ttk.Frame(armer_frame)
        armer_header.pack(fill=tk.X, padx=10, pady=10)

        info_label = ttk.Label(armer_header, text="ARMER Radio Sites and Talkgroups",
                              font=(tw_theme.SANS, 16, 'bold'))
        info_label.pack(side=tk.LEFT)

        # Greyed with the reason until there is a site to send and an op25
        # to send it to; the same button in the same place either way.
        self.op25_btn = ttk.Button(armer_header, command=self.send_to_op25)
        self.op25_btn.pack(side=tk.RIGHT, padx=5, ipadx=15, ipady=6)
        self._update_op25_button()

        # A RadioReference account gives you the system as two CSVs. Put
        # them anywhere - a stick, a download folder, the other Pi - and
        # point this at them; which file is which is read off the header,
        # not the name. Export writes them back properly quoted, which
        # the file from the website is not.
        ttk.Button(armer_header, text="Export CSV...",
                   command=self.export_radioreference).pack(
                       side=tk.RIGHT, padx=5, ipadx=10, ipady=6)
        ttk.Button(armer_header, text="Import CSV...",
                   command=self.import_radioreference).pack(
                       side=tk.RIGHT, padx=5, ipadx=10, ipady=6)

        # What the last import found, under the buttons rather than in a
        # box somebody has to dismiss before they can read the tree. Until
        # there has been one it says what the button takes, because a
        # button that only says "Import" does not tell you what to bring
        # out to a unit that has no connection to go and look with.
        # wraplength, because this label also carries the report of an
        # import, which runs long - and a label that does not wrap sets
        # the width of everything above it. A 1024-wide Pi screen is the
        # one that has to survive it, not this desk.
        self.armer_import_note = ttk.Label(
            armer_frame,
            text="Import takes RadioReference and RepeaterBook CSV exports,"
                 " read by header rather than filename.",
            font=(tw_theme.SANS, 9), wraplength=940, justify=tk.LEFT)
        self.armer_import_note.pack(fill=tk.X, padx=10)

        # ARMER sites tree
        columns = ('Site', 'Description', 'County', 'Distance', 'Bearing', 'Range', 'Frequencies')
        self.armer_tree = ttk.Treeview(armer_frame, columns=columns, show='headings', height=15)

        # Define column widths (percentage-based)
        available_width = 980
        for col in columns:
            self.armer_tree.heading(col, text=col)
            if col == 'Site':
                width = int(available_width * 0.10)
            elif col == 'Description':
                width = int(available_width * 0.25)
            elif col == 'County':
                width = int(available_width * 0.15)
            elif col == 'Distance':
                width = int(available_width * 0.10)
            elif col == 'Bearing':
                width = int(available_width * 0.10)
            elif col == 'Range':
                width = int(available_width * 0.10)
            else:  # Frequencies
                width = int(available_width * 0.20)
            self.armer_tree.column(col, width=width, stretch=True)

        self.armer_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def create_interop_tab(self):
        """Create Interoperability tab"""
        interop_frame = ttk.Frame(self.notebook)
        self.notebook.add(interop_frame, text="InterOp")

        info_label = ttk.Label(interop_frame, text="Minnesota Interoperability Channels",
                              font=(tw_theme.SANS, 16, 'bold'))
        info_label.pack(pady=15)

        # Interop data tree
        columns = ('Frequency', 'Description', 'Alpha Tag', 'Mode', 'Category')
        self.interop_tree = ttk.Treeview(interop_frame, columns=columns, show='headings', height=15)

        # Define column widths (percentage-based)
        available_width = 980
        for col in columns:
            self.interop_tree.heading(col, text=col)
            if col == 'Frequency':
                width = int(available_width * 0.12)
            elif col == 'Description':
                width = int(available_width * 0.40)
            elif col == 'Alpha Tag':
                width = int(available_width * 0.16)
            elif col == 'Mode':
                width = int(available_width * 0.16)
            else:  # Category
                width = int(available_width * 0.16)
            self.interop_tree.column(col, width=width, stretch=True)

        self.interop_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def create_aviation_tab(self):
        """Create Aviation frequencies tab with sub-tabs"""
        aviation_frame = ttk.Frame(self.notebook)
        self.notebook.add(aviation_frame, text="Aviation")

        # Create sub-notebook for aviation categories
        self.aviation_notebook = ttk.Notebook(aviation_frame)
        self.aviation_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create aviation sub-tabs
        self.create_aviation_subtab("Nearby", "Nearby Airports (GPS-based)")
        self.create_aviation_subtab("Emergency", "Emergency Aviation Operations")
        self.create_aviation_subtab("Common", "Common Aviation Frequencies")
        self.create_aviation_subtab("Center", "Center & Approach Control")

    def create_aviation_subtab(self, tab_name, description):
        """Create a sub-tab for aviation frequencies"""
        subtab_frame = ttk.Frame(self.aviation_notebook)
        self.aviation_notebook.add(subtab_frame, text=tab_name)

        # Description label
        desc_label = ttk.Label(subtab_frame, text=description,
                              font=(tw_theme.SANS, 14, 'bold'))
        desc_label.pack(pady=12)

        # Columns for aviation data
        columns = ('Frequency', 'Description', 'Alpha Tag', 'Mode', 'Category')
        
        # Calculate column widths based on window width (proportional sizing)
        # Get available width (accounting for padding/margins)
        available_width = 980  # ~1024 window width minus padding
        
        # Use tree mode for Nearby tab to enable collapsible airports
        if tab_name == "Nearby":
            aviation_tree = ttk.Treeview(subtab_frame, columns=columns, show='tree headings', height=12)
            # Airport column: 17% of available width
            aviation_tree.column('#0', width=int(available_width * 0.17), stretch=False)
            aviation_tree.heading('#0', text='Airport')
        else:
            aviation_tree = ttk.Treeview(subtab_frame, columns=columns, show='headings', height=12)

        for col in columns:
            aviation_tree.heading(col, text=col)
            if col == 'Description':
                # Description: 42% with stretch enabled
                width = int(available_width * 0.42)
                aviation_tree.column(col, width=width, stretch=True)
            elif col == 'Frequency':
                # Frequency: 10% fixed
                width = int(available_width * 0.10)
                aviation_tree.column(col, width=width, stretch=False)
            elif col == 'Mode':
                # Mode: 7% fixed
                width = int(available_width * 0.07)
                aviation_tree.column(col, width=width, stretch=False)
            elif col == 'Alpha Tag':
                # Alpha Tag: 12% fixed
                width = int(available_width * 0.12)
                aviation_tree.column(col, width=width, stretch=False)
            elif col == 'Category':
                # Category: 12% fixed
                width = int(available_width * 0.12)
                aviation_tree.column(col, width=width, stretch=False)

        aviation_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Configure tags for styling (especially for Nearby airports)
        if tab_name == "Nearby":
            # Make airport parent rows bold and slightly different
            aviation_tree.tag_configure('airport', font=(tw_theme.SANS, 12, 'bold'))
            aviation_tree.tag_configure('frequency', font=(tw_theme.SANS, 11))

        # Store reference to the tree based on tab name
        if tab_name == "Nearby":
            self.aviation_nearby_tree = aviation_tree
        elif tab_name == "Emergency":
            self.aviation_emergency_tree = aviation_tree
        elif tab_name == "Common":
            self.aviation_common_tree = aviation_tree
        elif tab_name == "Center":
            self.aviation_center_tree = aviation_tree

    def create_skywarn_tab(self):
        """Create Skywarn tab"""
        skywarn_frame = ttk.Frame(self.notebook)
        self.notebook.add(skywarn_frame, text="Skywarn")

        info_label = ttk.Label(skywarn_frame, text="Skywarn Weather Emergency Repeaters",
                              font=(tw_theme.SANS, 16, 'bold'))
        info_label.pack(pady=15)

        # Skywarn data tree
        columns = ('Call Sign', 'Location', 'Frequency', 'Tone', 'Distance', 'Bearing')
        self.skywarn_tree = ttk.Treeview(skywarn_frame, columns=columns, show='headings', height=15)

        # Define column widths (percentage-based)
        available_width = 980
        for col in columns:
            self.skywarn_tree.heading(col, text=col)
            if col == 'Call Sign':
                width = int(available_width * 0.15)
            elif col == 'Location':
                width = int(available_width * 0.25)
            elif col == 'Frequency':
                width = int(available_width * 0.15)
            elif col == 'Tone':
                width = int(available_width * 0.15)
            elif col == 'Distance':
                width = int(available_width * 0.12)
            else:  # Bearing
                width = int(available_width * 0.18)
            self.skywarn_tree.column(col, width=width, stretch=True)

        self.skywarn_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def create_fusion_tab(self):
        """Create Fusion repeater tab"""
        fusion_frame = ttk.Frame(self.amateur_notebook)
        self.amateur_notebook.add(fusion_frame, text="Fusion")

        info_label = ttk.Label(fusion_frame, text="Yaesu System Fusion Digital Repeaters",
                              font=(tw_theme.SANS, 16, 'bold'))
        info_label.pack(pady=15)

        # Fusion data tree - optimized for touch screen with responsive columns
        columns = ('Call', 'Location', 'Output', 'Input', 'Tone', 'Modes', 'Dist', 'Bear')
        self.fusion_tree = ttk.Treeview(fusion_frame, columns=columns, show='headings', height=15)

        # Configure columns with percentage-based widths
        available_width = 980
        for col in columns:
            # Use short header names for compact display
            header_text = col
            if col == 'Dist':
                header_text = 'Miles'
            elif col == 'Bear':
                header_text = 'Bearing'
            
            self.fusion_tree.heading(col, text=header_text)
            
            if col == 'Call':
                width = int(available_width * 0.10)
            elif col == 'Location':
                width = int(available_width * 0.25)
            elif col == 'Output':
                width = int(available_width * 0.12)
            elif col == 'Input':
                width = int(available_width * 0.12)
            elif col == 'Tone':
                width = int(available_width * 0.10)
            elif col == 'Modes':
                width = int(available_width * 0.12)
            elif col == 'Dist':
                width = int(available_width * 0.10)
            else:  # Bear
                width = int(available_width * 0.09)
            
            self.fusion_tree.column(col, width=width, stretch=True)

        self.fusion_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def create_dmr_dstar_tab(self):
        """Create DMR and D-Star digital repeater tab"""
        dmr_dstar_frame = ttk.Frame(self.amateur_notebook)
        self.amateur_notebook.add(dmr_dstar_frame, text="DMR/D-Star")

        info_label = ttk.Label(dmr_dstar_frame, text="DMR and D-Star Digital Repeaters",
                              font=(tw_theme.SANS, 16, 'bold'))
        info_label.pack(pady=15)

        # DMR/D-Star data tree - optimized for touch screen
        columns = ('Call', 'Location', 'Output', 'Input', 'Mode', 'CC/ID', 'Dist', 'Bear')
        self.dmr_dstar_tree = ttk.Treeview(dmr_dstar_frame, columns=columns, show='headings', height=15)

        # Configure columns with percentage-based widths
        available_width = 980
        for col in columns:
            # Use short header names for compact display
            header_text = col
            if col == 'Dist':
                header_text = 'Miles'
            elif col == 'Bear':
                header_text = 'Bearing'
            elif col == 'CC/ID':
                header_text = 'CC/ID'
            
            self.dmr_dstar_tree.heading(col, text=header_text)
            
            if col == 'Call':
                width = int(available_width * 0.10)
            elif col == 'Location':
                width = int(available_width * 0.25)
            elif col == 'Output':
                width = int(available_width * 0.12)
            elif col == 'Input':
                width = int(available_width * 0.12)
            elif col == 'Mode':
                width = int(available_width * 0.10)
            elif col == 'CC/ID':
                width = int(available_width * 0.10)
            elif col == 'Dist':
                width = int(available_width * 0.11)
            else:  # Bear
                width = int(available_width * 0.10)
            
            self.dmr_dstar_tree.column(col, width=width, stretch=True)

        self.dmr_dstar_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def create_noaa_weather_tab(self):
        """Create NOAA Weather Radio tab"""
        noaa_frame = ttk.Frame(self.notebook)
        self.notebook.add(noaa_frame, text="NOAA")

        info_label = ttk.Label(noaa_frame, text="NOAA Weather Radio (NWR) Frequencies",
                              font=(tw_theme.SANS, 16, 'bold'))
        info_label.pack(pady=15)

        # Instructions
        instructions = ttk.Label(noaa_frame, 
                                text="These are the 7 NOAA Weather Radio frequencies used nationwide.\n"
                                     "Check which station(s) cover your area at weather.gov/nwr",
                                font=(tw_theme.SANS, 11),
                                justify=tk.CENTER)
        instructions.pack(pady=10)

        # NOAA data tree
        columns = ('Channel', 'Frequency', 'Coverage Area', 'Signal')
        self.noaa_tree = ttk.Treeview(noaa_frame, columns=columns, show='headings', height=10)

        # Define column widths (percentage-based)
        available_width = 980
        for col in columns:
            self.noaa_tree.heading(col, text=col)
            if col == 'Channel':
                width = int(available_width * 0.12)
            elif col == 'Frequency':
                width = int(available_width * 0.18)
            elif col == 'Coverage Area':
                width = int(available_width * 0.55)
            else:  # Signal
                width = int(available_width * 0.15)
            self.noaa_tree.column(col, width=width, stretch=True)

        self.noaa_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def create_amateur_tab(self):
        """Create amateur radio tab with sub-tabs for different bands"""
        amateur_frame = ttk.Frame(self.notebook)
        self.notebook.add(amateur_frame, text="Amateur")

        # Create sub-notebook for amateur bands
        self.amateur_notebook = ttk.Notebook(amateur_frame)
        self.amateur_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create band tabs
        self.create_band_tab("10m", "10 Meters (28-29.7 MHz)")
        self.create_band_tab("6m", "6 Meters (50-54 MHz)")
        self.create_band_tab("2m", "2 Meters (144-148 MHz)")
        self.create_band_tab("1.25m", "1.25 Meters (220-225 MHz)")
        self.create_band_tab("70cm", "70 Centimeters (420-450 MHz)")
        self.create_band_tab("Simplex", "Simplex & Special Frequencies")

    def create_band_tab(self, tab_name, description):
        """Create a tab for a specific amateur radio band"""
        band_frame = ttk.Frame(self.amateur_notebook)
        self.amateur_notebook.add(band_frame, text=tab_name)

        # Band description - larger for touch screens
        desc_label = ttk.Label(band_frame, text=description,
                              font=(tw_theme.SANS, 14, 'bold'))
        desc_label.pack(pady=12)

        # Different columns for Simplex tab
        if tab_name == "Simplex":
            columns = ('Frequency', 'Description', 'Alpha Tag', 'Mode', 'Tone')
        else:
            columns = ('Call Sign', 'Location', 'Output', 'Input', 'Tone', 'Distance', 'Bearing')
        
        band_tree = ttk.Treeview(band_frame, columns=columns, show='headings', height=12)

        # Define column widths (percentage-based)
        available_width = 980
        for col in columns:
            band_tree.heading(col, text=col)
            if tab_name == "Simplex":
                if col == 'Frequency':
                    width = int(available_width * 0.12)
                elif col == 'Description':
                    width = int(available_width * 0.40)
                elif col == 'Alpha Tag':
                    width = int(available_width * 0.18)
                elif col == 'Mode':
                    width = int(available_width * 0.15)
                else:  # Tone
                    width = int(available_width * 0.15)
            else:
                if col == 'Call Sign':
                    width = int(available_width * 0.13)
                elif col == 'Location':
                    width = int(available_width * 0.25)
                elif col == 'Output':
                    width = int(available_width * 0.13)
                elif col == 'Input':
                    width = int(available_width * 0.13)
                elif col == 'Tone':
                    width = int(available_width * 0.12)
                elif col == 'Distance':
                    width = int(available_width * 0.12)
                else:  # Bearing
                    width = int(available_width * 0.12)
            band_tree.column(col, width=width, stretch=True)

        band_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Store tree reference for data population
        band_clean = tab_name
        # Handle special cases for proper attribute names
        if band_clean == "1.25m":
            attr_name = "amateur_125m_tree"
        elif band_clean == "70cm":
            attr_name = "amateur_70cm_tree"
        else:
            attr_name = f'amateur_{band_clean.replace(".", "").lower()}_tree'

        setattr(self, attr_name, band_tree)
        print(f"[OK] Created tree attribute: {attr_name}")

    def load_static_data(self):
        """Load static repeater and frequency data"""
        print("[OK] Loading static amateur radio data...")

        # Load grid display
        self.update_grid_display()
        
        # Load ARMER data
        self.load_armer_data()
        
        # Load interop data
        self.load_interop_data()
        
        # Load aviation data
        self.load_aviation_data()
        
        # Load Skywarn data
        self.load_skywarn_data()

        # Load amateur band data
        self.load_amateur_data()

        # Load simplex data
        self.load_simplex_data()
        
        # Load fusion data (in background thread to avoid blocking on geocoding)
        print("[INFO] Starting Fusion data load in background...")
        threading.Thread(target=self.load_fusion_data, daemon=True).start()

        # Load DMR/D-Star data
        self.load_dmr_dstar_data()

        # Load NOAA Weather Radio data
        self.load_noaa_weather_data()

    def load_interop_data(self):
        """Load interoperability channel data"""
        interop_file = os.path.join(os.path.dirname(__file__), "data/interoperability.csv")
        
        # Clear existing data
        for item in self.interop_tree.get_children():
            self.interop_tree.delete(item)
        
        if not os.path.exists(interop_file):
            print(f"[WARN] Interop file not found: {interop_file}")
            return
            
        try:
            with open(interop_file, 'r') as f:
                reader = csv.DictReader(f)
                count = 0
                for row in reader:
                    freq_output = row.get('Frequency Output', '0')
                    if float(freq_output) == 0:
                        continue
                    
                    # Determine category from tag or description
                    tag = row.get('Tag', '')
                    description = row.get('Description', '').lower()
                    alpha_tag = row.get('Alpha Tag', '').lower()
                    
                    # Skip Ham and Data frequencies - they don't belong in Interoperability table
                    if 'Ham' in tag or 'Data' in tag:
                        continue
                    
                    # Skip aviation frequencies - they belong in Aviation tab
                    if any(keyword in description or keyword in alpha_tag 
                           for keyword in ['air-air', 'air-ground', 'tanker', 'guard', 'aviation']):
                        continue
                    
                    if 'Emergency' in tag:
                        category = 'Emergency'
                    elif 'Interop' in tag:
                        category = 'Interop'
                    elif 'Hospital' in tag:
                        category = 'Hospital'
                    elif 'Federal' in tag:
                        category = 'Federal'
                    else:
                        category = 'Other'
                    
                    values = (
                        f"{freq_output} MHz",
                        description,
                        row.get('Alpha Tag', ''),
                        row.get('Mode', ''),
                        category
                    )
                    self.interop_tree.insert('', 'end', values=values)
                    count += 1
                    
            print(f"[OK] Loaded {count} interoperability channels")
        except Exception as e:
            print(f"[ERROR] Error loading interop data: {e}")

    def load_aviation_data(self):
        """Load aviation frequency data - dynamically fetches nearby airports based on GPS"""
        # Clear existing data from all aviation sub-tabs
        for tree in [self.aviation_nearby_tree, self.aviation_emergency_tree, 
                     self.aviation_common_tree, self.aviation_center_tree]:
            for item in tree.get_children():
                tree.delete(item)
        
        # === Load Emergency Aviation Frequencies ===
        interop_file = os.path.join(os.path.dirname(__file__), "data/interoperability.csv")
        if os.path.exists(interop_file):
            try:
                with open(interop_file, 'r') as f:
                    reader = csv.DictReader(f)
                    emergency_count = 0
                    for row in reader:
                        freq_output = row.get('Frequency Output', '0')
                        if float(freq_output) == 0:
                            continue
                        
                        description = row.get('Description', '').lower()
                        alpha_tag = row.get('Alpha Tag', '').lower()
                        tag = row.get('Tag', '')
                        
                        # Only include aviation-related frequencies
                        is_aviation = any(keyword in description or keyword in alpha_tag 
                                         for keyword in ['air-air', 'air-ground', 'tanker', 'guard', 'aviation'])
                        
                        if not is_aviation:
                            continue
                        
                        # Determine category
                        if 'Emergency' in tag:
                            category = 'Emergency Ops'
                        elif 'Federal' in tag:
                            category = 'Federal'
                        else:
                            category = 'Aviation'
                        
                        values = (
                            f"{freq_output} MHz",
                            row.get('Description', ''),
                            row.get('Alpha Tag', ''),
                            row.get('Mode', ''),
                            category
                        )
                        self.aviation_emergency_tree.insert('', 'end', values=values)
                        emergency_count += 1
                        
                print(f"[OK] Loaded {emergency_count} emergency aviation frequencies")
            except Exception as e:
                print(f"[ERROR] Error loading emergency aviation data: {e}")
        
        # === Load Common Aviation Frequencies ===
        common_freqs = [
            ("121.5", "Emergency (Guard)", "GUARD", "AM", "Emergency"),
            ("243.0", "Military Emergency", "MIL GUARD", "AM", "Emergency"),
            ("122.75", "Air-to-Air (Fixed Wing)", "Air-to-Air", "AM", "Common"),
            ("123.45", "Air-to-Air (Helicopter)", "Helo Air-Air", "AM", "Common"),
            ("122.9", "Multicom (CTAF)", "Multicom", "AM", "Common"),
            ("121.5", "Ground/Multicom", "Ground", "AM", "Common"),
        ]
        
        for freq, desc, tag, mode, cat in common_freqs:
            values = (f"{freq} MHz", desc, tag, mode, cat)
            self.aviation_common_tree.insert('', 'end', values=values)
        print(f"[OK] Loaded {len(common_freqs)} common aviation frequencies")
        
        # === Load Center/Approach Frequencies ===
        center_freqs = [
            ("123.6", "Minneapolis Center", "MSP Center", "AM", "Center"),
            ("127.85", "Minneapolis Center (High)", "MSP Center HI", "AM", "Center"),
            ("132.4", "Minneapolis Center (Low)", "MSP Center LO", "AM", "Center"),
        ]
        
        for freq, desc, tag, mode, cat in center_freqs:
            values = (f"{freq} MHz", desc, tag, mode, cat)
            self.aviation_center_tree.insert('', 'end', values=values)
        print(f"[OK] Loaded {len(center_freqs)} center/approach frequencies")
        
        # === Fetch Nearby Airports Based on GPS ===
        print(f"[INFO] Fetching airports near {self.last_lat:.4f}, {self.last_lon:.4f}...")
        nearby_airports = self.get_nearby_airports(self.last_lat, self.last_lon, radius_nm=100)
        
        if nearby_airports:
            airport_count = 0
            for airport in nearby_airports[:10]:  # Limit to 10 nearest airports
                airport_code = airport.get('code', '')
                distance_nm = airport.get('distance_nm', 0)
                distance_mi = airport.get('distance_mi', 0)
                bearing = airport.get('bearing', 0)
                
                # Insert airport as parent node (collapsible)
                airport_name = f"{airport_code} ({distance_nm:.1f}nm / {distance_mi:.1f}mi @ {bearing:.0f}°)"
                airport_node = self.aviation_nearby_tree.insert(
                    '', 'end',
                    text=airport_name,
                    values=('', '', '', '', 'Airport'),
                    tags=('airport',)
                )
                
                # Add all frequencies as children of this airport
                freq_count = 0
                for freq_data in airport.get('frequencies', []):
                    freq = freq_data.get('freq', '0')
                    if float(freq) == 0:
                        continue
                    
                    service = freq_data.get('service', 'Airport')
                    values = (
                        f"{freq} MHz",
                        freq_data.get('description', ''),
                        freq_data.get('alpha_tag', ''),
                        freq_data.get('mode', ''),
                        service
                    )
                    self.aviation_nearby_tree.insert(
                        airport_node, 'end',
                        text=f"  {service}",
                        values=values,
                        tags=('frequency',)
                    )
                    freq_count += 1
                    airport_count += 1
                
                # Start with airports collapsed; user can click to expand.
                self.aviation_nearby_tree.item(airport_node, open=False)
            
            print(f"[OK] Loaded {airport_count} frequencies from {len(nearby_airports[:10])} nearby airports")
        else:
            # No nearby airports - add informational message
            self.aviation_nearby_tree.insert(
                '', 'end',
                text="No airports within 100nm",
                values=('', 'No airports found within 100nm of current position', '', '', 'Info'),
                tags=('info',)
            )
            print(f"[INFO] No nearby airports found")
        
        print(f"[OK] Aviation data loaded across all sub-tabs")

    def load_local_skywarn_csv(self):
        """Load local Skywarn/ARES/emergency repeater data from CSV files"""
        # Primary source: dedicated sky_warn.csv file
        sky_warn_file = os.path.join(os.path.dirname(__file__), 'data/sky_warn.csv')
        
        # Minnesota county coordinates (approximate center points)
        county_coords = {
            'aitkin': (46.5333, -93.7133),
            'anoka': (45.2697, -93.2425),
            'becker': (46.9294, -95.8061),
            'beltrami': (47.7661, -94.9294),
            'benton': (45.7036, -94.1303),
            'big stone': (45.5497, -96.4594),
            'blue earth': (44.0275, -94.1019),
            'brown': (44.2547, -94.7133),
            'carlton': (46.6661, -92.7258),
            'carver': (44.8233, -93.8008),
            'cass': (46.8992, -94.3378),
            'chippewa': (45.0125, -95.5372),
            'chisago': (45.4869, -92.8897),
            'clay': (46.8844, -96.5111),
            'clearwater': (47.5736, -95.3994),
            'cook': (47.8183, -90.5497),
            'cottonwood': (43.9858, -95.1686),
            'crow wing': (46.4992, -94.0839),
            'dakota': (44.6697, -93.0633),
            'dodge': (44.0178, -92.8569),
            'douglas': (45.9383, -95.4372),
            'faribault': (43.6572, -93.9478),
            'fillmore': (43.6700, -92.0886),
            'freeborn': (43.6733, -93.3628),
            'goodhue': (44.4394, -92.7258),
            'grant': (45.9333, -96.1133),
            'hennepin': (45.0069, -93.4828),
            'houston': (43.5950, -91.4219),
            'hubbard': (47.1236, -94.9186),
            'isanti': (45.5486, -93.2775),
            'itasca': (47.5511, -93.4828),
            'jackson': (43.6500, -95.1686),
            'kanabec': (45.9358, -93.2686),
            'kandiyohi': (45.1331, -94.9186),
            'kittson': (48.7767, -96.8361),
            'koochiching': (48.3903, -93.6736),
            'lac qui parle': (45.0119, -96.1750),
            'lake': (47.5328, -91.3731),
            'lake of the woods': (48.6950, -94.8358),
            'le sueur': (44.3761, -93.7222),
            'lincoln': (44.4261, -96.2647),
            'lyon': (44.4261, -95.8969),
            'mahnomen': (47.3200, -95.8250),
            'marshall': (48.3989, -96.2647),
            'martin': (43.6586, -94.5572),
            'mcleod': (44.7869, -94.2508),
            'meeker': (45.1197, -94.5572),
            'mille lacs': (45.9419, -93.6386),
            'morrison': (45.9700, -94.2508),
            'mower': (43.6622, -92.7436),
            'murray': (44.0000, -95.7219),
            'nicollet': (44.3436, -94.2508),
            'nobles': (43.6606, -95.7864),
            'norman': (47.3197, -96.5111),
            'olmsted': (43.9072, -92.4600),
            'otter tail': (46.4086, -95.7219),
            'pennington': (47.9967, -96.1133),
            'pine': (46.1378, -92.7258),
            'pipestone': (44.0000, -96.3292),
            'polk': (47.7700, -96.2003),
            'pope': (45.5919, -95.4372),
            'ramsey': (45.0158, -93.1000),
            'red lake': (47.8772, -96.0489),
            'redwood': (44.5483, -95.1686),
            'renville': (44.7197, -95.2331),
            'rice': (44.3486, -93.2686),
            'rock': (43.6550, -96.2647),
            'roseau': (48.8467, -95.7864),
            'scott': (44.6508, -93.5428),
            'sherburne': (45.4422, -93.7781),
            'sibley': (44.5569, -94.2508),
            'st louis': (47.4231, -92.3769),
            'stearns': (45.5569, -94.6400),
            'steele': (43.9572, -93.2686),
            'stevens': (45.5919, -96.0489),
            'swift': (45.2814, -95.7219),
            'todd': (46.0608, -94.8828),
            'traverse': (45.7683, -96.4594),
            'wabasha': (44.2858, -92.0886),
            'wadena': (46.4419, -95.1331),
            'waseca': (44.0000, -93.5428),
            'washington': (45.0508, -92.9033),
            'watonwan': (43.9858, -94.6400),
            'wilkin': (46.3600, -96.5755),
            'winona': (43.9936, -91.6828),
            'wright': (45.1736, -93.9650),
            'yellow medicine': (44.7125, -95.8969)
        }
        
        all_skywarn = []
        
        # Load dedicated sky_warn.csv file
        if os.path.exists(sky_warn_file):
            try:
                with open(sky_warn_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        try:
                            output_freq = float(row.get('Output Freq', '0'))
                            if output_freq == 0:
                                continue
                            
                            # Get tone (prefer Downlink/Output Tone)
                            tone_str = row.get('Downlink Tone', row.get('Uplink Tone', '')).strip()
                            if not tone_str or tone_str.startswith('D'):
                                tone = 'CSQ'
                            else:
                                tone = tone_str
                            
                            # Get county and lookup coordinates
                            county = row.get('County', '').strip().lower()
                            location_name = row.get('Location', 'Unknown').strip()
                            
                            # Get coordinates from county
                            lat, lon = county_coords.get(county, (46.450, -94.150))  # Default to central MN
                            
                            repeater = {
                                'call': row.get('Call', 'N0CALL').strip(),
                                'location': f"{location_name}, {county.title()}",
                                'freq': f"{output_freq:.4f}",
                                'tone': tone,
                                'lat': lat,
                                'lon': lon
                            }
                            all_skywarn.append(repeater)
                            
                        except (ValueError, KeyError) as e:
                            continue
                
                if all_skywarn:
                    print(f"[OK] Loaded {len(all_skywarn)} Skywarn repeaters from sky_warn.csv")
                    return all_skywarn
                    
            except Exception as e:
                print(f"[WARN] Error loading sky_warn.csv: {e}")
        
        # Fallback: try loading from county radio reference files
        repeater_files = [
            'data/crow_wing_county_radio_reference.csv',
            'data/cass_county_radio_reference.csv',
        ]
        
        for csv_file in repeater_files:
            file_path = os.path.join(os.path.dirname(__file__), csv_file)
            if not os.path.exists(file_path):
                continue
                
            try:
                with open(file_path, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Look for amateur radio entries with ARES/SKYWARN/emergency keywords
                        category = row.get('Agency/Category', '').lower()
                        description = row.get('Description', '').lower()
                        tag = row.get('Tag', '').lower()
                        
                        is_amateur = 'amateur' in category or 'ham' in tag
                        is_emergency = any(keyword in description or keyword in category 
                                         for keyword in ['ares', 'skywarn', 'races', 'emergency', 'net'])
                        
                        if is_amateur and is_emergency:
                            try:
                                output_freq = float(row.get('Frequency Output', '0'))
                                
                                if output_freq == 0:
                                    continue
                                
                                # Extract tone
                                tone_str = row.get('PL Input Tone', row.get('PL Output Tone', 'CSQ'))
                                tone = tone_str.replace(' PL', '').replace('CSQ', '0.0')
                                
                                # Location
                                location_name = row.get('Description', 'Unknown')
                                if 'brainerd' in location_name.lower():
                                    lat, lon = 46.358, -94.201
                                elif 'crosslake' in location_name.lower():
                                    lat, lon = 46.660, -94.107
                                elif 'pequot' in location_name.lower():
                                    lat, lon = 46.603, -94.312
                                else:
                                    lat, lon = 46.450, -94.150
                                
                                repeater = {
                                    'call': row.get('FCC Callsign', 'N0CALL'),
                                    'location': location_name,
                                    'freq': f"{output_freq:.4f}",
                                    'tone': tone,
                                    'lat': lat,
                                    'lon': lon
                                }
                                all_skywarn.append(repeater)
                                
                            except (ValueError, KeyError):
                                continue
                
                if all_skywarn:
                    print(f"[OK] Loaded {len(all_skywarn)} Skywarn/ARES repeaters from {csv_file}")
                    
            except Exception as e:
                print(f"[WARN] Error loading {csv_file}: {e}")
        
        return all_skywarn

    def load_amateur_data(self):
        """Load amateur radio repeater data.

        Two sources, neither of them required: the repeater CSVs if any
        are on disk, and the rows tagged Ham of whatever RadioReference
        county exports have been imported. A county export is the one
        most likely to be there, because it is the file the Import button
        takes and the website hands out per county.
        """
        local_repeaters = list(self.load_local_repeater_csv())
        from_county = self.county_amateur_repeaters()
        if from_county:
            print(f"[OK] {len(from_county)} amateur repeaters from imported "
                  f"county frequencies")
        local_repeaters += from_county

        if local_repeaters:
            print(f"[OK] {len(local_repeaters)} amateur repeaters to place "
                  f"on the band tabs")
            # Separate by band
            repeaters_10m = [r for r in local_repeaters if 28 <= float(r.get('output', '0')) <= 30]
            repeaters_6m = [r for r in local_repeaters if 50 <= float(r.get('output', '0')) <= 54]
            repeaters_2m = [r for r in local_repeaters if 144 <= float(r.get('output', '0')) <= 148]
            repeaters_125m = [r for r in local_repeaters if 220 <= float(r.get('output', '0')) <= 225]
            repeaters_70cm = [r for r in local_repeaters if 420 <= float(r.get('output', '0')) <= 450]
            repeaters_23cm = [r for r in local_repeaters if 1240 <= float(r.get('output', '0')) <= 1300]
            
            # Populate band trees
            if repeaters_10m:
                self.populate_band_tree(repeaters_10m, '10m')
            if repeaters_6m:
                self.populate_band_tree(repeaters_6m, '6m')
            if repeaters_2m:
                self.populate_band_tree(repeaters_2m, '2m')
            if repeaters_125m:
                self.populate_band_tree(repeaters_125m, '1.25m')
            if repeaters_70cm:
                self.populate_band_tree(repeaters_70cm, '70cm')
        else:
            # There used to be five invented repeaters here - metro
            # machines with real callsigns pinned to towns they are not
            # in - shown whenever the CSVs were missing, which was
            # always. A placeholder that looks exactly like data is
            # worse than an empty tab: nobody thinks to check a list
            # that is already full, and a ham who trusts it keys up into
            # nothing. An empty band now reads as empty.
            print("[INFO] no amateur repeaters on hand - Import a county CSV "
                  "from RadioReference, or put a repeater CSV in data/")
            for band in ('10m', '6m', '2m', '1.25m', '70cm'):
                self.populate_band_tree([], band)

    def town_position(self, place):
        """Where a named place is, or (None, None) if we have no idea.

        A RadioReference county export describes a repeater by the town
        it serves and never by position, so the description is matched
        against the town table. Longest match first: "Crosslake" must not
        be answered by "Cross" or a shorter town sitting inside it.
        """
        if not place:
            return None, None
        haystack = place.lower()
        best = None
        for town, coords in MN_TOWNS.items():
            if town in haystack and (best is None or len(town) > len(best[0])):
                best = (town, coords)
        return best[1] if best else (None, None)

    def county_amateur_repeaters(self):
        """The Ham rows of every imported county, shaped for a band tab.

        The tone given is the input tone - the one you have to send to
        open the machine - falling back to the output tone when there is
        no input. A repeater whose town is not in the table is still
        listed; it simply cannot say how far away it is.
        """
        try:
            records = frequency_store.frequencies(COUNTY_JSON, tag="Ham")
        except Exception as exc:     # a bad store must not empty the tab
            print(f"[WARN] county frequencies could not be read: {exc}")
            return []

        out, unplaced = [], []
        for record in records:
            output_hz = record.get("output_hz")
            if not output_hz:
                continue
            description = (record.get("description") or "").strip()
            lat, lon = self.town_position(description)
            if lat is None:
                unplaced.append(description or "(unnamed)")
            input_hz = record.get("input_hz")
            tone = record.get("tone_in") or record.get("tone_out") or {}
            out.append({
                'call': (record.get("callsign") or "").strip() or "",
                'location': description or (record.get("alpha_tag") or ""),
                'output': f"{output_hz / 1e6:.4f}",
                'input': f"{input_hz / 1e6:.4f}" if input_hz else "",
                'tone': (f"{tone['hz']:.1f}" if tone.get("kind") == "ctcss"
                         else tone.get("text", "")),
                'lat': lat,
                'lon': lon,
            })
        if unplaced:
            print(f"[INFO] {len(unplaced)} amateur repeaters have no town in "
                  f"the table, listed without a distance: "
                  f"{', '.join(sorted(set(unplaced))[:4])}")
        return out

    def load_local_repeater_csv(self):
        """Load local repeater data from CSV files"""
        # Known Minnesota city/town coordinates (expanded statewide coverage)
        known_locations = MN_TOWNS
        
        repeater_files = [
            'data/repeaterbook.csv',             # whatever came in through Import
            'data/Repeater_Book_Minnesota.csv',  # Primary statewide source
            'data/crow_wing_county_radio_reference.csv',
            'data/cass_county_radio_reference.csv',
        ]
        
        all_repeaters = []
        
        for csv_file in repeater_files:
            file_path = os.path.join(os.path.dirname(__file__), csv_file)
            if not os.path.exists(file_path):
                continue
                
            try:
                with open(file_path, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Detect file format and extract data accordingly
                        if 'Output Freq' in row:
                            # Repeater Book format
                            try:
                                output_freq = float(row.get('Output Freq', '0'))
                                input_freq = float(row.get('Input Freq', '0'))
                                
                                if output_freq == 0:
                                    continue
                                
                                callsign = row.get('Call', 'N0CALL').strip()
                                location_name = row.get('Location', 'Unknown').strip()
                                county = row.get('County', '').strip().lower()
                                state = row.get('State', '').strip().lower()
                                # A RepeaterBook export is whatever was asked
                                # of it, and the national one is mostly not
                                # Minnesota. The town and county tables below
                                # are Minnesota's, and county names repeat
                                # across states - Polk, Washington and Lake
                                # are each several places. Placing an out of
                                # state row from them puts a Texas machine in
                                # Minnesota, so those rows are carried without
                                # a position rather than with a wrong one.
                                in_minnesota = state in ('', 'minnesota', 'mn')
                                
                                # Extract tone
                                uplink_tone = row.get('Uplink Tone', '').strip()
                                downlink_tone = row.get('Downlink Tone', '').strip()
                                tone = uplink_tone or downlink_tone or 'CSQ'
                                if tone and tone != 'CSQ':
                                    tone = tone.replace('D', '').replace('d', '')  # Remove D-code prefix
                                
                                # Find coordinates using location matching
                                lat, lon = None, None
                                location_lower = location_name.lower()
                                
                                # Try exact city match
                                if in_minnesota:
                                    for city_key, coords in known_locations.items():
                                        if city_key in location_lower:
                                            lat, lon = coords
                                            break
                                
                                # Fallback to county center
                                if lat is None and county and in_minnesota:
                                    county_centers = {
                                        'crow wing': (46.450, -94.150), 'cass': (46.900, -94.350),
                                        'aitkin': (46.533, -93.717), 'hennepin': (44.977, -93.265),
                                        'ramsey': (45.015, -93.100), 'dakota': (44.668, -93.065),
                                        'anoka': (45.270, -93.242), 'washington': (45.050, -92.910),
                                        'st louis': (47.350, -92.450), 'stearns': (45.558, -94.612),
                                        'olmsted': (44.022, -92.468), 'winona': (44.050, -91.639),
                                        'goodhue': (44.500, -92.750), 'rice': (44.350, -93.300),
                                        'steele': (44.000, -93.230), 'dodge': (44.020, -92.850),
                                        'mower': (43.667, -92.750), 'fillmore': (43.667, -92.083),
                                        'houston': (43.617, -91.400), 'blue earth': (44.000, -94.100),
                                        'nicollet': (44.333, -94.250), 'le sueur': (44.450, -93.650),
                                        'waseca': (44.083, -93.500), 'faribault': (43.667, -93.950),
                                        'martin': (43.667, -94.583), 'jackson': (43.650, -95.167),
                                        'nobles': (43.650, -95.750), 'rock': (43.650, -96.333),
                                        'pipestone': (44.000, -96.317), 'murray': (44.000, -95.750),
                                        'cottonwood': (44.000, -95.150), 'watonwan': (43.983, -94.600),
                                        'brown': (44.250, -94.717), 'redwood': (44.550, -95.150),
                                        'lyon': (44.417, -95.900), 'lincoln': (44.450, -96.267),
                                        'chippewa': (45.000, -95.533), 'yellow medicine': (44.717, -95.917),
                                        'lac qui parle': (45.000, -96.167), 'swift': (45.283, -95.650),
                                        'kandiyohi': (45.167, -94.983), 'meeker': (45.083, -94.533),
                                        'mcleod': (44.833, -94.267), 'sibley': (44.583, -94.217),
                                        'scott': (44.660, -93.470), 'carver': (44.807, -93.798),
                                        'wright': (45.168, -93.965), 'sherburne': (45.440, -93.767),
                                        'isanti': (45.487, -93.247), 'chisago': (45.458, -92.891),
                                        'pine': (46.083, -92.783), 'kanabec': (45.950, -93.300),
                                        'mille lacs': (46.017, -93.650), 'benton': (45.700, -94.000),
                                        'morrison': (46.017, -94.317), 'todd': (46.167, -94.933),
                                        'wadena': (46.433, -95.000), 'otter tail': (46.417, -95.700),
                                        'douglas': (45.933, -95.433), 'stevens': (45.567, -96.000),
                                        'traverse': (45.767, -96.517), 'big stone': (45.467, -96.433),
                                        'wilkin': (46.350, -96.500), 'clay': (46.900, -96.450),
                                        'norman': (47.317, -96.367), 'mahnomen': (47.317, -95.867),
                                        'polk': (47.783, -96.183), 'red lake': (47.867, -96.050),
                                        'pennington': (48.117, -96.050), 'marshall': (48.400, -96.200),
                                        'kittson': (48.767, -96.833), 'roseau': (48.833, -95.767),
                                        'lake of the woods': (48.633, -94.867), 'koochiching': (48.267, -93.683),
                                        'beltrami': (47.717, -94.917), 'clearwater': (47.583, -95.367),
                                        'hubbard': (47.017, -94.917), 'itasca': (47.500, -93.500),
                                        'carlton': (46.583, -92.633), 'lake': (47.517, -91.183),
                                        'cook': (47.800, -90.667), 'wabasha': (44.383, -92.033),
                                        'freeborn': (43.650, -93.350), 'becker': (46.850, -95.717),
                                    }
                                    if county in county_centers:
                                        lat, lon = county_centers[county]
                                
                                # No coordinates is an answer. It used to
                                # default to central Minnesota, which put every
                                # unplaceable repeater in Brainerd - a made up
                                # position reads as a real one on a bearing.
                                # The band tab lists these without a distance.
                                
                                repeater = {
                                    'call': callsign,
                                    'location': location_name,
                                    'output': f"{output_freq:.4f}",
                                    'input': f"{input_freq:.4f}" if input_freq > 0 else f"{output_freq:.4f}",
                                    'tone': tone,
                                    'lat': lat,
                                    'lon': lon
                                }
                                all_repeaters.append(repeater)
                                
                            except (ValueError, KeyError) as e:
                                continue
                        
                        else:
                            # Radio Reference county format
                            category = row.get('Agency/Category', '').lower()
                            tag = row.get('Tag', '').lower()
                            
                            if 'amateur' in category or 'ham' in tag:
                                try:
                                    output_freq = float(row.get('Frequency Output', '0'))
                                    input_freq = float(row.get('Frequency Input', '0'))
                                    
                                    # Skip non-repeater frequencies
                                    if output_freq == 0 or input_freq == 0:
                                        continue
                                    
                                    # Extract tone (handle various formats)
                                    tone_str = row.get('PL Input Tone', row.get('PL Output Tone', 'CSQ'))
                                    tone = tone_str.replace(' PL', '').replace('CSQ', '0.0')
                                    
                                    # Find location coordinates
                                    location_name = row.get('Description', 'Unknown')
                                    lat, lon = None, None
                                    location_lower = location_name.lower()
                                    
                                    # Try known locations match
                                    for city_key, coords in known_locations.items():
                                        if city_key in location_lower:
                                            lat, lon = coords
                                            break
                                    
                                    # Fallback to Crow Wing County if no match
                                    if lat is None:
                                        lat, lon = 46.450, -94.150
                                    
                                    repeater = {
                                        'call': row.get('FCC Callsign', 'N0CALL'),
                                        'location': location_name,
                                        'output': f"{output_freq:.4f}",
                                        'input': f"{input_freq:.4f}",
                                        'tone': tone,
                                        'lat': lat,
                                        'lon': lon
                                    }
                                    all_repeaters.append(repeater)
                                    
                                except (ValueError, KeyError) as e:
                                    continue
                
                if all_repeaters:
                    print(f"[OK] Loaded {len(all_repeaters)} amateur repeaters from {csv_file}")
                    
            except Exception as e:
                print(f"[WARN] Error loading {csv_file}: {e}")
        
        return all_repeaters

    def determine_band(self, frequency):
        """Determine amateur band from frequency (in MHz)"""
        freq = float(frequency)
        if 50 <= freq <= 54:
            return '6m'
        elif 144 <= freq <= 148:
            return '2m'
        elif 222 <= freq <= 225:
            return '1.25m'
        elif 420 <= freq <= 450:
            return '70cm'
        elif 902 <= freq <= 928:
            return '33cm'
        elif 1240 <= freq <= 1300:
            return '23cm'
        else:
            return None

    @staticmethod
    def _mhz(value, blank="—"):
        """A frequency for a column, or a word when there is not one.

        An output frequency is always a number. An input is not: a
        simplex channel has none, and rendering the nothing as
        "0.0000 MHz" puts a frequency at the bottom of the spectrum on
        screen and invites somebody to transmit on it.
        """
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value).strip() or blank
        return f"{number:.4f} MHz" if number else blank

    @staticmethod
    def _tone_text(value):
        """A tone for a column. CSQ is not a number of hertz, and
        labelling it as one reads as a tone somebody should be sending."""
        text = str(value or "").strip()
        if not text:
            return "CSQ"
        try:
            hz = float(text)
        except ValueError:
            return text                  # CSQ, a DCS code, whatever it was
        return f"{hz:.1f} Hz" if hz else "CSQ"

    def populate_band_tree(self, repeaters, band):
        """Populate a specific band tree with repeater data"""
        # Fix band naming to match our attribute names
        if band == "1.25m":
            tree_name = 'amateur_125m_tree'
        elif band == "70cm":
            tree_name = 'amateur_70cm_tree'
        else:
            tree_name = f'amateur_{band}_tree'

        if hasattr(self, tree_name):
            tree = getattr(self, tree_name)

            # Clear existing data
            for item in tree.get_children():
                tree.delete(item)

            # Calculate distances and sort by proximity
            # A repeater whose town is not in the table still belongs on
            # the list - it is audible or it is not, and that does not
            # depend on our being able to measure it. It sorts to the end
            # and leaves the distance blank rather than claiming a zero.
            repeater_distances = []
            for repeater in repeaters:
                if repeater.get("lat") is None or repeater.get("lon") is None:
                    repeater_distances.append((float("inf"), repeater))
                    continue
                distance = self.calculate_distance(self.last_lat, self.last_lon,
                                                 repeater["lat"], repeater["lon"])
                repeater_distances.append((distance, repeater))

            # Nearest first, and all of them. It used to show the
            # closest seven, which is a filter that cannot be seen from
            # the screen: a band with forty repeaters on it looked
            # exactly like a band with seven. The tree scrolls.
            repeater_distances.sort(key=lambda x: x[0])

            # Populate with repeater data
            for distance, repeater in repeater_distances:
                if distance == float("inf"):
                    how_far, heading = "—", "—"
                else:
                    bearing = self.calculate_bearing(self.last_lat, self.last_lon,
                                                   repeater["lat"], repeater["lon"])
                    how_far = f"{distance:.1f} mi"
                    heading = f"{bearing:.0f}°"

                values = (
                    repeater["call"],
                    repeater["location"],
                    self._mhz(repeater.get("output")),
                    self._mhz(repeater.get("input"), blank="simplex"),
                    self._tone_text(repeater.get("tone")),
                    how_far,
                    heading,
                )

                tree.insert('', 'end', values=values)
            placed = sum(1 for d, _ in repeater_distances if d != float("inf"))
            print(f"[OK] Populated {band} with {len(repeater_distances)} "
                  f"repeaters"
                  + (f", {len(repeater_distances) - placed} without a position"
                     if placed != len(repeater_distances) else ""))
        else:
            print(f"[WARN] Tree {tree_name} not found for band {band}")

    def load_skywarn_data(self):
        """Load Skywarn repeater data"""
        # Try to load from local CSV first
        local_skywarn = self.load_local_skywarn_csv()
        
        if local_skywarn:
            print(f"[OK] Using {len(local_skywarn)} local Skywarn/ARES repeaters from CSV")
            # Clear existing data
            for item in self.skywarn_tree.get_children():
                self.skywarn_tree.delete(item)

            # Calculate distances and sort by proximity
            repeater_distances = []
            for repeater in local_skywarn:
                distance = self.calculate_distance(self.last_lat, self.last_lon,
                                                 repeater["lat"], repeater["lon"])
                repeater_distances.append((distance, repeater))
            
            # Sort by distance and take closest 7
            repeater_distances.sort(key=lambda x: x[0])
            
            # Populate tree with distance calculations
            for distance, repeater in repeater_distances[:7]:
                bearing = self.calculate_bearing(self.last_lat, self.last_lon,
                                               repeater["lat"], repeater["lon"])

                values = (
                    repeater["call"],
                    repeater["location"],
                    f"{repeater['freq']} MHz",
                    f"{repeater['tone']} Hz",
                    f"{distance:.1f} mi",
                    f"{bearing:.0f}°"
                )

                item = self.skywarn_tree.insert('', 'end', values=values)

                # Color code by distance
                if distance < 25:
                    self.skywarn_tree.set(item, 'Call Sign', f"[NEAR] {repeater['call']}")
                elif distance < 75:
                    self.skywarn_tree.set(item, 'Call Sign', f"[MID] {repeater['call']}")
                else:
                    self.skywarn_tree.set(item, 'Call Sign', f"[FAR] {repeater['call']}")
            return
        
        # Fall back to hardcoded Skywarn repeaters
        skywarn_repeaters = [
            {"call": "W0EAR", "location": "Minneapolis ARES", "freq": "146.94", "tone": "114.8", "lat": 44.9778, "lon": -93.2650},
            {"call": "WB0CMZ", "location": "Ramsey County ARES", "freq": "145.43", "tone": "123.0", "lat": 44.9537, "lon": -93.0900},
            {"call": "KC0YHH", "location": "Anoka County ARES", "freq": "145.45", "tone": "131.8", "lat": 45.1975, "lon": -93.3063},
            {"call": "W0MSP", "location": "MSP Emergency Coord", "freq": "147.42", "tone": "100.0", "lat": 44.8848, "lon": -93.2223},
            {"call": "K0USC", "location": "Duluth SKYWARN", "freq": "146.76", "tone": "131.8", "lat": 46.7867, "lon": -92.1005},
        ]

        # Clear existing data
        for item in self.skywarn_tree.get_children():
            self.skywarn_tree.delete(item)

        # Calculate distances and sort by proximity
        repeater_distances = []
        for repeater in skywarn_repeaters:
            distance = self.calculate_distance(self.last_lat, self.last_lon,
                                             repeater["lat"], repeater["lon"])
            repeater_distances.append((distance, repeater))
        
        # Sort by distance and take closest 7
        repeater_distances.sort(key=lambda x: x[0])
        
        # Populate tree with distance calculations
        for distance, repeater in repeater_distances[:7]:
            # Distance already calculated in sort
            bearing = self.calculate_bearing(self.last_lat, self.last_lon,
                                           repeater["lat"], repeater["lon"])

            values = (
                repeater["call"],
                repeater["location"],
                f"{repeater['freq']} MHz",
                f"{repeater['tone']} Hz",
                f"{distance:.1f} mi",
                f"{bearing:.0f}°"
            )

            item = self.skywarn_tree.insert('', 'end', values=values)

            # Color code by distance (using text indicators for compatibility)
            if distance < 25:
                self.skywarn_tree.set(item, 'Call Sign', f"[NEAR] {repeater['call']}")
            elif distance < 75:
                self.skywarn_tree.set(item, 'Call Sign', f"[MID] {repeater['call']}")
            else:
                self.skywarn_tree.set(item, 'Call Sign', f"[FAR] {repeater['call']}")

    def build_repeater_coordinate_cache(self):
        """Build a cache of repeater coordinates from existing amateur data
        
        Handles club callsigns with multiple towers at different locations by:
        - Primary key: frequency (most specific, unique per repeater)
        - Secondary key: callsign + location (for cross-mode matching)
        - Location name cache for geocoding assistance
        """
        cache = {}
        location_cache = {}  # Track known location coordinates
        
        # Known locations with coordinates
        known_locations = {
            'brainerd': (46.358, -94.201),
            'crosslake': (46.660, -94.107),
            'pequot': (46.603, -94.312),
            'crosby': (46.484, -93.957),
            'nisswa': (46.521, -94.289),
            'baxter': (46.345, -94.263),
            'aitkin': (46.533, -93.717),
            'pine river': (46.718, -94.397),
            'pillager': (46.344, -94.482),
        }
        
        # Load from local repeater CSV files
        repeater_files = [
            'data/crow_wing_county_radio_reference.csv',
            'data/cass_county_radio_reference.csv',
        ]
        
        for csv_file in repeater_files:
            file_path = os.path.join(os.path.dirname(__file__), csv_file)
            if not os.path.exists(file_path):
                continue
                
            try:
                with open(file_path, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        category = row.get('Agency/Category', '').lower()
                        tag = row.get('Tag', '').lower()
                        
                        if 'amateur' in category or 'ham' in tag:
                            try:
                                call = row.get('FCC Callsign', '').strip()
                                output_freq = row.get('Frequency Output', '0')
                                location_name = row.get('Description', 'Unknown').lower()
                                
                                # Match location to known coordinates
                                lat, lon = None, None
                                for loc_key, coords in known_locations.items():
                                    if loc_key in location_name:
                                        lat, lon = coords
                                        break
                                
                                # Fallback to central Crow Wing County
                                if lat is None:
                                    lat, lon = 46.450, -94.150
                                
                                # Cache by frequency (PRIMARY - most specific)
                                if output_freq and float(output_freq) > 0:
                                    freq_key = f"{float(output_freq):.3f}"
                                    cache[freq_key] = (lat, lon)
                                
                                # Cache by callsign + location for multi-site clubs
                                if call and location_name:
                                    # Extract key location word
                                    for loc_key in known_locations.keys():
                                        if loc_key in location_name:
                                            composite_key = f"{call}:{loc_key}"
                                            cache[composite_key] = (lat, lon)
                                            break
                                
                                # Build location name cache for geocoding assistance
                                for loc_key in known_locations.keys():
                                    if loc_key in location_name:
                                        location_cache[loc_key] = (lat, lon)
                                        break
                                    
                            except (ValueError, KeyError):
                                continue
            except Exception as e:
                print(f"[WARN] Error building coordinate cache from {csv_file}: {e}")
        
        # Store location cache for geocoding assistance
        self.location_cache = location_cache
        return cache

    def geocode_location(self, city, county, state='Minnesota'):
        """Geocode a city/county location using Nominatim (OpenStreetMap)"""
        try:
            # First check if we have this location in our local cache
            if hasattr(self, 'location_cache') and city:
                city_lower = city.lower()
                for loc_key, coords in self.location_cache.items():
                    if loc_key in city_lower:
                        return coords
            
            # Build query - try city first, fallback to county
            queries = []
            if city and city.strip():
                queries.append(f"{city}, {county} County, {state}")
                queries.append(f"{city}, {state}")
            if county and county.strip():
                queries.append(f"{county} County, {state}")
            
            headers = {
                'User-Agent': 'TowerWitch-Amateur-Radio-App/1.0'
            }
            
            for query in queries:
                try:
                    url = f"https://nominatim.openstreetmap.org/search?format=json&q={parse.quote(query)}&limit=1"
                    req = request.Request(url, headers=headers)
                    
                    with request.urlopen(req, timeout=3) as response:
                        data = json.loads(response.read().decode())
                        
                        if data and len(data) > 0:
                            lat = float(data[0]['lat'])
                            lon = float(data[0]['lon'])
                            # Small delay to respect rate limiting
                            time.sleep(0.1)
                            return lat, lon
                except:
                    continue
            
            # Fallback to approximate Minnesota center
            return 46.0, -94.0
            
        except Exception as e:
            print(f"[WARN] Geocoding failed for {city}, {county}: {e}")
            return 46.0, -94.0

    def load_fusion_data(self):
        """Load Yaesu System Fusion repeater data from CSV"""
        # Fusion is not a separate download. A RepeaterBook export says
        # in its Modes column which machines carry C4FM, so the file the
        # Import button already writes is the source. The hand-filtered
        # file is still read if somebody has one - including under the
        # misspelling it has always had.
        candidates = [os.path.join(os.path.dirname(__file__), name)
                      for name in ("data/repeaterbook.csv",
                                   "data/fusion_repeater_boook.csv",
                                   "data/fusion_repeater_book.csv")]

        # Clear existing data
        for item in self.fusion_tree.get_children():
            self.fusion_tree.delete(item)

        fusion_file = next((p for p in candidates if os.path.exists(p)), None)
        if fusion_file is None:
            print("[INFO] no repeater file to read Fusion from - Import a "
                  "RepeaterBook export")
            return
        
        try:
            print("[INFO] Loading Fusion repeater data...")
            
            # Build coordinate cache from existing amateur repeater data
            coord_cache = self.build_repeater_coordinate_cache()
            print(f"[OK] Built coordinate cache with {len(coord_cache)} entries")
            
            with open(fusion_file, 'r') as f:
                reader = csv.DictReader(f)
                fusion_repeaters = []
                geocode_count = 0
                cache_hit_count = 0
                
                for row in reader:
                    try:
                        # A hand-filtered Fusion file says nothing in its
                        # Modes column, so an empty one is taken at its
                        # word. A full export does say, and then it has
                        # to say Fusion to belong on this tab.
                        modes_text = (row.get('Modes') or '').strip()
                        if modes_text and 'fusion' not in modes_text.lower():
                            continue
                        output_freq = row.get('Output Freq', '0')
                        input_freq = row.get('Input Freq', '0')
                        
                        # Skip invalid entries
                        if not output_freq or float(output_freq) == 0:
                            continue
                        
                        # Parse tone - handle both numeric and D codes
                        uplink_tone = row.get('Uplink Tone', '')
                        downlink_tone = row.get('Downlink Tone', '')
                        
                        # Use downlink tone if available, otherwise uplink
                        tone = downlink_tone if downlink_tone else uplink_tone
                        if not tone:
                            tone = 'CSQ'
                        
                        # Build location string with city and county
                        location_parts = []
                        city = row.get('Location', '').strip()
                        county = row.get('County', '').strip()
                        call = row.get('Call', '').strip()
                        
                        if city:
                            location_parts.append(city)
                        if county:
                            location_parts.append(county)
                        location = ', '.join(location_parts) if location_parts else 'Unknown'
                        
                        # Get modes
                        modes = row.get('Modes', 'FM Fusion')
                        
                        # Try to get coordinates using multi-tier lookup
                        lat, lon = None, None
                        
                        # TIER 1: Match by frequency (most specific - same repeater)
                        if output_freq:
                            freq_key = f"{float(output_freq):.3f}"
                            if freq_key in coord_cache:
                                lat, lon = coord_cache[freq_key]
                                cache_hit_count += 1
                        
                        # TIER 2: Match by callsign + location (for multi-site clubs like W0UJ)
                        if lat is None and call and city:
                            city_lower = city.lower()
                            # Try each known location
                            for loc_key in ['brainerd', 'crosslake', 'crosby', 'nisswa', 'pequot', 
                                          'baxter', 'aitkin', 'pine river', 'pillager']:
                                if loc_key in city_lower:
                                    composite_key = f"{call}:{loc_key}"
                                    if composite_key in coord_cache:
                                        lat, lon = coord_cache[composite_key]
                                        cache_hit_count += 1
                                        break
                        
                        # TIER 3: Check location cache for known location names
                        if lat is None and hasattr(self, 'location_cache') and city:
                            city_lower = city.lower()
                            for loc_key, coords in self.location_cache.items():
                                if loc_key in city_lower:
                                    lat, lon = coords
                                    cache_hit_count += 1
                                    break
                        
                        # TIER 4: the town table, then a county centre - and
                        # both of them are Minnesota's. A RepeaterBook export
                        # is national, and Hennepin, Dakota and Cass are each
                        # several states, so only a Minnesota row is placed
                        # from them. The rest are listed without a distance
                        # rather than stood in the middle of Minnesota.
                        state_name = (row.get('State') or '').strip().lower()
                        in_minnesota = state_name in ('', 'minnesota', 'mn')
                        if lat is None and in_minnesota:
                            lat, lon = self.town_position(city)
                        if lat is None and in_minnesota:
                            county_centers = {
                                'crow wing': (46.450, -94.150),
                                'cass': (47.000, -94.300),
                                'hennepin': (44.977, -93.265),
                                'ramsey': (44.953, -93.090),
                                'anoka': (45.261, -93.450),
                                'dakota': (44.767, -93.277),
                                'olmsted': (43.967, -92.458),
                            }
                            county_lower = county.lower() if county else ''
                            lat, lon = county_centers.get(county_lower,
                                                          (None, None))
                        
                        repeater = {
                            'call': call if call else 'N0CALL',
                            'location': location,
                            'output': output_freq,
                            'input': input_freq,
                            'tone': tone,
                            'modes': modes,
                            'lat': lat,
                            'lon': lon
                        }
                        fusion_repeaters.append(repeater)
                        
                    except (ValueError, KeyError) as e:
                        continue
                
                print(f"[OK] Loaded {len(fusion_repeaters)} Fusion repeaters from CSV")
                print(f"[OK] Coordinate cache hits: {cache_hit_count}/{len(fusion_repeaters)} (no API calls)")
                
                # Calculate distances and sort by proximity
                repeater_distances = []
                for repeater in fusion_repeaters:
                    if repeater['lat'] is None or repeater['lon'] is None:
                        repeater_distances.append((float("inf"), None, repeater))
                        continue
                    distance = self.calculate_distance(self.last_lat, self.last_lon,
                                                     repeater['lat'], repeater['lon'])
                    bearing = self.calculate_bearing(self.last_lat, self.last_lon,
                                                   repeater['lat'], repeater['lon'])
                    repeater_distances.append((distance, bearing, repeater))
                
                # Sort by distance
                repeater_distances.sort(key=lambda x: x[0])
                
                # Populate tree
                for distance, bearing, repeater in repeater_distances:
                    if bearing is None:
                        how_far, heading = "—", "—"
                    else:
                        how_far = f"{distance:.1f} mi"
                        heading = f"{bearing:.0f}°"
                    values = (
                        repeater['call'],
                        repeater['location'],
                        self._mhz(repeater['output']),
                        self._mhz(repeater['input'], blank="simplex"),
                        self._tone_text(repeater['tone']),
                        repeater['modes'],
                        how_far,
                        heading,
                    )
                    self.fusion_tree.insert('', 'end', values=values)
                
        except Exception as e:
            print(f"[ERROR] Error loading Fusion data: {e}")
    
    def approximate_location_from_name(self, location, county, state=None):
        """Approximate coordinates from location and county names.

        Every table in here is Minnesota's, and county names repeat
        across states, so a row from anywhere else gets no position
        rather than a Minnesota one. It used to answer (46.0, -94.0)
        for anything it did not know, which reads on screen as a
        real fix in the middle of the state.
        """
        if state and state.strip().lower() not in ('minnesota', 'mn'):
            return (None, None)
        location_lower = location.lower()
        county_lower = county.lower() if county else ''
        
        # Common Minnesota cities and towns
        city_coords = {
            'minneapolis': (44.9778, -93.2650),
            'saint paul': (44.9537, -93.0900),
            'st paul': (44.9537, -93.0900),
            'st. paul': (44.9537, -93.0900),
            'duluth': (46.7867, -92.1005),
            'rochester': (43.9667, -92.4580),
            'bloomington': (44.8408, -93.2983),
            'brooklyn park': (45.0941, -93.3563),
            'plymouth': (45.0105, -93.4555),
            'woodbury': (44.9239, -92.9594),
            'maple grove': (45.0725, -93.4558),
            'blaine': (45.1608, -93.2349),
            'lakeville': (44.6497, -93.2427),
            'burnsville': (44.7678, -93.2777),
            'eden prairie': (44.8547, -93.4708),
            'coon rapids': (45.1199, -93.2877),
            'st cloud': (45.5579, -94.1632),
            'brainerd': (46.3580, -94.2008),
            'bemidji': (47.4736, -94.8803),
            'thief river falls': (48.1169, -96.1812),
            'marshall': (44.4469, -95.7883),
            'mankato': (44.1636, -93.9993),
            'moorhead': (46.8738, -96.7678),
            'winona': (44.0499, -91.6393),
            'albert lea': (43.6480, -93.3683),
            'white bear lake': (45.0847, -93.0099),
            'burnsville': (44.7678, -93.2777),
            'medina': (45.0430, -93.5827),
            'little falls': (45.9763, -94.3627),
            'pine river': (46.7280, -94.3947),
            'walker': (47.1013, -94.5886),
            'aitkin': (46.5330, -93.7108),
            'crosby': (46.4830, -93.9571),
            'crosslake': (46.6619, -94.1069),
            'pequot lakes': (46.6038, -94.3105),
            'backus': (46.8272, -94.5068),
            'hugo': (45.1608, -92.9955),
            'oakdale': (44.9630, -92.9649),
            'centerville': (45.1622, -93.0558),
            'medford': (44.1694, -93.2452),
            'rockford': (45.0877, -93.7341),
            'clara city': (44.9516, -95.3647),
            'karlstad': (48.5730, -96.5178),
            'warroad': (48.9055, -95.3133),
            'isanti': (45.4911, -93.2477),
            'princeton': (45.5705, -93.5816),
            'little canada': (45.0241, -93.0877),
            'wabasso': (44.4061, -95.2464),
        }
        
        # Check for city name match
        for city, coords in city_coords.items():
            if city in location_lower:
                return coords
        
        # County center fallbacks
        county_centers = {
            'ramsey': (44.9537, -93.0900),
            'hennepin': (44.9778, -93.2650),
            'dakota': (44.7678, -93.2777),
            'anoka': (45.1608, -93.2349),
            'washington': (45.0491, -92.8288),
            'crow wing': (46.4500, -94.1500),
            'cass': (47.0000, -94.3000),
            'beltrami': (47.6500, -94.9000),
            'pennington': (48.0500, -96.0000),
            'redwood': (44.5500, -95.2500),
            'morrison': (46.0000, -94.3000),
            'kittson': (48.7500, -96.7500),
            'steele': (44.0000, -93.2500),
            'wright': (45.1800, -93.9600),
            'lyon': (44.4500, -95.8500),
            'chippewa': (45.0000, -95.5000),
        }
        
        if county_lower in county_centers:
            return county_centers[county_lower]

        # Nothing known. Saying so beats standing it in central Minnesota.
        return (None, None)
    
    def load_dmr_dstar_data(self):
        """Load DMR and D-Star repeater data from CSV or Radio Reference"""
        # Clear existing data
        for item in self.dmr_dstar_tree.get_children():
            self.dmr_dstar_tree.delete(item)
        
        # Build coordinate cache for lookups
        coord_cache = self.build_repeater_coordinate_cache()
        
        dmr_dstar_repeaters = []
        
        # First, try loading from dedicated Repeater Book DMR file
        # The dedicated file if somebody has one, otherwise the export
        # the Import button writes: a RepeaterBook export names DMR and
        # DSTAR in its Modes column, so it needs no filtering beforehand.
        dmr_book_file = next(
            (p for p in (os.path.join(os.path.dirname(__file__),
                                      'data/Repeater_Book_DMR_MN.csv'),
                         os.path.join(os.path.dirname(__file__),
                                      'data/repeaterbook.csv'))
             if os.path.exists(p)), None)
        if dmr_book_file:
            try:
                with open(dmr_book_file, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        try:
                            # A dedicated DMR file says nothing in Modes and
                            # is taken at its word; a full export has to say
                            # one of the two to belong on this tab.
                            modes_text = (row.get('Modes') or '').strip().lower()
                            if modes_text and not any(m in modes_text for m in
                                                      ('dmr', 'dstar', 'd-star')):
                                continue
                            output_freq = row.get('Output Freq', '0').strip()
                            input_freq = row.get('Input Freq', '0').strip()
                            
                            if not output_freq or float(output_freq) == 0:
                                continue
                            
                            call = row.get('Call', '').strip()
                            location_name = row.get('Location', 'Unknown').strip()
                            county = row.get('County', '').strip()
                            modes = row.get('Modes', 'DMR').strip()
                            digital_access = row.get('Digital Access', '').strip()
                            
                            # Parse location for coordinates
                            lat, lon = None, None
                            location_lower = location_name.lower()
                            
                            # Use coordinate cache or location-based lookup
                            if call and call in coord_cache:
                                lat, lon = coord_cache[call]
                            else:
                                # Try to geocode from location name
                                location_key = f"{location_name.split('-')[0].strip().lower()}|{county.lower()}|minnesota"
                                if location_key in coord_cache:
                                    lat, lon = coord_cache[location_key]
                                else:
                                    # Use approximate coordinates for known cities
                                    lat, lon = self.approximate_location_from_name(
                                        location_name, county,
                                        row.get('State'))
                            
                            repeater = {
                                'call': call if call else 'N0CALL',
                                'location': f"{location_name}, {county}" if county else location_name,
                                'output': output_freq,
                                'input': input_freq if input_freq else output_freq,
                                'mode': modes,
                                'cc_id': digital_access if digital_access else 'N/A',
                                'lat': lat,
                                'lon': lon
                            }
                            dmr_dstar_repeaters.append(repeater)
                            
                        except (ValueError, KeyError) as e:
                            continue
                            
                print(f"[OK] Loaded {len(dmr_dstar_repeaters)} DMR/D-Star "
                      f"repeaters from {os.path.basename(dmr_book_file)}")
            except Exception as e:
                print(f"[WARN] Error loading DMR from Repeater Book: {e}")
        
        # Also load from Radio Reference CSV files (for additional coverage)
        repeater_files = [
            'data/crow_wing_county_radio_reference.csv',
            'data/cass_county_radio_reference.csv',
        ]
        
        for csv_file in repeater_files:
            file_path = os.path.join(os.path.dirname(__file__), csv_file)
            if not os.path.exists(file_path):
                continue
                
            try:
                with open(file_path, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        category = row.get('Agency/Category', '').lower()
                        tag = row.get('Tag', '').lower()
                        mode = row.get('Mode', '').upper()
                        
                        # Look for DMR or D-Star repeaters
                        if ('amateur' in category or 'ham' in tag) and (mode == 'DMR' or 'dstar' in mode.lower() or 'd-star' in mode.lower()):
                            try:
                                output_freq = row.get('Frequency Output', '0')
                                input_freq = row.get('Frequency Input', '0')
                                
                                if not output_freq or float(output_freq) == 0:
                                    continue
                                
                                call = row.get('FCC Callsign', '').strip()
                                location_name = row.get('Description', 'Unknown')
                                
                                # Get CC/ID info from tone fields for DMR
                                cc_id = ''
                                if mode == 'DMR':
                                    tone_info = row.get('PL Output Tone', row.get('PL Input Tone', ''))
                                    if 'CC' in tone_info or 'TG' in tone_info:
                                        cc_id = tone_info
                                
                                # Get coordinates from cache or location lookup
                                lat, lon = None, None
                                freq_key = f"{float(output_freq):.3f}"
                                if freq_key in coord_cache:
                                    lat, lon = coord_cache[freq_key]
                                elif call and call in coord_cache:
                                    lat, lon = coord_cache[call]
                                else:
                                    # Use location-based lookup
                                    if 'brainerd' in location_name.lower():
                                        lat, lon = 46.358, -94.201
                                    elif 'crosslake' in location_name.lower():
                                        lat, lon = 46.660, -94.107
                                    elif 'pequot' in location_name.lower():
                                        lat, lon = 46.603, -94.312
                                    elif 'crosby' in location_name.lower():
                                        lat, lon = 46.484, -93.957
                                    else:
                                        lat, lon = 46.450, -94.150
                                
                                repeater = {
                                    'call': call if call else 'N0CALL',
                                    'location': location_name,
                                    'output': output_freq,
                                    'input': input_freq if input_freq else output_freq,
                                    'mode': mode,
                                    'cc_id': cc_id if cc_id else 'N/A',
                                    'lat': lat,
                                    'lon': lon
                                }
                                dmr_dstar_repeaters.append(repeater)
                                
                            except (ValueError, KeyError) as e:
                                continue
            except Exception as e:
                print(f"[WARN] Error loading DMR/D-Star from {csv_file}: {e}")
        
        if dmr_dstar_repeaters:
            print(f"[OK] Loaded {len(dmr_dstar_repeaters)} DMR/D-Star repeaters")
            
            # Calculate distances and sort by proximity
            repeater_distances = []
            for repeater in dmr_dstar_repeaters:
                if repeater['lat'] is None or repeater['lon'] is None:
                    repeater_distances.append((float("inf"), None, repeater))
                    continue
                distance = self.calculate_distance(self.last_lat, self.last_lon,
                                                 repeater['lat'], repeater['lon'])
                bearing = self.calculate_bearing(self.last_lat, self.last_lon,
                                               repeater['lat'], repeater['lon'])
                repeater_distances.append((distance, bearing, repeater))
            
            # Sort by distance
            repeater_distances.sort(key=lambda x: x[0])
            
            # Populate tree
            for distance, bearing, repeater in repeater_distances:
                if bearing is None:
                    how_far, heading = "—", "—"
                else:
                    how_far = f"{distance:.1f} mi"
                    heading = f"{bearing:.0f}°"
                values = (
                    repeater['call'],
                    repeater['location'],
                    self._mhz(repeater['output']),
                    self._mhz(repeater['input'], blank="simplex"),
                    repeater['mode'],
                    repeater['cc_id'],
                    how_far,
                    heading,
                )
                self.dmr_dstar_tree.insert('', 'end', values=values)
        else:
            print("[INFO] No DMR/D-Star repeaters found in local data")
            # Add info message
            self.dmr_dstar_tree.insert('', 'end', values=(
                '', 'No DMR/D-Star repeaters in loaded data', '', '', '', '', '', ''
            ))

    def load_noaa_weather_data(self):
        """Load NOAA Weather Radio station data for Minnesota"""
        # Clear existing data
        for item in self.noaa_tree.get_children():
            self.noaa_tree.delete(item)
        
        # Minnesota NOAA Weather Radio Stations
        # Data from https://www.weather.gov/nwr/stations?State=MN
        mn_noaa_stations = [
            # Format: (city, frequency, coverage_area, lat, lon)
            ('Alexandria', '162.475', 'Douglas, Pope, Todd, Grant, Stevens counties', 45.8852, -95.3772),
            ('Baudette', '162.550', 'Lake of the Woods, Koochiching, Beltrami counties', 48.7128, -94.6103),
            ('Bemidji', '162.400', 'Beltrami, Clearwater, Hubbard counties', 47.4736, -94.8803),
            ('Brainerd', '162.550', 'Crow Wing, Cass, Aitkin, Morrison counties', 46.3580, -94.2008),
            ('Crookston', '162.550', 'Polk, Norman, Clay, Red Lake counties', 47.7741, -96.6078),
            ('Detroit Lakes', '162.400', 'Becker, Otter Tail, Wadena counties', 46.8172, -95.8453),
            ('Duluth', '162.550', 'St. Louis, Carlton, Lake, Cook counties', 46.7867, -92.1005),
            ('Ely', '162.425', 'Lake, Cook, northern St. Louis counties', 47.9032, -91.8671),
            ('Fairmont', '162.500', 'Martin, Faribault, Jackson, Watonwan counties', 43.6524, -94.4608),
            ('Fergus Falls', '162.475', 'Otter Tail, Wilkin, Grant counties', 46.2830, -96.0776),
            ('Grand Marais', '162.450', 'Cook, Lake counties', 47.7505, -90.3343),
            ('Grand Rapids', '162.525', 'Itasca, Aitkin, Cass counties', 47.2369, -93.5302),
            ('Hibbing', '162.475', 'Northern St. Louis, Itasca counties', 47.4271, -92.9377),
            ('International Falls', '162.400', 'Koochiching, northern St. Louis counties', 48.6019, -93.4105),
            ('Jackson', '162.425', 'Jackson, Nobles, Cottonwood, Martin counties', 43.6205, -94.9869),
            ('Mankato', '162.475', 'Blue Earth, Nicollet, Le Sueur, Waseca counties', 44.1636, -94.0000),
            ('Marshall', '162.425', 'Lyon, Lincoln, Murray, Yellow Medicine counties', 44.4469, -95.7883),
            ('Minneapolis', '162.550', 'Hennepin, Ramsey, Anoka, Washington counties', 44.9778, -93.2650),
            ('Montevideo', '162.450', 'Chippewa, Swift, Lac qui Parle, Yellow Medicine counties', 44.9458, -95.7231),
            ('New Ulm', '162.400', 'Brown, Nicollet, Sibley, Renville counties', 44.3124, -94.4608),
            ('Owatonna', '162.400', 'Steele, Dodge, Waseca, Freeborn counties', 44.0958, -93.2260),
            ('Park Rapids', '162.475', 'Hubbard, Wadena, Becker counties', 46.9219, -95.0586),
            ('Pipestone', '162.500', 'Pipestone, Rock, Murray, Lincoln counties', 44.0066, -96.3178),
            ('Red Wing', '162.500', 'Goodhue, Dakota, Wabasha, Pierce (WI) counties', 44.5624, -92.5338),
            ('Redwood Falls', '162.475', 'Redwood, Brown, Renville, Lyon counties', 44.5391, -95.1169),
            ('Rochester', '162.400', 'Olmsted, Dodge, Mower, Fillmore counties', 43.9667, -92.4580),
            ('St. Cloud', '162.475', 'Stearns, Benton, Sherburne counties', 45.5579, -94.1632),
            ('St. James', '162.550', 'Watonwan, Martin, Jackson, Blue Earth counties', 43.9880, -94.6272),
            ('St. Peter', '162.525', 'Nicollet, Le Sueur, Sibley counties', 44.3236, -93.9578),
            ('Thief River Falls', '162.475', 'Pennington, Marshall, Red Lake counties', 48.1191, -96.1811),
            ('Two Harbors', '162.500', 'Lake, St. Louis (northeast) counties', 47.0227, -91.6707),
            ('Virginia', '162.400', 'St. Louis (north-central), Itasca counties', 47.5233, -92.5366),
            ('Willmar', '162.550', 'Kandiyohi, Meeker, Renville counties', 45.1219, -95.0433),
            ('Winona', '162.475', 'Winona, Wabasha, Fillmore, Houston counties', 44.0499, -91.6393),
            ('Worthington', '162.450', 'Nobles, Jackson, Rock, Murray counties', 43.6199, -95.5969),
        ]
        
        # Calculate distances and sort by proximity (nearest first for SDR reception)
        station_distances = []
        for city, freq, coverage, lat, lon in mn_noaa_stations:
            distance = self.calculate_distance(self.last_lat, self.last_lon, lat, lon)
            station_distances.append((distance, city, freq, coverage, lat, lon))
        
        # Sort by distance (nearest stations are most likely receivable)
        station_distances.sort(key=lambda x: x[0])
        
        # Populate tree with distance info
        for distance, city, freq, coverage, lat, lon in station_distances:
            # More granular signal strength indicator for SDR reception
            # NOAA transmitters are typically 300-1000 watts
            if distance < 15:
                signal = "Very Strong"
            elif distance < 30:
                signal = "Strong"
            elif distance < 50:
                signal = "Good"
            elif distance < 75:
                signal = "Moderate"
            elif distance < 100:
                signal = "Weak"
            else:
                signal = "Very Weak"
            
            values = (
                city,
                f"{freq} MHz",
                f"{coverage} ({distance:.1f} mi)",
                signal
            )
            self.noaa_tree.insert('', 'end', values=values)
        
        print(f"[OK] Loaded {len(mn_noaa_stations)} NOAA Weather Radio stations for Minnesota")
    
    def load_simplex_data(self):
        """Load simplex frequency data"""
        simplex_file = os.path.join(os.path.dirname(__file__), "data/amateur_simplex.csv")
        if os.path.exists(simplex_file):
            try:
                with open(simplex_file, 'r') as f:
                    reader = csv.DictReader(f)
                    self.amateur_simplex_data = list(reader)
                print(f"[OK] Loaded {len(self.amateur_simplex_data)} simplex frequencies")
            except Exception as e:
                print(f"[ERROR] Error loading simplex data: {e}")
                self.amateur_simplex_data = []
        else:
            print(f"[WARN] Simplex file not found: {simplex_file}")
            self.amateur_simplex_data = []

        # Populate simplex tree if it exists
        if hasattr(self, 'amateur_simplex_tree'):
            self.populate_simplex_tree()

    def populate_simplex_tree(self):
        """Populate simplex frequency tree"""
        tree = self.amateur_simplex_tree

        # Clear existing data
        for item in tree.get_children():
            tree.delete(item)

        # Add simplex frequencies
        for entry in self.amateur_simplex_data:
            freq_output = entry.get('Frequency Output', '0')
            freq_input = entry.get('Frequency Input', '0')
            
            # Display format: show input if it's a cross-band/repeater, otherwise just output
            if freq_input and float(freq_input) > 0 and freq_input != freq_output:
                freq_display = f"{freq_output} / {freq_input}"
            else:
                freq_display = freq_output
            
            tone_out = entry.get('PL Output Tone', 'CSQ')
            tone_in = entry.get('PL Input Tone', '')
            tone_display = tone_out if tone_out else 'CSQ'
            
            values = (
                freq_display,
                entry.get('Description', ''),
                entry.get('Alpha Tag', ''),
                entry.get('Mode', ''),
                tone_display
            )
            tree.insert('', 'end', values=values)

    def calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two points using haversine formula"""
        R = 3959  # Earth radius in miles
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        return R * c

    def calculate_bearing(self, lat1, lon1, lat2, lon2):
        """Calculate bearing from point 1 to point 2"""
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlon = lon2 - lon1
        y = sin(dlon) * cos(lat2)
        x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
        bearing = atan2(y, x)
        return (degrees(bearing) + 360) % 360

    def lat_lon_to_maidenhead(self, lat, lon):
        """Convert latitude/longitude to Maidenhead grid square (6-character)"""
        # Adjust longitude to 0-360 range
        adj_lon = lon + 180
        adj_lat = lat + 90
        
        # Field (first 2 characters)
        field_lon = int(adj_lon / 20)
        field_lat = int(adj_lat / 10)
        grid = chr(ord('A') + field_lon) + chr(ord('A') + field_lat)
        
        # Square (next 2 digits)
        square_lon = int((adj_lon % 20) / 2)
        square_lat = int((adj_lat % 10) / 1)
        grid += str(square_lon) + str(square_lat)
        
        # Subsquare (last 2 characters - lowercase)
        subsq_lon = int(((adj_lon % 20) % 2) * 12)
        subsq_lat = int(((adj_lat % 10) % 1) * 24)
        grid += chr(ord('a') + subsq_lon) + chr(ord('a') + subsq_lat)
        
        return grid

    def update_grid_display(self):
        """Update grid systems display with current position"""
        # Clear existing
        for item in self.grid_tree.get_children():
            self.grid_tree.delete(item)
        
        # Calculate Maidenhead grid
        grid_6char = self.lat_lon_to_maidenhead(self.last_lat, self.last_lon)
        grid_4char = grid_6char[:4]  # Common 4-character format
        
        # Calculate MGRS/UTM coordinates
        mgrs_coord = self.lat_lon_to_mgrs(self.last_lat, self.last_lon)
        
        # Get What3Words if available
        w3w_coord = self.get_what3words(self.last_lat, self.last_lon)
        
        # Format coordinates in various systems
        grid_items = [
            ('Maidenhead (6-char)', grid_6char, 'Full precision'),
            ('Maidenhead (4-char)', grid_4char, 'Common format'),
            ('Decimal Degrees', f"{self.last_lat:.6f}, {self.last_lon:.6f}", 'DD format'),
            ('Degrees Minutes Seconds', self.dd_to_dms(self.last_lat, self.last_lon), 'DMS format'),
            ('MGRS/UTM', mgrs_coord, 'Military Grid Reference'),
        ]
        
        # Add What3Words if available
        if w3w_coord:
            grid_items.append(('What3Words', w3w_coord, 'Three word address'))
        
        for system, value, info in grid_items:
            self.grid_tree.insert('', 'end', values=(system, value, info))
        
        print(f"[OK] Updated grid display for position: {self.last_lat:.6f}, {self.last_lon:.6f}")

    def dd_to_dms(self, lat, lon):
        """Convert decimal degrees to degrees/minutes/seconds format."""
        def split(value):
            d = int(abs(value))
            m_full = (abs(value) - d) * 60
            m = int(m_full)
            s = (m_full - m) * 60
            return d, m, s

        lat_d, lat_m, lat_s = split(lat)
        lon_d, lon_m, lon_s = split(lon)
        lat_dir = 'N' if lat >= 0 else 'S'
        lon_dir = 'E' if lon >= 0 else 'W'
        return (f"{lat_d}°{lat_m:02d}'{lat_s:05.2f}\"{lat_dir}, "
                f"{lon_d}°{lon_m:02d}'{lon_s:05.2f}\"{lon_dir}")

    def get_utm_zone(self, lon):
        """Get UTM zone from longitude"""
        zone = int((lon + 180) / 6) + 1
        return f"Zone {zone}"

    def lat_lon_to_mgrs(self, lat, lon):
        """Convert lat/lon to MGRS coordinate (simplified)"""
        try:
            # Calculate UTM zone
            zone = int((lon + 180) / 6) + 1
            
            # Calculate latitude band (C-X, omitting I and O)
            bands = 'CDEFGHJKLMNPQRSTUVWXX'
            band_idx = int((lat + 80) / 8)
            if band_idx < 0 or band_idx >= len(bands):
                band = 'Z'  # Special case for polar regions
            else:
                band = bands[band_idx]
            
            # Calculate UTM easting and northing (simplified WGS84)
            lat_rad = radians(lat)
            lon_rad = radians(lon)
            lon0_rad = radians((zone - 1) * 6 - 180 + 3)  # Central meridian
            
            # WGS84 parameters
            a = 6378137.0  # Semi-major axis
            f = 1/298.257223563  # Flattening
            k0 = 0.9996  # Scale factor
            
            # Calculate UTM coordinates (simplified, good enough for display)
            N = a / sqrt(1 - (2*f - f*f) * sin(lat_rad)**2)
            T = tan(lat_rad)**2
            C = (2*f - f*f) / (1 - (2*f - f*f)) * cos(lat_rad)**2
            A = cos(lat_rad) * (lon_rad - lon0_rad)
            
            easting = k0 * N * (A + (1-T+C)*A**3/6) + 500000
            northing = k0 * (N * lat_rad + N * tan(lat_rad) * (A**2/2))
            if lat < 0:
                northing += 10000000
            
            # Calculate 100km grid square (simplified)
            # For display purposes, just show zone, band, and 6-digit coordinates
            e_100km = int(easting / 100000)
            n_100km = int(northing / 100000) % 20
            
            # Grid square letters (simplified - real MGRS uses complex lookup tables)
            e_letters = 'ABCDEFGHJKLMNPQRSTUV'
            n_letters = 'ABCDEFGHJKLMNPQRSTUV'
            grid_e = e_letters[e_100km % 8] if e_100km < 8 else 'X'
            grid_n = n_letters[n_100km % 20]
            
            # Format: zone + band + grid + 5-digit easting + 5-digit northing
            e_digits = str(int(easting % 100000)).zfill(5)
            n_digits = str(int(northing % 100000)).zfill(5)
            
            return f"{zone}{band} {grid_e}{grid_n} {e_digits} {n_digits}"
            
        except Exception as e:
            print(f"[WARN] MGRS calculation error: {e}")
            return f"Zone {zone}{band}"

    def get_what3words(self, lat, lon):
        """Get What3Words address (requires API key in config)"""
        try:
            # Check if API key exists in config
            config = configparser.ConfigParser()
            config.read('towerwitch_config.ini')
            
            if not config.has_option('API', 'what3words_key'):
                return None
                
            api_key = config.get('API', 'what3words_key')
            if not api_key or api_key == 'YOUR_KEY_HERE':
                return None
            
            # Make API request to What3Words using urllib
            url = f"https://api.what3words.com/v3/convert-to-3wa?coordinates={lat},{lon}&key={api_key}"
            
            req = request.Request(url)
            with request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                words = data.get('words', '')
                if words:
                    return f"///{words}"
            
            return None
            
        except Exception as e:
            print(f"[WARN] What3Words lookup failed: {e}")
            return None

    # ---------------------------------------------- RadioReference import
    def import_radioreference(self):
        """Pick one or more RadioReference CSVs and take them in.

        Either kind, in any order, from anywhere - a stick, a download
        folder, the other Pi. Which file is which is read off its header
        rather than its name, because a file that has been through a
        download folder twice is "trs_tg_3508 (1).csv".

        Nothing here is allowed to take the window down. A file that
        cannot be read, is not one of ours, or is half full of nonsense
        ends as a line in the report and the rest of the files still go
        in. See radioreference.py for what a report carries.
        """
        paths = filedialog.askopenfilenames(
            title="Import RadioReference CSV",
            filetypes=[("RadioReference CSV", "*.csv"), ("All files", "*.*")])
        if not paths:
            return                       # cancelled; not a fault, say nothing

        said, sites_in, tgs_in, freqs_in, reps_in, failed = [], 0, 0, 0, 0, 0
        for path in paths:
            summarise = radioreference.summary
            try:
                kind, records, report = radioreference.read(path)
                if kind is None:
                    # Not RadioReference. RepeaterBook is the other export
                    # somebody is likely to be holding, and it is the better
                    # source for amateur repeaters - the people who own the
                    # machines keep it. Try it before calling the file junk.
                    other, other_report = repeaterbook.read(path)
                    if not other_report["fatal"]:
                        kind, records, report = (repeaterbook.REPEATERBOOK,
                                                 other, other_report)
                        summarise = repeaterbook.summary
            except Exception as exc:     # a reader must never take the GUI down
                print(f"[ERROR] import: {os.path.basename(path)} could not be "
                      f"read ({exc})")
                said.append(f"{os.path.basename(path)}: could not be read")
                failed += 1
                continue

            for line in summarise(report):
                print(line)
            if report["fatal"]:
                said.append(f"{os.path.basename(path)}: {report['fatal']}")
                failed += 1
                continue

            try:
                if kind == radioreference.SITES:
                    # Written back out properly quoted to the path the
                    # rest of the program already reads, so the sites
                    # tree and the OP25 payload both see it without
                    # anything else having to learn a new place to look.
                    radioreference.write_sites_csv(ARMER_CSV_PATH, records)
                    armer_state_store.bootstrap_from_csv(ARMER_CSV_PATH,
                                                         ARMER_STATE_JSON)
                    sites_in += report["kept"]
                    said.append(f"{report['kept']} sites")
                elif kind == radioreference.TALKGROUPS:
                    talkgroup_store.save(TALKGROUPS_JSON,
                                         report["system"] or "unknown",
                                         records, source=path)
                    tgs_in += report["kept"]
                    said.append(f"{report['kept']} talkgroups"
                                + (f" for system {report['system']}"
                                   if report["system"] else ""))
                elif kind == radioreference.FREQUENCIES:
                    # A county, not a system: everything audible in one
                    # place, each row carrying the Tag that says what it
                    # is. Only the amateur rows have somewhere to go on
                    # screen so far; the rest are held until we decide
                    # where a Fire Dispatch channel belongs.
                    frequency_store.save(COUNTY_JSON,
                                         report["system"] or "unknown",
                                         records, source=path)
                    freqs_in += report["kept"]
                    ham = sum(1 for r in records
                              if (r.get("tag") or "").lower() == "ham")
                    said.append(f"{report['kept']} county frequencies"
                                + (f" for county {report['system']}"
                                   if report["system"] else "")
                                + (f", {ham} amateur" if ham else ""))
                elif kind == repeaterbook.REPEATERBOOK:
                    # Written to the folder the band tabs already read, the
                    # way a sites import is written to the ARMER CSV. Coming
                    # in through this button is what should put a file where
                    # the program looks; nobody should have to place it by
                    # hand afterwards.
                    repeaterbook.write_csv(REPEATERBOOK_CSV, records)
                    reps_in += report["kept"]
                    states = len(report.get("states") or {})
                    said.append(f"{report['kept']} repeaters"
                                + (f" across {states} states" if states > 1
                                   else ""))
                else:
                    # A kind that was read but that nothing here stores used
                    # to fall through both tests, report success and keep
                    # nothing - which is how a county import announced 90
                    # frequencies and left no trace of them.
                    print(f"[ERROR] import: {os.path.basename(path)} was read "
                          f"as {kind!r}, which nothing here knows how to keep")
                    said.append(f"{os.path.basename(path)}: read but not kept")
                    failed += 1
                    continue
            except (OSError, ValueError) as exc:
                print(f"[ERROR] import: {os.path.basename(path)} read but not "
                      f"saved ({exc})")
                said.append(f"{os.path.basename(path)}: read but not saved")
                failed += 1
                continue

            if report["repaired"]:
                said.append(f"{len(report['repaired'])} rows had quotes the "
                            f"export failed to escape, put back")
            if report["skipped"]:
                said.append(f"{len(report['skipped'])} rows skipped")

        if sites_in:
            self.load_armer_data()       # the tree, from the file just written
            self._update_op25_button()
        if freqs_in or reps_in:
            self.load_amateur_data()     # the band tabs, from what just came in

        note = "; ".join(said) if said else "nothing imported"
        self.armer_import_note.config(text=f"Last import: {note}")
        if failed and not (sites_in or tgs_in or freqs_in or reps_in):
            messagebox.showerror("Import failed", note)
        elif failed:
            messagebox.showwarning("Imported with problems", note)

    def export_radioreference(self):
        """Write what is held back out as RadioReference CSVs.

        Into a folder, one file per kind, named the way the website names
        them so they go back where they came from. What leaves here is
        correct CSV - the quotes inside a description escaped the way the
        standard says - which the file from the website is not, so an
        export can be read by anything and the original cannot.
        """
        sites = []
        try:
            state = armer_state_store.load(ARMER_STATE_JSON) or {}
            for entry in (state.get("sites") or {}).values():
                sites.append({
                    "rfss": entry.get("rfid"), "site": entry.get("stid"),
                    "site_hex": (entry.get("stid_hex") or "").replace("0x", ""),
                    "nac": int(entry["nac"], 16) if entry.get("nac") else None,
                    "description": entry.get("description", ""),
                    "county": entry.get("county", ""),
                    "lat": entry.get("lat"), "lon": entry.get("lon"),
                    "range_mi": entry.get("range_mi"),
                    "control_hz": entry.get("cc_freqs_hz") or [],
                    "all_hz": entry.get("all_freqs_hz") or [],
                })
        except (OSError, ValueError, TypeError) as exc:
            print(f"[WARN] export: the site store could not be read ({exc})")

        by_system = talkgroup_store.load(TALKGROUPS_JSON).get("systems", {})
        if not sites and not by_system:
            messagebox.showinfo(
                "Nothing to export",
                "No sites or talkgroups have been imported yet.")
            return

        folder = filedialog.askdirectory(title="Export RadioReference CSV into")
        if not folder:
            return

        written = []
        try:
            if sites:
                name = os.path.join(folder, "trs_sites_export.csv")
                radioreference.write_sites_csv(name, sites)
                written.append(f"{len(sites)} sites")
            for system, entry in by_system.items():
                records = entry.get("talkgroups") or []
                if not records:
                    continue
                name = os.path.join(folder, f"trs_tg_{system}.csv")
                radioreference.write_talkgroups_csv(name, records)
                written.append(f"{len(records)} talkgroups ({system})")
        except OSError as exc:
            print(f"[ERROR] export: could not write into {folder} ({exc})")
            messagebox.showerror("Export failed",
                                 f"Could not write into that folder:\n{exc}")
            return

        said = ", ".join(written) if written else "nothing"
        print(f"[OK] export: wrote {said} into {folder}")
        self.armer_import_note.config(text=f"Last export: {said} -> {folder}")
        messagebox.showinfo("Exported", f"Wrote {said} into\n{folder}")

    def load_armer_data(self):
        """Load ARMER site data from CSV"""
        armer_file = os.path.join(os.path.dirname(__file__), "trs_sites_3508.csv")
        
        if not os.path.exists(armer_file):
            print("[WARN] ARMER data file not found")
            self.armer_loaded = False
            self._update_op25_button()
            return
        
        # Clear existing
        for item in self.armer_tree.get_children():
            self.armer_tree.delete(item)
        self.armer_loaded = False
        
        try:
            with open(armer_file, 'r') as f:
                reader = csv.reader(f)
                header = next(reader)  # Skip header
                
                sites = []
                for row in reader:
                    if len(row) < 9:
                        continue
                    
                    try:
                        lat = float(row[6])
                        lon = float(row[7])
                        
                        # Calculate distance and bearing
                        distance = self.calculate_distance(
                            self.last_lat, self.last_lon, lat, lon)
                        bearing = self.calculate_bearing(
                            self.last_lat, self.last_lon, lat, lon)
                        
                        # Get control frequencies (marked with 'c')
                        freqs = [f for f in row[9:] if f and 'c' in f.lower()]
                        freq_display = ', '.join(freqs[:3])  # Show first 3
                        if len(freqs) > 3:
                            freq_display += f" (+{len(freqs)-3} more)"
                        
                        site = {
                            'site_id': row[1],
                            'rfid': row[0],
                            'description': row[4],
                            'county': row[5],
                            'range': row[8],
                            'distance': distance,
                            'bearing': bearing,
                            'freqs': freq_display
                        }
                        sites.append(site)
                    except (ValueError, IndexError):
                        continue
                
                # Sort by distance
                sites.sort(key=lambda x: x['distance'])
                
                # Add to tree (show closest 7)
                for site in sites[:7]:
                    values = (
                        site['site_id'],
                        site['description'][:25],  # Truncate long names
                        site['county'],
                        f"{site['distance']:.1f} mi",
                        f"{site['bearing']:.0f}°",
                        f"{site['range']} mi",
                        site['freqs']
                    )
                    self.armer_tree.insert('', 'end', iid=f"{site['rfid']}-{site['site_id']}", values=values)
                self._armer_closest = [
                    {'site_name': site['description'], 'distance': f"{site['distance']:.1f} mi",
                     'bearing': f"{site['bearing']:.0f}°", 'nac': '',
                     'control_channels': site['freqs']}
                    for site in sites[:UDP_CONFIG['armer_tower_count']]]
                
                print(f"[OK] Loaded {len(sites)} ARMER sites")
                self.armer_loaded = len(sites) > 0
                
        except Exception as e:
            print(f"[ERROR] Error loading ARMER data: {e}")
        self._update_op25_button()

    def get_nearest_town(self, lat, lon):
        """Get nearest town/city using reverse geocoding with Nominatim (OSM)"""
        try:
            # Nominatim requires a user agent
            headers = {
                'User-Agent': 'TowerWitch-Amateur-Radio-App/1.0'
            }
            
            # Build the geocoding URL
            url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=10"
            
            req = request.Request(url, headers=headers)
            with request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                
                # Extract city/town information
                address = data.get('address', {})
                town = (address.get('city') or 
                       address.get('town') or 
                       address.get('village') or 
                       address.get('hamlet') or
                       address.get('county', 'Unknown'))
                
                state = address.get('state', '')
                
                if town and state:
                    new_town = f"{town}, {state}"
                elif town:
                    new_town = town
                else:
                    new_town = "Unknown Location"
                
                # Update the nearest town
                self.nearest_town = new_town
                self.last_geocode_time = time.time()
                print(f"[OK] Nearest town: {self.nearest_town}")
                
                # Force update the GPS display on main thread to show new town
                self.root.after(0, lambda: self.update_gps_display())
                
        except (URLError, Exception) as e:
            print(f"[WARN] Geocoding failed: {e}")
            # Keep the last known town
        
        return self.nearest_town

    def get_nearby_airports(self, lat, lon, radius_nm=50):
        """Get nearby airports using CheckWX or fallback to static data
        
        Args:
            lat: Latitude
            lon: Longitude  
            radius_nm: Search radius in nautical miles (default 50nm)
            
        Returns:
            List of airport dictionaries with frequencies
        """
        airports = []
        
        try:
            # Try CheckWX API first (free tier, no API key needed for basic queries)
            # Alternative: use AirLabs, AviationStack, or OurAirports
            
            # For now, use a simple approach: calculate distance to known airports from our static data
            # and supplement with any API data if available
            
            # Load our static airport data
            airport_file = os.path.join(os.path.dirname(__file__), "data/airport_frequencies.csv")
            custom_airport_file = os.path.join(os.path.dirname(__file__), "data/airport_frequencies_custom.csv")
            
            airport_data = {}
            
            # Load main airport file
            if os.path.exists(airport_file):
                with open(airport_file, 'r') as f:
                    reader = csv.DictReader(f)
                    
                    # Group frequencies by airport
                    for row in reader:
                        airport_code = row.get('Airport', '')
                        if airport_code and airport_code != 'COMMON':
                            if airport_code not in airport_data:
                                airport_data[airport_code] = {
                                    'code': airport_code,
                                    'frequencies': [],
                                    'lat': None,
                                    'lon': None
                                }
                            
                            airport_data[airport_code]['frequencies'].append({
                                'freq': row.get('Frequency Output', '0'),
                                'description': row.get('Description', ''),
                                'service': row.get('Service', ''),
                                'mode': row.get('Mode', ''),
                                'alpha_tag': row.get('Alpha Tag', '')
                            })
            
            # Load custom airport file if it exists (user-added airports)
            if os.path.exists(custom_airport_file):
                try:
                    with open(custom_airport_file, 'r') as f:
                        reader = csv.DictReader(f)
                        custom_count = 0
                        
                        for row in reader:
                            airport_code = row.get('Airport', '')
                            if airport_code and airport_code != 'COMMON':
                                if airport_code not in airport_data:
                                    airport_data[airport_code] = {
                                        'code': airport_code,
                                        'frequencies': [],
                                        'lat': None,
                                        'lon': None
                                    }
                                
                                airport_data[airport_code]['frequencies'].append({
                                    'freq': row.get('Frequency Output', '0'),
                                    'description': row.get('Description', ''),
                                    'service': row.get('Service', ''),
                                    'mode': row.get('Mode', ''),
                                    'alpha_tag': row.get('Alpha Tag', '')
                                })
                                custom_count += 1
                        
                        if custom_count > 0:
                            print(f"[OK] Loaded {custom_count} custom airport frequencies")
                except Exception as e:
                    print(f"[WARN] Error loading custom airport file: {e}")
            
            # Add approximate coordinates for major Minnesota airports
            airport_coords = {
                'KMSP': (44.8848, -93.2223),  # Minneapolis-St. Paul
                'KDLH': (46.8420, -92.1936),  # Duluth
                'KRST': (43.9083, -92.5000),  # Rochester
                'KSTC': (45.5466, -94.0596),  # St. Cloud
                'KFCM': (44.8272, -93.4571),  # Flying Cloud
                'KMIC': (45.0620, -93.3539),  # Crystal
                'KANE': (45.1450, -93.2113),  # Anoka County
                'KSGS': (44.8233, -93.1457),  # South St. Paul
                'KBRD': (46.3983, -94.1381),  # Brainerd Lakes
                'KHZX': (46.6188, -93.3098),  # Isedor Iverson/McGregor
                'KLXL': (45.9493, -94.3450),  # Little Falls/Morrison County
                'KPWC': (46.7045, -94.3699),  # Pine River Regional
                'KAIT': (46.5481, -93.6770),  # Aitkin Municipal (Steve Kurtz)
                'Y49': (47.1595, -94.6453),   # Walker Municipal
                'KOWA': (44.1234, -93.2606),  # Owatonna Degner Regional
                'KAUM': (43.6650, -92.9344),  # Austin Municipal
                'KGPZ': (47.2111, -93.5098),  # Grand Rapids
                'KBJI': (47.5094, -94.9347),  # Bemidji
                'KINL': (48.5656, -93.4022),  # Falls International-Einarson Field
                'KMKT': (44.2216, -93.9187),  # Mankato
                'KAEL': (43.6815, -93.3676),  # Albert Lea
                'KONA': (44.0797, -91.7093),  # Winona
                'KRWF': (44.5472, -95.0825),  # Redwood Falls
                'KTVF': (48.0656, -96.1850),  # Thief River Falls
                '7Y3':  (46.8272, -94.5068),  # Backus Municipal
                'KSEZ': (34.8486, -111.7884), # Sedona (AZ)
                'KAXN': (45.8663, -95.3947),  # Alexandria Regional/Chandler Field
                '8MN3': (46.5958, -94.2200),  # Breezy Point (private)
                'KPNM': (45.5599, -93.6082),  # Princeton Municipal
                '18Y':  (45.7725, -93.6322),  # Milaca Municipal
                'KSAZ': (46.3809, -94.8066),  # Staples Municipal
            }
            
            # Calculate distances and filter by radius
            for code, data in airport_data.items():
                if code in airport_coords:
                    apt_lat, apt_lon = airport_coords[code]
                    data['lat'] = apt_lat
                    data['lon'] = apt_lon
                    
                    # Calculate distance in nautical miles
                    distance_mi = self.calculate_distance(lat, lon, apt_lat, apt_lon)
                    distance_nm = distance_mi * 0.868976  # Convert to nautical miles
                    
                    if distance_nm <= radius_nm:
                        data['distance_nm'] = distance_nm
                        data['distance_mi'] = distance_mi
                        data['bearing'] = self.calculate_bearing(lat, lon, apt_lat, apt_lon)
                        airports.append(data)
            
            # Sort by distance
            airports.sort(key=lambda x: x.get('distance_nm', 999))
            print(f"[OK] Found {len(airports)} airports within {radius_nm}nm")
                    
        except Exception as e:
            print(f"[WARN] Error fetching nearby airports: {e}")
        
        return airports

    def start_gps(self):
        """Start GPS monitoring"""
        print("[OK] GPS Worker started")
        # Skip demo fallback if we already seeded the UI with a saved position.
        self.gps_worker = GPSWorker(self.on_gps_update,
                                     send_demo_on_failure=not self.has_saved_state,
                                     status_callback=self.on_gps_status)
        self.gps_worker.start()

    def on_gps_status(self, info):
        """Show how the wait for a fix is going: the header label and the GPS
        tab's satellite count, so a receiver that sees no sky and one that is
        unplugged stop looking the same on screen. Called from the GPS worker
        thread, so the widget updates go to the main thread."""
        state = info.get('state')
        if state == 'waiting':
            used, seen = info.get('satellites_used', 0), info.get('satellites_seen', 0)
            text, color, sats = f"GPS: Waiting for fix ({used}/{seen} sats)", self.p.amber, f"{used}/{seen}"
        elif state == 'silent':
            text, color, sats = "GPS: No data from receiver", self.p.red, '--'
        else:
            text, color, sats = "GPS: gpsd unreachable (retrying)", self.p.red, '--'

        def show():
            self.gps_status.config(text=text, foreground=color)
            try:
                self.nav_satellites.config(text=sats)
            except Exception:
                pass

        try:
            self.root.after(0, show)
        except Exception as e:
            print(f"[WARN] Could not schedule GPS status update: {e}")

    def on_gps_update(self, gps_data):
        """Handle GPS data updates - MANUAL REFRESH mode (performance optimized)
        This is called from GPS worker thread, so schedule all UI updates on main thread"""
        if not gps_data:
            return
        
        # Schedule the actual update on the main thread
        try:
            self.root.after(0, lambda: self._process_gps_update(gps_data))
        except Exception as e:
            print(f"[WARN] Could not schedule GPS update: {e}")
    
    def _process_gps_update(self, gps_data):
        """Process GPS update on main thread (safe for tkinter widget updates)"""
        if gps_data:
            old_lat, old_lon = self.last_lat, self.last_lon
            self.last_lat = gps_data.get('lat', self.last_lat)
            self.last_lon = gps_data.get('lon', self.last_lon)

            # If GPS has drifted far from where data was last loaded, flash the
            # Refresh button to prompt the user. Skip in demo mode and only when
            # we actually have a fix worth trusting (mode >= 2).
            mode = gps_data.get('mode', 0)
            is_demo = gps_data.get('demo', False)
            if gps_data.get('source') == 'elmer':
                # Borrowed, and said to be. Deliberately not one of the two
                # sources the UDP packet calls its own: this position is
                # ELMER's own answer, and handing it back as though it were
                # TowerWitch's fix would be the suite talking to itself.
                self.position_source = 'elmer'
                self.elmer_words = gps_data.get('elmer_words') or 'ELMER'
                self.last_speed = None
                self.is_vehicle_speed = False
            if not is_demo and mode >= 2 and gps_data.get('source') != 'elmer':
                self.position_source = 'gps'
                speed = gps_data.get('speed')
                self.last_speed = float(speed) if speed is not None else None
                self.is_vehicle_speed = bool(self.last_speed and self.last_speed >= 2.0)
                drift = self.calculate_distance(self.data_lat, self.data_lon,
                                                 self.last_lat, self.last_lon)
                if drift > self.stale_threshold_miles:
                    if self.auto_refresh and not self._refresh_running:
                        print(f"[INFO] {drift:.1f} mi from where data was loaded - refreshing")
                        self.refresh_all_data()
                    else:
                        self._start_refresh_flash()
                else:
                    self._stop_refresh_flash()
            
            # Calculate how far we've moved (for display purposes only)
            distance_moved = self.calculate_distance(old_lat, old_lon, 
                                                     self.last_lat, self.last_lon)
            
            # Check if this is first real GPS data (moving from demo default)
            is_first_real_gps = (old_lat == 44.9778 and old_lon == -93.2650) and not gps_data.get('demo', False)
            
            if is_first_real_gps:
                print(f"[INFO] First real GPS position: {self.last_lat:.6f}, {self.last_lon:.6f}")
                print("[INFO] Click 'Refresh Data' button to load data for your location")
            
            # MANUAL REFRESH MODE - only update GPS display, no automatic data loading
            # User must click "Refresh Data" button to update tower/repeater data
            
            # Always update GPS display (lightweight operation)
            self.update_gps_display(gps_data)
            
            # Update grid display when position changes
            if distance_moved > 0.001:  # Update grid if moved even slightly
                self.root.after(0, self.update_grid_display)

            # Update status with GPS mode indication
            mode = gps_data.get('mode', 0)
            is_demo = gps_data.get('demo', False)
            sats = gps_data.get('satellites_used', 0)
            
            if gps_data.get('source') == 'elmer':
                # Borrowed, and the line says whose. Amber rather than green:
                # it is a position and it is not this receiver's, and the
                # difference matters when somebody is deciding whether to
                # trust the nearest-site list under it.
                self.gps_status.config(
                    text="Position: %s" % (gps_data.get('elmer_words') or "from ELMER"),
                    foreground=self.p.amber)
            elif is_demo:
                status_text = "GPS: DEMO MODE (Minneapolis)"
                self.gps_status.config(text=status_text, foreground=self.p.amber)  # Orange for demo
            elif mode >= 3:
                self.gps_status.config(text=f"GPS: 3D Fix ({sats} sats)", foreground=self.p.green)  # Green
            elif mode == 2:
                self.gps_status.config(text=f"GPS: 2D Fix ({sats} sats)", foreground=self.p.amber)  # Yellow
            else:
                self.gps_status.config(text=f"GPS: No Fix ({sats} sats)", foreground=self.p.red)  # Red

            # One line every 30 s with the whole picture, so the log shows
            # where the vehicle was and what the receiver said without a
            # thousand grid lines to read through.
            now = time.monotonic()
            if not is_demo and mode >= 2 and now - self._last_gps_heartbeat >= 30:
                self._last_gps_heartbeat = now
                mph = (gps_data.get('speed') or 0.0) * 2.23694
                track = gps_data.get('track')
                heading = f"{track:.0f}\u00b0" if track is not None else "---\u00b0"
                drift = self.calculate_distance(self.data_lat, self.data_lon,
                                                 self.last_lat, self.last_lon)
                print(f"[GPS] {self.last_lat:.6f},{self.last_lon:.6f} {mph:.0f} mph {heading} "
                      f"mode {mode} {sats} sats, {drift:.1f} mi from loaded data")

    def update_gps_display(self, gps_data=None):
        """Update GPS data display"""
        if not gps_data:
            # Default GPS data (altitude in meters)
            gps_data = {
                'lat': self.last_lat,
                'lon': self.last_lon,
                'alt': 260.0,  # meters
                'time': datetime.now().isoformat(),
                'mode': 3,
                'satellites_used': 8
            }

        # Clear existing GPS data
        for item in self.gps_tree.get_children():
            self.gps_tree.delete(item)

        # Convert altitude from meters to feet
        # GPS provides altitude in meters (typically HAE - Height Above Ellipsoid)
        # Note: True MSL requires geoid correction, but HAE is close enough for amateur radio use
        alt_meters = gps_data.get('alt', 0)
        alt_feet = alt_meters * 3.28084
        
        # Check if in demo mode
        is_demo = gps_data.get('demo', False)

        # Add GPS data rows
        gps_items = [
            ('Latitude', f"{gps_data.get('lat', 0):.6f}", '°'),
            ('Longitude', f"{gps_data.get('lon', 0):.6f}", '°'),
            ('Altitude', f"{alt_feet:.1f}", 'ft MSL'),
            ('Nearest Town', self.nearest_town, ''),
            ('Fix Mode', str(gps_data.get('mode', 0)) if not is_demo else 'DEMO', 'D' if not is_demo else ''),
            ('Satellites', str(gps_data.get('satellites_used', 0)), ''),
            ('Time', gps_data.get('time', ''), ''),
        ]
        
        # Add warning row if in demo mode
        if is_demo:
            gps_items.insert(0, ('WARNING', 'USING DEMO DATA', '[Minneapolis]'))

        for prop, value, unit in gps_items:
            self.gps_tree.insert('', 'end', values=(prop, value, unit))
        
        # Update Navigation Dashboard
        try:
            # Fix Status
            mode = gps_data.get('mode', 0)
            if is_demo:
                self.nav_fix_status.config(text="DEMO MODE", foreground=self.p.amber)
            elif mode >= 3:
                self.nav_fix_status.config(text="3D FIX", foreground=self.p.green)
            elif mode == 2:
                self.nav_fix_status.config(text="2D FIX", foreground=self.p.amber)
            else:
                self.nav_fix_status.config(text="NO FIX", foreground=self.p.red)
            
            # Satellites
            sats = gps_data.get('satellites_used', 0)
            self.nav_satellites.config(text=str(sats))
            
            # Speed (convert m/s to mph)
            speed_ms = gps_data.get('speed', 0)
            speed_mph = speed_ms * 2.23694
            self.nav_speed.config(text=f"{speed_mph:.1f} mph")
            
            # Heading (track)
            heading = gps_data.get('track', None)
            if heading is not None:
                # Convert heading to cardinal direction
                directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
                idx = int((heading + 22.5) / 45) % 8
                self.nav_heading.config(text=f"{heading:.0f}° {directions[idx]}")
            else:
                self.nav_heading.config(text="---°")
            
            # Altitude
            self.nav_altitude.config(text=f"{alt_feet:.0f} ft")
            
            # Last Update
            time_now = datetime.now().strftime("%H:%M:%S")
            self.nav_last_update.config(text=time_now)
            
        except Exception as e:
            print(f"[WARN] Error updating navigation dashboard: {e}")

    def update_datetime(self):
        """Update date/time display"""
        now = datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M:%S")
        self.datetime_label.config(text=time_str)

        # Schedule next update
        self.root.after(1000, self.update_datetime)

    def toggle_night_mode_key(self):
        """Toggle night mode via keyboard (F12)"""
        self.night_mode_var.set(not self.night_mode_var.get())
        self.toggle_night_mode()

    def toggle_night_mode(self):
        """Night is the same look in red; everything reads its colour from
        the palette, so swapping the palette is the whole change."""
        self.night_mode_on = self.night_mode_var.get()
        self.p = tw_theme.NIGHT if self.night_mode_on else tw_theme.DAY
        print(f"[OK] {self.p.name.capitalize()} palette")
        tw_theme.apply(self.style, self.root, self.p)
        self.update_treeview_colors()
        self._recolor_status()
        self.root.update_idletasks()

    def _recolor_status(self):
        """Re-read the state labels' colour from the palette after a swap."""
        try:
            text = self.gps_status.cget('text')
            if '3D Fix' in text:
                self.gps_status.config(foreground=self.p.green)
            elif 'No Fix' in text or 'No data' in text or 'unreachable' in text:
                self.gps_status.config(foreground=self.p.red)
            else:
                self.gps_status.config(foreground=self.p.amber)
            fix = self.nav_fix_status.cget('text')
            self.nav_fix_status.config(foreground=self.p.green if 'FIX' in fix and 'NO' not in fix
                                       else self.p.red if 'NO' in fix else self.p.amber)
        except Exception:
            pass

    def update_treeview_colors(self):
        """Have every table take the palette again after a swap."""
        treeviews = [
            self.gps_tree,
            self.grid_tree,
            self.armer_tree,
            self.interop_tree,
            self.skywarn_tree,
            self.aviation_nearby_tree,
            self.aviation_emergency_tree,
            self.aviation_common_tree,
            self.aviation_center_tree
        ]
        
        # Add amateur band trees
        amateur_tree_names = ['amateur_10m_tree', 'amateur_6m_tree', 'amateur_2m_tree', 
                             'amateur_125m_tree', 'amateur_70cm_tree', 'amateur_simplex_tree']
        for tree_name in amateur_tree_names:
            if hasattr(self, tree_name):
                treeviews.append(getattr(self, tree_name))
        
        for tree in treeviews:
            try:
                tree.configure(style='Treeview')
                # Force style reapplication
                tree.update_idletasks()
            except:
                pass

    def refresh_all_data(self):
        """Refresh all data from local CSV sources (MANUAL REFRESH MODE).

        CSV-only by default. The Radio Reference API is opt-in: if the local
        data has no results for the current area, the user is prompted to try
        the API (only when a key is configured in towerwitch_config.ini).
        """
        print("[OK] Refreshing all data for current location...")
        print(f"[INFO] Current position: {self.last_lat:.6f}, {self.last_lon:.6f}")
        self._refresh_running = True

        # Data is now in sync with the current GPS position, stop any flashing.
        self.data_lat = self.last_lat
        self.data_lon = self.last_lon
        self._stop_refresh_flash()

        # Save the current status so we can restore it after refresh
        prev_status = self.gps_status.cget('text')
        prev_color = self.gps_status.cget('foreground')
        self.gps_status.config(text="Refreshing data...", foreground=self.p.amber)

        def do_refresh():
            try:
                # Load everything from local CSVs (load_static_data covers
                # ARMER, Skywarn, amateur bands, simplex, DMR/D-Star, Fusion,
                # NOAA, interop, aviation, and grid display).
                self.root.after(0, self.load_static_data)
                self.root.after(0, self.update_gps_display)

                # Look up nearest town in a separate thread so a slow Nominatim
                # response can't delay the data refresh or hang the UI.
                threading.Thread(
                    target=lambda: self.get_nearest_town(self.last_lat, self.last_lon),
                    daemon=True,
                ).start()

                # Persist state
                self.save_state()
                print("[OK] Data refresh complete (CSV-only)")
            except Exception as e:
                print(f"[ERROR] Refresh failed: {e}")
            finally:
                # Always restore the status label and check for empty results.
                # Scheduled via after(0) so it runs after the data loaders above.
                self.root.after(0, lambda: self._on_refresh_complete(prev_status, prev_color))

        threading.Thread(target=do_refresh, daemon=True).start()

    def _on_refresh_complete(self, prev_status, prev_color):
        """Restore the status label and, if local data is empty for this area,
        offer to fetch from the Radio Reference API."""
        self._refresh_running = False
        try:
            self.gps_status.config(text=prev_status, foreground=prev_color)
        except Exception:
            pass

        # Detect "no local data for this area" by checking the location-sensitive
        # trees. If all three are empty, the CSVs likely don't cover this region.
        try:
            armer_empty = len(self.armer_tree.get_children()) == 0
            skywarn_empty = len(self.skywarn_tree.get_children()) == 0
            amateur_2m = getattr(self, 'amateur_2m_tree', None)
            amateur_empty = (amateur_2m is None) or (len(amateur_2m.get_children()) == 0)
        except Exception:
            return

        if not (armer_empty and skywarn_empty and amateur_empty):
            return  # We have data — nothing to prompt about

        has_api_key = bool(self.api_key) and self.api_key != 'your_api_key_here'
        if has_api_key:
            ok = messagebox.askyesno(
                "No local data for this area",
                "Local CSV files returned no repeaters for your current "
                "location.\n\nFetch live data from the Radio Reference API now?",
                parent=self.root,
            )
            if ok:
                self._fetch_from_api_async()
        else:
            messagebox.showinfo(
                "No local data for this area",
                "Local CSV files returned no repeaters for your current "
                "location.\n\nTo enable live lookups, set "
                "'radio_reference_key' in towerwitch_config.ini.",
                parent=self.root,
            )

    def _start_refresh_flash(self):
        """Begin flashing the Refresh button to signal data is stale."""
        if self._flash_after_id is not None:
            return  # Already flashing
        self._flash_on = False
        self._tick_refresh_flash()

    def _stop_refresh_flash(self):
        """Stop flashing the Refresh button and restore its normal appearance."""
        if self._flash_after_id is not None:
            try:
                self.root.after_cancel(self._flash_after_id)
            except Exception:
                pass
            self._flash_after_id = None
        self._flash_on = False
        try:
            self.refresh_btn.config(text="Refresh Data", style='TButton')
        except Exception:
            pass

    def _tick_refresh_flash(self):
        """Toggle the button's text/style. Reschedules itself every 700ms."""
        try:
            self._flash_on = not self._flash_on
            if self._flash_on:
                self.refresh_btn.config(text="⚠ Refresh Data (stale)", style='Stale.TButton')
            else:
                self.refresh_btn.config(text="Refresh Data", style='TButton')
        except Exception:
            return
        self._flash_after_id = self.root.after(700, self._tick_refresh_flash)

    def _fetch_from_api_async(self):
        """Opt-in: fetch live data from Radio Reference in a background thread."""
        prev_status = self.gps_status.cget('text')
        prev_color = self.gps_status.cget('foreground')
        self.gps_status.config(text="Fetching from API...", foreground=self.p.amber)

        def do_api_fetch():
            try:
                print("[INFO] Fetching live data from Radio Reference API...")
                skywarn_live = self.radio_api.get_skywarn_repeaters(
                    self.last_lat, self.last_lon, radius=100)
                amateur_live = self.radio_api.get_amateur_repeaters(
                    self.last_lat, self.last_lon, radius=50)
                self.root.after(0, lambda: self._update_with_live_data(skywarn_live, amateur_live))
            except Exception as e:
                print(f"[ERROR] API fetch failed: {e}")
            finally:
                self.root.after(0, lambda: self.gps_status.config(text=prev_status, foreground=prev_color))

        threading.Thread(target=do_api_fetch, daemon=True).start()

    def _fetch_and_update_live_repeaters(self):
        """Fetch live repeater data from Radio Reference API and update displays"""
        try:
            print("[INFO] Fetching live repeater data from API...")
            
            # Fetch Skywarn repeaters (100 mile radius)
            skywarn_live = self.radio_api.get_skywarn_repeaters(
                self.last_lat, self.last_lon, radius=100)
            
            # Fetch Amateur repeaters (50 mile radius)
            amateur_live = self.radio_api.get_amateur_repeaters(
                self.last_lat, self.last_lon, radius=50)
            
            # Update ARMER (always from CSV)
            self.root.after(0, self.load_armer_data)
            
            # Update displays with API data on main thread
            if skywarn_live:
                print(f"[OK] Found {len(skywarn_live)} Skywarn repeaters")
                self.root.after(0, lambda: self._populate_skywarn_with_data(skywarn_live))
            else:
                print("[INFO] No Skywarn repeaters found, using static data")
                self.root.after(0, self.load_skywarn_data)
            
            if amateur_live:
                print(f"[OK] Found {len(amateur_live)} amateur repeaters")
                self.root.after(0, lambda: self._populate_amateur_with_data(amateur_live))
            else:
                print("[INFO] No amateur repeaters found, using static data")
                self.root.after(0, self.load_amateur_data)
                
        except Exception as e:
            print(f"[ERROR] Failed to fetch live repeater data: {e}")
            # Fall back to static data
            self.root.after(0, self.load_armer_data)
            self.root.after(0, self.load_skywarn_data)
            self.root.after(0, self.load_amateur_data)

    def _update_with_live_data(self, skywarn_data, amateur_data):
        """Update displays with live data from Radio Reference"""
        if skywarn_data:
            print(f"[OK] Updating with {len(skywarn_data)} live Skywarn repeaters")
            self._populate_skywarn_with_data(skywarn_data)
        
        if amateur_data:
            print(f"[OK] Updating with {len(amateur_data)} live amateur repeaters")
            self._populate_amateur_with_data(amateur_data)
        
        # Restore GPS status
        self.gps_status.config(text="GPS: Live API Data")
        
        if not skywarn_data and not amateur_data:
            # No live data, fall back to static
            self.load_static_data()

    def _populate_skywarn_with_data(self, repeaters):
        """Populate Skywarn tree with data"""
        # Clear existing
        for item in self.skywarn_tree.get_children():
            self.skywarn_tree.delete(item)
        
        # Add repeaters
        for rep in repeaters:
            distance = self.calculate_distance(
                self.last_lat, self.last_lon, 
                rep.get('lat', 0), rep.get('lon', 0))
            bearing = self.calculate_bearing(
                self.last_lat, self.last_lon,
                rep.get('lat', 0), rep.get('lon', 0))
            
            values = (
                rep.get('call', 'N0CALL'),
                rep.get('location', 'Unknown'),
                f"{rep.get('output', '0.0')} MHz",
                rep.get('tone', ''),
                f"{distance:.1f} mi",
                f"{bearing:.0f}°"
            )
            
            item = self.skywarn_tree.insert('', 'end', values=values)
            
            # Distance indicators
            if distance < 25:
                self.skywarn_tree.set(item, 'Call Sign', f"[NEAR] {rep.get('call', 'N0CALL')}")
            elif distance < 75:
                self.skywarn_tree.set(item, 'Call Sign', f"[MID] {rep.get('call', 'N0CALL')}")
            else:
                self.skywarn_tree.set(item, 'Call Sign', f"[FAR] {rep.get('call', 'N0CALL')}")

    def _populate_amateur_with_data(self, repeaters):
        """Populate amateur band trees with live data"""
        # Sort repeaters by band
        bands = {'2m': [], '70cm': []}
        
        for rep in repeaters:
            freq = float(rep.get('output', '0'))
            if 144 <= freq <= 148:
                bands['2m'].append(rep)
            elif 420 <= freq <= 450:
                bands['70cm'].append(rep)
        
        # Update each band
        for band, reps in bands.items():
            if reps:
                self.populate_band_tree(reps, band)

    def run(self):
        """Start the application"""
        try:
            # Apply colored tabs after everything is created
            self.root.after(100, self.apply_tab_colors)

            # Reveal the window now that all setup is complete (we hid it in
            # __init__ to avoid a default-geometry flash before state restore).
            self.root.deiconify()

            # Bring window to front and focus it
            self.root.lift()
            self.root.attributes('-topmost', True)
            self.root.after(1000, lambda: self.root.attributes('-topmost', False))

            print("[OK] TowerWitch Tkinter version started!")
            print(f"[INFO] Window geometry: {self.root.geometry()}")
            print("[INFO] Starting main event loop...")

            # Start the main loop
            self.root.mainloop()

        except Exception as e:
            print(f"[ERROR] Error in main loop: {e}")
            import traceback
            traceback.print_exc()

class _StampedLog:
    """Stands in for stdout or stderr: every line goes on to the original
    stream and to logs/towerwitch.log, stamped with the clock time. The file
    outlives a login (~/.xsession-errors does not) and stamped lines lay
    against journalctl and gpsd. Rotates at 2 MB, keeps three."""
    _file = None
    _lock = threading.Lock()
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs', 'towerwitch.log')
    max_bytes = 2_000_000
    keep = 3

    def __init__(self, stream):
        self._stream = stream
        self._at_line_start = True
        if _StampedLog._file is None:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                _StampedLog._file = open(self.path, 'a', buffering=1)
            except OSError as e:
                stream.write(f"[WARN] No log file at {self.path}: {e}\n")

    def write(self, text):
        with self._lock:
            out = []
            for piece in text.splitlines(keepends=True):
                if self._at_line_start:
                    out.append(datetime.now().strftime('%H:%M:%S '))
                out.append(piece)
                self._at_line_start = piece.endswith('\n')
            stamped = ''.join(out)
            self._stream.write(stamped)
            f = _StampedLog._file
            if f is not None:
                try:
                    f.write(stamped)
                    if f.tell() > self.max_bytes:
                        self._rotate()
                except Exception:
                    pass

    def _rotate(self):
        _StampedLog._file.close()
        for n in range(self.keep, 0, -1):
            newer = self.path if n == 1 else f"{self.path}.{n - 1}"
            if os.path.exists(newer):
                os.replace(newer, f"{self.path}.{n}")
        _StampedLog._file = open(self.path, 'a', buffering=1)

    def flush(self):
        self._stream.flush()
        if _StampedLog._file is not None:
            try:
                _StampedLog._file.flush()
            except Exception:
                pass

    def fileno(self):
        return self._stream.fileno()

    def isatty(self):
        return self._stream.isatty()


def _log_startup_event(message):
    """Append a startup diagnostic event to /tmp/towerwitch_startup.log.
    Used to debug duplicate-instance reports. Each launch appends one line
    with timestamp, pid, ppid, and argv so we can see exactly what fired."""
    try:
        log_path = os.path.join(tempfile.gettempdir(), 'towerwitch_startup.log')
        with open(log_path, 'a') as f:
            f.write(f"{datetime.now().isoformat()} pid={os.getpid()} "
                    f"ppid={os.getppid()} argv={sys.argv} -- {message}\n")
    except Exception:
        pass

# Where the Windows lock sits, and how much room the pid is given. Well
# apart, so the one never covers the other.
LOCK_BYTE = 1000
PID_WIDTH = 16


def acquire_single_instance_lock():
    """Acquire an exclusive lock file to prevent a second instance from running.
    Returns the file descriptor (kept open for process lifetime) or None if
    another instance already holds the lock."""
    lock_path = os.path.join(tempfile.gettempdir(), 'towerwitch.lock')
    try:
        # Opened without truncating: on Windows the holder's byte lock sits
        # on the first byte of this file, and coming in with 'w' would try
        # to empty it out from under them. The pid is written after the
        # lock is held, which is the only point at which it is ours to
        # write. r+ needs the file to exist; the first run makes it.
        try:
            lock_fd = open(lock_path, 'r+')
        except FileNotFoundError:
            lock_fd = open(lock_path, 'w')
        if fcntl is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            # Windows locks a byte *range*, and a locked byte cannot be read
            # by anybody else - so the lock goes on a byte well past the end
            # of the pid rather than on the pid itself. main() prints who is
            # holding it when a second copy is refused, and locking the pid
            # would make that message read "held by pid=?" for ever. Locking
            # past the end of the file is allowed.
            lock_fd.seek(LOCK_BYTE)
            msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
        # Padded, not truncated: truncating would cut away the byte Windows
        # has just locked, and a fixed width stops the tail of an older,
        # longer pid showing through behind a shorter one.
        lock_fd.seek(0)
        lock_fd.write(str(os.getpid()).ljust(PID_WIDTH))
        lock_fd.flush()
        _log_startup_event("lock acquired")
        return lock_fd
    except (OSError, IOError) as e:
        _log_startup_event(f"lock REJECTED ({e})")
        return None

def main():
    """Main entry point"""
    _log_startup_event("main() entered")
    sys.stdout = _StampedLog(sys.stdout)
    sys.stderr = _StampedLog(sys.stderr)
    print(f"==== TowerWitch {datetime.now():%Y-%m-%d %H:%M:%S} ====")
    print(f"[BOOT] pid={os.getpid()} ppid={os.getppid()} argv={sys.argv}")

    lock_fd = acquire_single_instance_lock()
    if lock_fd is None:
        try:
            with open(os.path.join(tempfile.gettempdir(), 'towerwitch.lock')) as f:
                holder = f.read().strip()
        except Exception:
            holder = '?'
        print(f"[ERROR] TowerWitch is already running (held by pid={holder}). Exiting.")
        sys.exit(1)

    root = tk.Tk()
    app = TowerWitchTkinter(root)

    try:
        app.run()
    except KeyboardInterrupt:
        print("\n[OK] TowerWitch shutting down...")
    finally:
        if app.gps_worker:
            app.gps_worker.stop()

if __name__ == "__main__":
    main()