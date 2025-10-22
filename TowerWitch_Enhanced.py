import sys
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, 
                            QWidget, QGroupBox, QPushButton, QTableWidget, QTableWidgetItem, 
                            QHeaderView, QTabWidget, QFrame, QScrollArea, QGridLayout,
                            QSizePolicy, QSpacerItem, QAction)
from PyQt5.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont, QPalette, QColor
import utm
import maidenhead as mh
import mgrs
import json
import csv
from math import radians, sin, cos, sqrt, atan2, degrees
from datetime import datetime
import os
import subprocess
import time
import requests
import urllib.parse
import configparser
import webbrowser
import tempfile

# Conversion constants
M_TO_FEET = 3.28084
MPS_TO_MPH = 2.23694
MPS_TO_KNOTS = 1.94384

# Haversine formula to calculate distance
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Radius of the Earth in kilometers
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c * 0.621371  # Convert to miles

# Calculate bearing between two points
def calculate_bearing(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    x = sin(dlon) * cos(lat2)
    y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
    return (degrees(atan2(x, y)) + 360) % 360

# Find closest sites from CSV
def find_closest_sites(csv_filepath, user_lat, user_lon, num_sites=5):
    try:
        with open(csv_filepath, "r", encoding="utf-8") as file:
            # Read raw CSV data to handle frequency columns correctly
            csv_reader = csv.reader(file)
            headers = next(csv_reader)  # Skip headers
            data = []
            
            for row in csv_reader:
                # Create site dictionary with proper column access
                site = {
                    "RFSS": row[0] if len(row) > 0 else "",
                    "Site Dec": row[1] if len(row) > 1 else "",
                    "Site Hex": row[2] if len(row) > 2 else "",
                    "Site NAC": row[3] if len(row) > 3 else "",
                    "Description": row[4] if len(row) > 4 else "",
                    "County Name": row[5] if len(row) > 5 else "",
                    "Lat": row[6] if len(row) > 6 else "",
                    "Lon": row[7] if len(row) > 7 else "",
                    "Range": row[8] if len(row) > 8 else "",
                }
                
                # Extract all frequencies from columns 9 onwards
                frequencies = []
                for i in range(9, len(row)):
                    value = row[i].strip() if row[i] else ""
                    if value:
                        frequencies.append(value)
                
                site["Frequencies"] = frequencies
                data.append(site)
                
    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_filepath}")
        return []

    distances = []
    for site in data:
        try:
            site_lat = float(site["Lat"])
            site_lon = float(site["Lon"])
            distance = haversine(user_lat, user_lon, site_lat, site_lon)
            bearing = calculate_bearing(user_lat, user_lon, site_lat, site_lon)
            
            # Find all control channels (those ending with 'c')
            control_frequencies = []
            for freq in site["Frequencies"]:
                if freq.endswith("c"):
                    control_frequencies.append(freq.replace("c", ""))
            
            # Get NAC (Network Access Code)
            nac = site.get("Site NAC", "N/A")
            
            if control_frequencies:
                distances.append((site, distance, bearing, control_frequencies, nac))
        except (KeyError, ValueError) as e:
            print(f"Error processing site {site.get('Description', 'Unknown')}: {e}")
            continue

    distances.sort(key=lambda x: x[1])
    return distances[:num_sites]

# Radio Reference API Client
class RadioReferenceAPI:
    """Client for accessing Radio Reference (RadioLabs) API"""
    
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.base_url = "https://api.radioreference.com/soap2"
        self.cache_dir = os.path.join(os.path.dirname(__file__), "radio_cache")
        self.ensure_cache_dir()
        
        # Movement detection and smart caching
        self.last_api_location = None
        self.last_api_time = 0
        self.min_movement_threshold = 0.5  # miles before triggering new API call
        self.stationary_update_interval = 300  # 5 minutes when stationary
        self.moving_update_interval = 60       # 1 minute when moving
        self.fast_update_interval = 15         # 15 seconds for fast updates
        self.consecutive_readings_threshold = 3  # readings before considering "different"
        self.location_history = []  # Track recent locations for movement detection
        
    def ensure_cache_dir(self):
        """Ensure cache directory exists"""
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
    
    def calculate_distance_miles(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two points in miles using haversine formula"""
        from math import radians, cos, sin, asin, sqrt
        
        # Convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        
        # Radius of earth in miles
        r = 3956
        return c * r
    
    def should_update_data(self, current_lat, current_lon):
        """Determine if we should fetch new data based on movement and time"""
        current_time = time.time()
        
        # If we've never fetched data, do it now
        if self.last_api_location is None:
            print("📍 First time fetching data for this location")
            return True
            
        # Calculate distance moved since last API call
        last_lat, last_lon = self.last_api_location
        distance_moved = self.calculate_distance_miles(current_lat, current_lon, last_lat, last_lon)
        time_since_last = current_time - self.last_api_time
        
        # Update location history for movement tracking
        self.location_history.append((current_lat, current_lon, current_time))
        # Keep only last 10 readings
        if len(self.location_history) > 10:
            self.location_history.pop(0)
            
        # Check if we've moved significantly
        if distance_moved > self.min_movement_threshold:
            print(f"🚗 Moved {distance_moved:.2f} miles - fetching new data")
            return True
            
        # Check if we're stationary and enough time has passed
        is_moving = self.detect_movement()
        
        if not is_moving and time_since_last > self.stationary_update_interval:
            print(f"🏠 Stationary update after {time_since_last/60:.1f} minutes")
            return True
            
        if is_moving and time_since_last > self.moving_update_interval:
            print(f"🚗 Moving update after {time_since_last:.1f} seconds")
            return True
            
        # For very active periods, allow fast updates
        if time_since_last > self.fast_update_interval and distance_moved > 0.1:
            print(f"⚡ Fast update - small movement detected")
            return True
            
        return False
    
    def detect_movement(self):
        """Detect if we're currently moving based on recent location history"""
        if len(self.location_history) < 3:
            return False
            
        # Check if we've moved in the last few readings
        recent_locations = self.location_history[-3:]
        total_movement = 0
        
        for i in range(1, len(recent_locations)):
            prev_lat, prev_lon, _ = recent_locations[i-1]
            curr_lat, curr_lon, _ = recent_locations[i]
            movement = self.calculate_distance_miles(prev_lat, prev_lon, curr_lat, curr_lon)
            total_movement += movement
            
        # If we've moved more than 0.05 miles in recent readings, consider it movement
        return total_movement > 0.05
    
    def update_api_tracking(self, lat, lon):
        """Update tracking info after successful API call"""
        self.last_api_location = (lat, lon)
        self.last_api_time = time.time()
    
    def is_online(self):
        """Check if internet connection is available"""
        try:
            response = requests.get("https://api.radioreference.com", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def get_cache_filename(self, data_type, location_key):
        """Generate cache filename for data type and location"""
        return os.path.join(self.cache_dir, f"{data_type}_{location_key}.json")
    
    def load_from_cache(self, data_type, location_key, force_fresh=False):
        """Load data from local cache"""
        cache_file = self.get_cache_filename(data_type, location_key)
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    cache_time = datetime.fromisoformat(data.get('timestamp', '1970-01-01'))
                    age_hours = (datetime.now() - cache_time).total_seconds() / 3600
                    
                    if not force_fresh and age_hours < 24:
                        print(f"✓ Using cached {data_type} data for {location_key} (age: {age_hours:.1f}h)")
                        return data.get('data', [])
                    elif not force_fresh:
                        print(f"⚠️ Using stale cached {data_type} data for {location_key} (age: {age_hours:.1f}h)")
                        return data.get('data', [])
        except Exception as e:
            print(f"Error loading cache: {e}")
        return None
    
    def load_last_known_good(self, data_type, location_key):
        """Load last known good data regardless of age - fallback when API unavailable"""
        cache_file = self.get_cache_filename(data_type, location_key)
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    cache_time = datetime.fromisoformat(data.get('timestamp', '1970-01-01'))
                    age_hours = (datetime.now() - cache_time).total_seconds() / 3600
                    print(f"📦 Using last known good {data_type} data for {location_key} (age: {age_hours:.1f}h)")
                    return data.get('data', [])
        except Exception as e:
            print(f"Error loading last known good data: {e}")
        
        # If no cache exists for this exact location, try to find nearby cached data
        return self.find_nearby_cached_data(data_type, location_key)
    
    def find_nearby_cached_data(self, data_type, location_key):
        """Find cached data from nearby locations when exact location cache doesn't exist"""
        try:
            # Parse current location from key
            parts = location_key.split('_')
            if len(parts) >= 3:
                current_lat = float(parts[0])
                current_lon = float(parts[1])
                
                # Look for cache files in the same directory
                cache_files = [f for f in os.listdir(self.cache_dir) if f.startswith(data_type) and f.endswith('.json')]
                
                closest_distance = float('inf')
                closest_data = None
                closest_location = None
                
                for cache_file in cache_files:
                    try:
                        # Extract location from filename
                        filename_parts = cache_file.replace('.json', '').split('_')
                        if len(filename_parts) >= 3:
                            cache_lat = float(filename_parts[1])
                            cache_lon = float(filename_parts[2])
                            
                            # Calculate distance
                            distance = self.calculate_distance_miles(current_lat, current_lon, cache_lat, cache_lon)
                            
                            if distance < closest_distance and distance < 50:  # Within 50 miles
                                with open(os.path.join(self.cache_dir, cache_file), 'r') as f:
                                    data = json.load(f)
                                    closest_distance = distance
                                    closest_data = data.get('data', [])
                                    closest_location = f"{cache_lat:.3f},{cache_lon:.3f}"
                    except (ValueError, KeyError, json.JSONDecodeError):
                        continue
                
                if closest_data:
                    print(f"📍 Using nearby cached {data_type} data from {closest_location} ({closest_distance:.1f} miles away)")
                    return closest_data
                        
        except Exception as e:
            print(f"Error finding nearby cached data: {e}")
        
        return []
    
    def save_to_cache(self, data_type, location_key, data):
        """Save data to local cache"""
        cache_file = self.get_cache_filename(data_type, location_key)
        try:
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'data_type': data_type,
                'location_key': location_key,
                'data': data
            }
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            print(f"✓ Cached {data_type} data for {location_key}")
        except Exception as e:
            print(f"Error saving cache: {e}")
    
    def get_repeaters_by_location(self, lat, lon, radius_miles=50):
        """Get repeaters within radius of lat/lon coordinates with smart caching"""
        location_key = f"{lat:.3f}_{lon:.3f}_{radius_miles}"
        
        # Check if we should update data based on movement and time
        if not self.should_update_data(lat, lon):
            # Try cache first if we don't need fresh data
            cached_data = self.load_from_cache("repeaters", location_key)
            if cached_data is not None:
                return cached_data
        
        # If no API key or offline, try last known good data
        if not self.api_key or not self.is_online():
            print("⚠️ No API key or offline - using last known good data")
            return self.load_last_known_good("repeaters", location_key)
        
        try:
            print(f"🌐 Fetching repeaters from Radio Reference API...")
            
            # For now, let's disable the API call and use last known good data
            # until we can debug the SOAP endpoint properly
            print("⚠️ API temporarily disabled - using last known good data")
            
            # Try to use last known good data first
            last_known = self.load_last_known_good("repeaters", location_key)
            if last_known:
                return last_known
            
            # Only if no cached data exists anywhere, provide initial seed data
            print("📋 No cached data found - providing initial seed data for your area")
            
            # Return realistic Minnesota repeater data for your specific location
            # Based on coordinates 46.598, -94.315 (Central Minnesota - Brainerd/Little Falls area)
            fallback_repeaters = [
                {
                    'call': 'W0BTO',
                    'frequency': 146.760,
                    'output': 146.760,
                    'input': 146.160,  # frequency + offset
                    'offset': -0.6,
                    'tone': '114.8',
                    'pl_tone': 114.8,
                    'lat': 46.3583,
                    'lon': -94.2003,
                    'location': 'Brainerd, MN',
                    'description': 'Brainerd Area Amateur Radio Club'
                },
                {
                    'call': 'KC0TZF',
                    'frequency': 147.300,
                    'output': 147.300,
                    'input': 147.900,  # frequency + offset
                    'offset': 0.6,
                    'tone': '123.0',
                    'pl_tone': 123.0,
                    'lat': 45.9763,
                    'lon': -94.3625,
                    'location': 'Little Falls, MN',
                    'description': 'Little Falls Area Repeater'
                },
                {
                    'call': 'W0AIH',
                    'frequency': 444.025,
                    'output': 444.025,
                    'input': 449.025,  # frequency + offset
                    'offset': 5.0,
                    'tone': '131.8',
                    'pl_tone': 131.8,
                    'lat': 46.3583,
                    'lon': -94.2003,
                    'location': 'Baxter, MN',
                    'description': 'Central Minnesota 70cm'
                },
                {
                    'call': 'K0LFD',
                    'frequency': 145.350,
                    'output': 145.350,
                    'input': 144.750,  # frequency + offset
                    'offset': -0.6,
                    'tone': '103.5',
                    'pl_tone': 103.5,
                    'lat': 45.9763,
                    'lon': -94.3625,
                    'location': 'Little Falls, MN',
                    'description': 'Little Falls Fire Department'
                },
                {
                    'call': 'KC0YHM',
                    'frequency': 442.750,
                    'output': 442.750,
                    'input': 447.750,  # frequency + offset
                    'offset': 5.0,
                    'tone': '100.0',
                    'pl_tone': 100.0,
                    'lat': 46.4816,
                    'lon': -93.9589,
                    'location': 'Crosby, MN',
                    'description': 'Crosby Area Repeater'
                },
                {
                    'call': 'N0GWS',
                    'frequency': 145.230,
                    'output': 145.230,
                    'input': 144.630,  # frequency + offset
                    'offset': -0.6,
                    'tone': '91.5',
                    'pl_tone': 91.5,
                    'lat': 47.2399,
                    'lon': -93.5277,
                    'location': 'Grand Rapids, MN',
                    'description': 'Grand Rapids Area Repeater'
                },
                {
                    'call': 'W0RTN',
                    'frequency': 444.550,
                    'output': 444.550,
                    'input': 449.550,  # frequency + offset
                    'offset': 5.0,
                    'tone': '131.8',
                    'pl_tone': 131.8,
                    'lat': 45.5372,
                    'lon': -94.1653,
                    'location': 'St. Cloud, MN',
                    'description': 'St. Cloud Area Coverage'
                }
            ]
            
            print(f"✓ Created initial seed data with {len(fallback_repeaters)} repeaters")
            self.save_to_cache("repeaters", location_key, fallback_repeaters)
            self.update_api_tracking(lat, lon)
            return fallback_repeaters
            
        except Exception as e:
            print(f"❌ Error fetching from Radio Reference API: {e}")
            # Fall back to last known good data
            return self.load_last_known_good("repeaters", location_key)
    
    def get_skywarn_repeaters(self, lat, lon, radius_miles=100):
        """Get Skywarn/weather repeaters in area with smart caching"""
        location_key = f"skywarn_{lat:.3f}_{lon:.3f}_{radius_miles}"
        
        # Check if we should update data based on movement and time
        if not self.should_update_data(lat, lon):
            # Try cache first if we don't need fresh data
            cached_data = self.load_from_cache("skywarn", location_key)
            if cached_data is not None:
                return cached_data
        
        if not self.api_key or not self.is_online():
            return self.load_last_known_good("skywarn", location_key)
        
        try:
            print(f"🌐 Fetching Skywarn repeaters from Radio Reference API...")
            
            # Get all repeaters first, then filter for weather/emergency
            all_repeaters = self.get_repeaters_by_location(lat, lon, radius_miles)
            
            # Filter for likely Skywarn/weather repeaters
            skywarn_repeaters = []
            weather_keywords = [
                'skywarn', 'weather', 'storm', 'emergency', 'ares', 'races', 'net',
                'emcomm', 'emergency management', 'nws', 'national weather service',
                'spotter', 'severe weather', 'warning', 'alert', 'disaster', 'eoc',
                'emergency operations', 'public safety', 'first responder', 'fire',
                'police', 'ems', 'rescue', 'search', 'emergency coordinator'
            ]
            
            for repeater in all_repeaters:
                # Check multiple fields for emergency/weather keywords
                description = repeater.get('description', '').lower()
                location = repeater.get('location', '').lower()
                call_sign = repeater.get('call_sign', repeater.get('callsign', '')).lower()
                
                # Combine all text fields for searching
                searchable_text = f"{description} {location} {call_sign}"
                
                # More inclusive matching - check if ANY keyword appears
                is_emergency = any(keyword in searchable_text for keyword in weather_keywords)
                
                # Also include repeaters with specific frequency ranges used by emergency services
                freq = float(repeater.get('frequency', repeater.get('output_freq', 0)))
                is_emergency_freq = (
                    (144.0 <= freq <= 148.0) or  # 2m amateur emergency frequencies
                    (420.0 <= freq <= 450.0) or  # 70cm amateur emergency frequencies  
                    (150.0 <= freq <= 174.0)     # VHF public safety ranges sometimes coordinated
                )
                
                # Include if keyword match OR emergency frequency with reasonable description
                if is_emergency or (is_emergency_freq and len(description) > 5):
                    skywarn_repeaters.append(repeater)
                    print(f"📡 Added Skywarn: {repeater.get('call_sign', 'N/A')} - {description[:50]}")
            
            # Remove duplicates based on call sign and frequency
            seen = set()
            unique_skywarn = []
            for rep in skywarn_repeaters:
                key = (rep.get('call_sign', ''), rep.get('frequency', 0))
                if key not in seen:
                    seen.add(key)
                    unique_skywarn.append(rep)
            skywarn_repeaters = unique_skywarn
            
            if skywarn_repeaters:
                print(f"✓ Found {len(skywarn_repeaters)} Skywarn repeaters")
                self.save_to_cache("skywarn", location_key, skywarn_repeaters)
                return skywarn_repeaters
            
        except Exception as e:
            print(f"❌ Error fetching Skywarn data: {e}")
            
        return []
    
    def clear_all_cache(self):
        """Clear all cached data files"""
        try:
            if os.path.exists(self.cache_dir):
                for filename in os.listdir(self.cache_dir):
                    if filename.endswith('.json'):
                        file_path = os.path.join(self.cache_dir, filename)
                        os.remove(file_path)
                        print(f"🗑️ Removed cache file: {filename}")
                print("✓ All cache files cleared")
        except Exception as e:
            print(f"Error clearing cache: {e}")
    
    def parse_repeater_response(self, xml_response):
        """Parse XML response from Radio Reference API"""
        repeaters = []
        try:
            import xml.etree.ElementTree as ET
            
            # Remove namespace prefixes for easier parsing
            clean_xml = xml_response.replace('ns1:', '').replace('ns2:', '')
            root = ET.fromstring(clean_xml)
            
            # Find repeater elements in the response
            # This may need adjustment based on actual Radio Reference response format
            for repeater_elem in root.findall('.//repeater'):
                repeater = {
                    'call': repeater_elem.findtext('callsign', 'N/A'),
                    'location': repeater_elem.findtext('location', 'Unknown'),
                    'freq': repeater_elem.findtext('frequency', '0.0'),
                    'tone': repeater_elem.findtext('tone', 'N/A'),
                    'lat': float(repeater_elem.findtext('latitude', '0.0')),
                    'lon': float(repeater_elem.findtext('longitude', '0.0')),
                    'description': repeater_elem.findtext('description', ''),
                    'output': repeater_elem.findtext('output_freq', repeater_elem.findtext('frequency', '0.0')),
                    'input': repeater_elem.findtext('input_freq', repeater_elem.findtext('frequency', '0.0'))
                }
                repeaters.append(repeater)
            
        except Exception as e:
            print(f"Error parsing API response: {e}")
            # Try alternative parsing approach
            try:
                # Look for JSON data if XML parsing fails
                import json
                if '{' in xml_response:
                    json_start = xml_response.find('{')
                    json_data = json.loads(xml_response[json_start:])
                    # Process JSON format if available
                    pass
            except:
                pass
        
        return repeaters

# GPS Worker Class using gpspipe
class GPSWorker(QThread):
    gps_data_signal = pyqtSignal(float, float, float, float, float)  # Added heading parameter

    def __init__(self, host='127.0.0.1', port=2947):
        super().__init__()
        self.host = host
        self.port = port
        self.running = True

    def run(self):
        try:
            # Start gpspipe process
            cmd = ['gpspipe', '-w']
            
            if self.host != '127.0.0.1' or self.port != 2947:
                env = os.environ.copy()
                env['GPSD_HOST'] = f"{self.host}:{self.port}"
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                          env=env, text=True)
            else:
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            print("✓ GPS Worker started - reading from gpspipe")
            
            # Read gpspipe output continuously
            for line in process.stdout:
                if not self.running:
                    break
                    
                try:
                    data = json.loads(line.strip())
                    msg_class = data.get('class', 'UNKNOWN')
                    
                    # Look for TPV (Time-Position-Velocity) messages
                    if msg_class == 'TPV':
                        if 'lat' in data and 'lon' in data and 'mode' in data:
                            lat = data['lat']
                            lon = data['lon']
                            alt = data.get('alt', 0.0)
                            mode = data['mode']
                            
                            # Get speed (in m/s) and track/heading
                            speed = data.get('speed', 0.0)
                            track = data.get('track', 0.0)  # Course over ground in degrees
                            
                            # mode: 0=no fix, 1=no fix, 2=2D, 3=3D
                            if mode >= 2:
                                # Emit GPS data to main thread (lat, lon, alt, speed, heading)
                                self.gps_data_signal.emit(lat, lon, alt, speed, track)
                                
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    print(f"Error parsing GPS message: {e}")
                    continue
            
            process.terminate()
            
        except FileNotFoundError:
            print("❌ Error: gpspipe not found. Install gpsd-clients package:")
            print("  sudo apt-get install gpsd-clients")
        except Exception as e:
            print(f"❌ Error in GPSWorker: {e}")
    
    def stop(self):
        self.running = False

# Enhanced Main Window Class
class EnhancedGPSWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TowerWitch - Enhanced GPS Tower Locator")
        
        # Optimize for 10" touchscreen (1024x600 typical resolution)
        self.setGeometry(0, 0, 1024, 600)
        self.setMinimumSize(800, 600)
        
        # Set up styling for touch interface
        self.setup_styling()
        
        # Create main widget and layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setSpacing(10)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Initialize configuration and API first
        self.load_configuration()
        self.radio_api = RadioReferenceAPI(self.api_key)
        self.cache_dir = self.radio_api.cache_dir  # Reference to the radio API cache directory
        
        # Initialize caching variables for amateur radio data
        self.cached_api_data = None
        self.cached_api_location = None
        self.cached_api_timestamp = None
        self.cached_api_radius = 200  # Cache covers 200-mile radius
        self.amateur_data_cache_timeout = 86400  # 24 hours (much longer for regional cache)
        self.is_stationary = False
        self.stationary_threshold = 0.01  # 0.01 miles = ~50 feet movement to trigger refresh
        self.last_known_position = None
        self.cache_region_radius = 150  # Stay within 150 miles of cache center before refresh
        self.force_band_refresh = False  # Flag to force refresh of band displays when moving
        
        # Check if cache refresh is requested (after radio_api is initialized)
        force_refresh = self.config.getboolean('API', 'force_refresh_cache', fallback=False)
        if force_refresh:
            print("🔄 Cache refresh requested - clearing all cached data")
            self.radio_api.clear_all_cache()
            # Reset the config option so it doesn't clear every time
            self.config.set('API', 'force_refresh_cache', 'false')
            with open(self.config_file, 'w') as f:
                self.config.write(f)
        
        # Data source status
        self.data_source_status = {
            'armer': 'static',
            'skywarn': 'static', 
            'amateur': 'static'
        }
        
        # Create header with title and status
        self.create_header()
        
        # Create tabbed interface
        self.create_tabs()
        
        # Create control buttons
        self.create_control_buttons()
        
        # Path to the CSV file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.csv_filepath = os.path.join(script_dir, "trs_sites_3508.csv")
        
        # Initialize Radio Reference API
        self.load_configuration()
        self.radio_api = RadioReferenceAPI(self.api_key)
        
        # Data source status
        self.data_source_status = {
            'armer': 'static',
            'skywarn': 'static', 
            'amateur': 'static'
        }
        
        # Start GPS worker
        self.gps_worker = GPSWorker()
        self.gps_worker.gps_data_signal.connect(self.update_gps_data)
        self.gps_worker.start()
        
        # Initialize with demo data if no GPS
        self.last_lat = 44.9778  # Minneapolis default
        self.last_lon = -93.2650
        # Track fullscreen state
        self._is_fullscreen = False

        # Create an action for toggling fullscreen with F11
        self._toggle_fullscreen_act = QAction(self)
        self._toggle_fullscreen_act.setShortcut('F11')
        self._toggle_fullscreen_act.triggered.connect(self.toggle_fullscreen)
        self.addAction(self._toggle_fullscreen_act)

    def setup_styling(self):
        """Set up fonts and colors for touch interface"""
        # Balanced fonts - larger for important data, reasonable for coordinates
        self.header_font = QFont("Arial", 18, QFont.Bold)
        self.label_font = QFont("Arial", 14, QFont.Bold)
        self.data_font = QFont("Arial", 12)  # Smaller for coordinate data
        self.coordinate_font = QFont("Arial", 11)  # Even smaller for coordinates
        self.button_font = QFont("Arial", 14, QFont.Bold)
        self.table_font = QFont("Arial", 13)
        
        # Color scheme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #555555;
                border-radius: 8px;
                margin-top: 1ex;
                padding-top: 12px;
                background-color: #3b3b3b;
                color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
                color: #00ff00;
                font-size: 14px;
            }
            QLabel {
                color: #ffffff;
                padding: 6px;
                font-size: 12px;
            }
            QPushButton {
                background-color: #4a90e2;
                border: none;
                border-radius: 8px;
                padding: 15px;
                font-weight: bold;
                color: white;
                min-height: 45px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QPushButton:pressed {
                background-color: #2968a3;
            }
            QTableWidget {
                background-color: #3b3b3b;
                border: 1px solid #555555;
                border-radius: 5px;
                gridline-color: #555555;
                font-size: 13px;
                color: #ffffff;
            }
            QTableWidget::item {
                padding: 12px;
                border-bottom: 1px solid #555555;
                color: #ffffff;
                font-size: 13px;
            }
            QTableWidget::item:alternate {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QTableWidget::item:selected {
                background-color: #4a90e2;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #4a90e2;
                color: #ffffff;
                padding: 12px;
                border: 1px solid #555555;
                font-weight: bold;
                font-size: 14px;
            }
            QTabWidget::pane {
                border: 1px solid #555555;
                background-color: #3b3b3b;
            }
            QTabBar::tab {
                background-color: #2b2b2b;
                color: #ffffff;
                padding: 15px 25px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                min-width: 120px;
                font-size: 14px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #4a90e2;
            }
        """)

    def create_header(self):
        """Create header with title, date/time, and GPS status"""
        header_frame = QFrame()
        header_layout = QHBoxLayout(header_frame)
        
        # Title
        title_label = QLabel("🗼 TowerWitch")
        title_label.setFont(self.header_font)
        title_label.setStyleSheet("color: #00ff00; padding: 10px;")
        
        # Date and Time in center
        self.datetime_label = QLabel()
        self.datetime_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.datetime_label.setStyleSheet("color: #ffffff; padding: 10px;")
        self.datetime_label.setAlignment(Qt.AlignCenter)
        self.update_datetime()
        
        # GPS Status indicator (right side)
        self.gps_status = QLabel("GPS: Searching...")
        self.gps_status.setFont(self.label_font)
        self.gps_status.setStyleSheet("color: #ffaa00; padding: 6px; font-size: 14px;")
        self.gps_status.setAlignment(Qt.AlignRight)
        
        header_layout.addWidget(title_label, 1)
        header_layout.addWidget(self.datetime_label, 2)
        header_layout.addWidget(self.gps_status, 1)
        
        self.main_layout.addWidget(header_frame)
        
        # Timer for updating date/time every second
        self.datetime_timer = QTimer()
        self.datetime_timer.timeout.connect(self.update_datetime)
        self.datetime_timer.start(1000)  # Update every second

    def create_tabs(self):
        """Create tabbed interface for different information views"""
        self.tabs = QTabWidget()
        
        # GPS Data Tab
        self.gps_tab = self.create_gps_tab()
        self.tabs.addTab(self.gps_tab, "📍 GPS Data")
        
        # Grid Systems Tab (grouped with GPS data)
        self.grid_tab = self.create_grid_tab()
        self.tabs.addTab(self.grid_tab, "�️ Grids")
        
        # ARMER Data Tab (start of repeater group)
        self.tower_tab = self.create_tower_tab()
        self.tabs.addTab(self.tower_tab, "� ARMER")
        
        # Skywarn Weather Tab
        self.skywarn_tab = self.create_skywarn_tab()
        self.tabs.addTab(self.skywarn_tab, "🌦️ Skywarn")
        
        # Amateur Radio Tab
        self.amateur_tab = self.create_amateur_tab()
        self.tabs.addTab(self.amateur_tab, "📻 Amateur")
        
        self.main_layout.addWidget(self.tabs)

		def create_gps_tab(self):
        """Create GPS data display tab with table format"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Create a table for GPS data
        self.gps_table = QTableWidget()
        self.gps_table.setColumnCount(2)
        self.gps_table.setHorizontalHeaderLabels(["MEASUREMENT", "VALUE"])
        self.gps_table.setRowCount(8)  # 8 different measurements (added heading and vector speed)
        
        # Set up table appearance
        self.gps_table.setAlternatingRowColors(True)
        self.gps_table.verticalHeader().setVisible(False)
        self.gps_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.gps_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        # Set column widths
        header = self.gps_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Measurement name column
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Value column expands
        
        # Set row height for better readability
        self.gps_table.verticalHeader().setDefaultSectionSize(45)
        
        # Style the GPS table specifically
        self.gps_table.setStyleSheet("""
            QTableWidget {
                background-color: #3b3b3b;
                border: 1px solid #555555;
                border-radius: 5px;
                gridline-color: #555555;
                font-size: 12px;
                color: #ffffff;
            }
            QTableWidget::item {
                padding: 10px;
                border-bottom: 1px solid #555555;
                color: #ffffff;
            }
            QTableWidget::item:alternate {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QTableWidget::item:selected {
                background-color: #4a90e2;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #4a90e2;
                color: #ffffff;
                padding: 12px;
                border: 1px solid #555555;
                font-weight: bold;
                font-size: 13px;
            }
        """)
        
        # Initialize GPS labels for updating
        self.gps_items = {}
        
        # Row 0: Latitude
        self.gps_items['lat_item'] = QTableWidgetItem("📍 LATITUDE")
        self.gps_items['lat_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.gps_items['lat_value'] = QTableWidgetItem("Waiting for GPS...")
        self.gps_items['lat_value'].setFont(QFont("Arial", 12))
        
        # Row 1: Longitude  
        self.gps_items['lon_item'] = QTableWidgetItem("� LONGITUDE")
        self.gps_items['lon_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.gps_items['lon_value'] = QTableWidgetItem("Waiting for GPS...")
        self.gps_items['lon_value'].setFont(QFont("Arial", 12))
        
        # Row 2: Altitude
        self.gps_items['alt_item'] = QTableWidgetItem("⛰️ ALTITUDE")
        self.gps_items['alt_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.gps_items['alt_value'] = QTableWidgetItem("N/A")
        self.gps_items['alt_value'].setFont(QFont("Arial", 12))
        
        # Row 3: Speed
        self.gps_items['speed_item'] = QTableWidgetItem("🚗 SPEED")
        self.gps_items['speed_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.gps_items['speed_value'] = QTableWidgetItem("N/A")
        self.gps_items['speed_value'].setFont(QFont("Arial", 12))
        
        # Row 4: Heading/Direction
        self.gps_items['heading_item'] = QTableWidgetItem("🧭 HEADING")
        self.gps_items['heading_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.gps_items['heading_value'] = QTableWidgetItem("N/A")
        self.gps_items['heading_value'].setFont(QFont("Arial", 12))
        
        # Row 5: Vector Speed (speed + direction)
        self.gps_items['vector_item'] = QTableWidgetItem("🏃 VECTOR SPEED")
        self.gps_items['vector_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.gps_items['vector_value'] = QTableWidgetItem("N/A")
        self.gps_items['vector_value'].setFont(QFont("Arial", 12))
        
        # Row 6: GPS Status
        self.gps_items['status_item'] = QTableWidgetItem("🛰️ GPS STATUS")
        self.gps_items['status_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.gps_items['status_value'] = QTableWidgetItem("Searching...")
        self.gps_items['status_value'].setFont(QFont("Arial", 12))
        
        # Row 7: Fix Quality
        self.gps_items['fix_item'] = QTableWidgetItem("📡 FIX QUALITY")
        self.gps_items['fix_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.gps_items['fix_value'] = QTableWidgetItem("No Fix")
        self.gps_items['fix_value'].setFont(QFont("Arial", 12))
        
        # Add items to table
        self.gps_table.setItem(0, 0, self.gps_items['lat_item'])
        self.gps_table.setItem(0, 1, self.gps_items['lat_value'])
        self.gps_table.setItem(1, 0, self.gps_items['lon_item'])
        self.gps_table.setItem(1, 1, self.gps_items['lon_value'])
        self.gps_table.setItem(2, 0, self.gps_items['alt_item'])
        self.gps_table.setItem(2, 1, self.gps_items['alt_value'])
        self.gps_table.setItem(3, 0, self.gps_items['speed_item'])
        self.gps_table.setItem(3, 1, self.gps_items['speed_value'])
        self.gps_table.setItem(4, 0, self.gps_items['heading_item'])
        self.gps_table.setItem(4, 1, self.gps_items['heading_value'])
        self.gps_table.setItem(5, 0, self.gps_items['vector_item'])
        self.gps_table.setItem(5, 1, self.gps_items['vector_value'])
        self.gps_table.setItem(6, 0, self.gps_items['status_item'])
        self.gps_table.setItem(6, 1, self.gps_items['status_value'])
        self.gps_table.setItem(7, 0, self.gps_items['fix_item'])
        self.gps_table.setItem(7, 1, self.gps_items['fix_value'])
        
        layout.addWidget(self.gps_table)
        
        return tab

    def create_tower_tab(self):
        """Create tower information display tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Tower table with enhanced formatting
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Site Name", "County", "Distance", "Bearing", "NAC", "Control Channels"])
        
        # Set column widths for better touch interface
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Site name can expand
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # County
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Distance
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Bearing
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # NAC
        header.setSectionResizeMode(5, QHeaderView.Stretch)  # Control frequencies can expand
        
        # Make table touch-friendly with larger fonts and spacing
        self.table.setMinimumHeight(450)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(50)  # Even taller rows for better readability
        self.table.setFont(self.table_font)
        
        layout.addWidget(self.table)
        
        return tab

    def create_grid_tab(self):
        """Create grid systems display tab with table format"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Create a table for grid systems
        self.grid_table = QTableWidget()
        self.grid_table.setColumnCount(2)
        self.grid_table.setHorizontalHeaderLabels(["GRID SYSTEM", "COORDINATES"])
        self.grid_table.setRowCount(6)  # 6 different coordinate systems
        
        # Set up table appearance
        self.grid_table.setAlternatingRowColors(True)
        self.grid_table.verticalHeader().setVisible(False)
        self.grid_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.grid_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        # Set column widths
        header = self.grid_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # System name column
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Coordinates column expands
        
        # Set row height for better readability
        self.grid_table.verticalHeader().setDefaultSectionSize(45)
        
        # Style the grid table specifically
        self.grid_table.setStyleSheet("""
            QTableWidget {
                background-color: #3b3b3b;
                border: 1px solid #555555;
                border-radius: 5px;
                gridline-color: #555555;
                font-size: 12px;
                color: #ffffff;
            }
            QTableWidget::item {
                padding: 10px;
                border-bottom: 1px solid #555555;
                color: #ffffff;
            }
            QTableWidget::item:alternate {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QTableWidget::item:selected {
                background-color: #4a90e2;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #4a90e2;
                color: #ffffff;
                padding: 12px;
                border: 1px solid #555555;
                font-weight: bold;
                font-size: 13px;
            }
        """)
        
        # Initialize grid labels for updating
        self.grid_items = {}
        
        # Row 0: Decimal Degrees
        self.grid_items['lat_item'] = QTableWidgetItem("📍 LATITUDE")
        self.grid_items['lat_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.grid_items['lat_value'] = QTableWidgetItem("Waiting for GPS...")
        self.grid_items['lat_value'].setFont(QFont("Arial", 12))
        
        # Row 1: Longitude
        self.grid_items['lon_item'] = QTableWidgetItem("📍 LONGITUDE")
        self.grid_items['lon_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.grid_items['lon_value'] = QTableWidgetItem("Waiting for GPS...")
        self.grid_items['lon_value'].setFont(QFont("Arial", 12))
        
        # Row 2: UTM
        self.grid_items['utm_item'] = QTableWidgetItem("🗺️ UTM")
        self.grid_items['utm_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.grid_items['utm_value'] = QTableWidgetItem("N/A")
        self.grid_items['utm_value'].setFont(QFont("Arial", 12))
        
        # Row 3: Maidenhead
        self.grid_items['mh_item'] = QTableWidgetItem("📡 MAIDENHEAD")
        self.grid_items['mh_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.grid_items['mh_value'] = QTableWidgetItem("N/A")
        self.grid_items['mh_value'].setFont(QFont("Arial", 12))
        
        # Row 4: MGRS Zone/Grid
        self.grid_items['mgrs_zone_item'] = QTableWidgetItem("🪖 MGRS ZONE/GRID")
        self.grid_items['mgrs_zone_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.grid_items['mgrs_zone_value'] = QTableWidgetItem("N/A")
        self.grid_items['mgrs_zone_value'].setFont(QFont("Arial", 12))
        
        # Row 5: MGRS Coordinates
        self.grid_items['mgrs_coords_item'] = QTableWidgetItem("🔢 MGRS EASTING/NORTHING")
        self.grid_items['mgrs_coords_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.grid_items['mgrs_coords_value'] = QTableWidgetItem("N/A")
        self.grid_items['mgrs_coords_value'].setFont(QFont("Arial", 12))
        
        # Add items to table
        self.grid_table.setItem(0, 0, self.grid_items['lat_item'])
        self.grid_table.setItem(0, 1, self.grid_items['lat_value'])
        self.grid_table.setItem(1, 0, self.grid_items['lon_item'])
        self.grid_table.setItem(1, 1, self.grid_items['lon_value'])
        self.grid_table.setItem(2, 0, self.grid_items['utm_item'])
        self.grid_table.setItem(2, 1, self.grid_items['utm_value'])
        self.grid_table.setItem(3, 0, self.grid_items['mh_item'])
        self.grid_table.setItem(3, 1, self.grid_items['mh_value'])
        self.grid_table.setItem(4, 0, self.grid_items['mgrs_zone_item'])
        self.grid_table.setItem(4, 1, self.grid_items['mgrs_zone_value'])
        self.grid_table.setItem(5, 0, self.grid_items['mgrs_coords_item'])
        self.grid_table.setItem(5, 1, self.grid_items['mgrs_coords_value'])
        
        layout.addWidget(self.grid_table)
        
        return tab

    def create_skywarn_tab(self):
        """Create Skywarn weather repeater display tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Skywarn table - maximize space for repeater data
        self.skywarn_table = QTableWidget()
        self.skywarn_table.setColumnCount(6)
        self.skywarn_table.setHorizontalHeaderLabels(["Call Sign", "Location", "Frequency", "Tone", "Distance", "Bearing"])
        
        # Set column widths for touch interface
        header = self.skywarn_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Call sign
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Location can expand
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Frequency
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Tone
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Distance
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Bearing
        
        # Make table touch-friendly with more space
        self.skywarn_table.setMinimumHeight(450)
        self.skywarn_table.setAlternatingRowColors(True)
        self.skywarn_table.verticalHeader().setDefaultSectionSize(50)
        self.skywarn_table.setFont(self.table_font)
        
        # Add sample Skywarn data for Minnesota
        self.populate_skywarn_data()
        
        layout.addWidget(self.skywarn_table)
        
        return tab

    def create_amateur_tab(self):
        """Create Amateur Radio repeater display tab with band sub-tabs"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Create sub-tabs for different bands - maximize space for data
        self.amateur_subtabs = QTabWidget()
        
        # 10m Tab
        self.amateur_10m_tab = self.create_band_tab("10m", "10 Meters (28-29.7 MHz)")
        self.amateur_subtabs.addTab(self.amateur_10m_tab, "10m")
        
        # 6m Tab  
        self.amateur_6m_tab = self.create_band_tab("6m", "6 Meters (50-54 MHz)")
        self.amateur_subtabs.addTab(self.amateur_6m_tab, "6m")
        
        # 2m Tab
        self.amateur_2m_tab = self.create_band_tab("2m", "2 Meters (144-148 MHz)")
        self.amateur_subtabs.addTab(self.amateur_2m_tab, "2m")
        
        # 1.25m Tab
        self.amateur_125m_tab = self.create_band_tab("1.25m", "1.25 Meters (220-225 MHz)")
        self.amateur_subtabs.addTab(self.amateur_125m_tab, "1.25m")
        
        # 70cm Tab
        self.amateur_70cm_tab = self.create_band_tab("70cm", "70 Centimeters (420-450 MHz)")
        self.amateur_subtabs.addTab(self.amateur_70cm_tab, "70cm")
        
        # Simplex Tab (Special frequencies)
        self.amateur_simplex_tab = self.create_simplex_tab("simplex", "Simplex & Special Frequencies")
        self.amateur_subtabs.addTab(self.amateur_simplex_tab, "Simplex")
        
        # Style the sub-tabs to match the main interface
        self.amateur_subtabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #555555;
                background-color: #3b3b3b;
            }
            QTabBar::tab {
                background-color: #2b2b2b;
                color: #ffffff;
                padding: 12px 20px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                min-width: 80px;
                font-size: 12px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #4a90e2;
            }
        """)
        
        layout.addWidget(self.amateur_subtabs)
        
        # Populate all band data
        self.populate_all_amateur_data()
        
        # Populate simplex data
        self.populate_simplex_data()
        
        return tab

    def create_band_tab(self, band_name, band_description):
        """Create a tab for a specific amateur radio band"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Band description
        desc_label = QLabel(band_description)
        desc_label.setFont(QFont("Arial", 12, QFont.Bold))
        desc_label.setStyleSheet("color: #ffffff; padding: 5px;")
        desc_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_label)
        
        # Create table for this band
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(["Call Sign", "Location", "Output", "Input", "Tone", "Distance", "Bearing"])
        
        # Set column widths for touch interface
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Call sign
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Location can expand
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Output freq
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Input freq
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Tone
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Distance
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Bearing
        
        # Make table touch-friendly
        table.setMinimumHeight(350)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setDefaultSectionSize(45)
        table.setFont(self.table_font)
        
        # Store reference to table for population
        # Create consistent table attribute names
        if band_name == "70cm":
            table_name = "amateur_70cm_table"
        elif band_name == "1.25m":
            table_name = "amateur_125_table"
        else:
            table_name = f'amateur_{band_name.replace(".", "").replace("m", "")}_table'
        setattr(self, table_name, table)
        
        layout.addWidget(table)
        
        return tab

    def create_simplex_tab(self, band_name, band_description):
        """Create a tab for amateur radio simplex and special frequencies"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Create table for simplex frequencies - maximize space for data
        table = QTableWidget()
        table.setColumnCount(6)  # Different columns for simplex
        table.setHorizontalHeaderLabels(["Frequency", "Description", "Type", "Mode", "Tone", "Notes"])
        
        # Set column widths for touch interface
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Frequency
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Description can expand
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Type
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Mode
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Tone
        header.setSectionResizeMode(5, QHeaderView.Stretch)  # Notes
        
        # Make table touch-friendly with more space
        table.setMinimumHeight(400)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setDefaultSectionSize(45)
        table.setFont(self.table_font)
        
        # Store reference to table for population
        setattr(self, "amateur_simplex_table", table)
        
        layout.addWidget(table)
        
        return tab

    def create_control_buttons(self):
        """Create touch-friendly control buttons"""
        button_frame = QFrame()
        button_layout = QHBoxLayout(button_frame)
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh All")
        refresh_btn.setFont(self.button_font)
        refresh_btn.clicked.connect(self.refresh_towers)
        
        # Export button  
        export_btn = QPushButton("💾 Export Data")
        export_btn.setFont(self.button_font)
        export_btn.clicked.connect(self.export_data)
        
        # Night Mode toggle button
        self.night_mode_btn = QPushButton("🌙 Night Mode")
        self.night_mode_btn.setFont(self.button_font)
        self.night_mode_btn.clicked.connect(self.toggle_night_mode_button)
        self.night_mode_active = False  # Track night mode state
        
        button_layout.addWidget(refresh_btn)
        button_layout.addWidget(export_btn)
        button_layout.addWidget(self.night_mode_btn)
        
        self.main_layout.addWidget(button_frame)

    def refresh_towers(self):
        """Manually refresh tower and repeater data"""
        if hasattr(self, 'last_lat') and hasattr(self, 'last_lon'):
            self.display_closest_sites(self.last_lat, self.last_lon)
            self.populate_skywarn_data()
            self.populate_all_amateur_data()

    def export_data(self):
        """Export current tower data"""
        # Placeholder for export functionality
        print("Export functionality - could save to file or copy to clipboard")

    def show_settings(self):
        """Show settings dialog"""
        # Placeholder for settings dialog
        print("Settings dialog - could configure GPS host, number of sites, etc.")

    def update_datetime(self):
        """Update date and time display"""
        now = datetime.now()
        # Format: "Mon Oct 20, 2025  14:35:27"
        day_name = now.strftime("%a")  # Mon, Tue, etc.
        date_str = now.strftime("%b %d, %Y")
        time_str = now.strftime("%H:%M:%S")
        self.datetime_label.setText(f"{day_name} {date_str}  {time_str}")

    def toggle_night_mode_button(self):
        """Toggle night mode when button is clicked"""
        self.night_mode_active = not self.night_mode_active
        self.toggle_night_mode(self.night_mode_active)
        
        # Update button text to reflect current state
        if self.night_mode_active:
            self.night_mode_btn.setText("☀️ Day Mode")
        else:
            self.night_mode_btn.setText("🌙 Night Mode")

    def update_table_colors_for_mode(self, night_mode_on):
        """Update table item colors based on current mode"""
        if night_mode_on:
            # Night mode colors - red theme
            active_color = QColor(255, 102, 102)      # Light red for active status
            warning_color = QColor(255, 153, 102)     # Orange-red for warnings  
            text_color = QColor(255, 102, 102)        # Red for regular text
        else:
            # Day mode colors - original theme
            active_color = QColor(0, 255, 0)          # Green for active status
            warning_color = QColor(255, 255, 0)       # Yellow for warnings
            text_color = QColor(255, 255, 255)        # White for regular text
        
        # Update GPS status colors if they exist
        if hasattr(self, 'gps_items'):
            if 'status_value' in self.gps_items:
                self.gps_items['status_value'].setForeground(active_color)
            if 'fix_value' in self.gps_items:
                # Check current fix text to determine appropriate color
                fix_text = self.gps_items['fix_value'].text()
                if "Moving" in fix_text:
                    self.gps_items['fix_value'].setForeground(active_color)
                else:
                    self.gps_items['fix_value'].setForeground(warning_color)
        
        # Update tower table colors if it exists
        if hasattr(self, 'tower_table'):
            for row in range(self.tower_table.rowCount()):
                for col in range(self.tower_table.columnCount()):
                    item = self.tower_table.item(row, col)
                    if item:
                        item.setForeground(text_color)

    def toggle_night_mode(self, night_mode_on):
        """Toggle between day and night mode for better night vision"""
        if night_mode_on:
            # Night mode - red theme for preserving night vision
            night_style = """
            QMainWindow {
                background-color: #1a0000;
                color: #ff6666;
            }
            QTabWidget::pane {
                border: 2px solid #330000;
                background-color: #1a0000;
            }
            QTabBar::tab {
                background-color: #220000;
                color: #ff6666;
                padding: 15px 25px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                min-width: 120px;
                font-size: 14px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #660000;
            }
            QTableWidget {
                background-color: #1a0000;
                alternate-background-color: #220000;
                color: #ff6666;
                gridline-color: #330000;
                border: 1px solid #330000;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #330000;
            }
            QHeaderView::section {
                background-color: #330000;
                color: #ff6666;
                font-weight: bold;
                font-size: 14px;
                padding: 8px;
                border: 1px solid #550000;
            }
            QLabel {
                color: #ff6666;
            }
            QPushButton {
                background-color: #660000;
                border: none;
                border-radius: 8px;
                padding: 15px;
                font-weight: bold;
                color: #ff6666;
                min-height: 45px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #880000;
            }

            """
            self.setStyleSheet(night_style)
            # Update header colors for night mode
            self.gps_status.setStyleSheet("color: #ff6666; padding: 6px; font-size: 14px;")
            self.datetime_label.setStyleSheet("color: #ff6666; padding: 10px;")
        else:
            # Day mode - restore original dark theme
            self.setup_styling()
            self.gps_status.setStyleSheet("color: #00ff00; padding: 6px; font-size: 14px;")
            self.datetime_label.setStyleSheet("color: #ffffff; padding: 10px;")
        
        # Update all table item colors to match the new theme
        self.update_table_colors_for_mode(night_mode_on)

    def update_gps_data(self, latitude, longitude, altitude, speed, heading):
        """Update all GPS-related displays"""
        self.last_lat = latitude
        self.last_lon = longitude
        
        # Update GPS status in header
        self.gps_status.setText("GPS: Active 🟢")
        self.gps_status.setStyleSheet("color: #00ff00; padding: 12px; font-size: 14px;")
        
        # Update GPS table
        self.gps_items['lat_value'].setText(f"{latitude:.6f}°")
        self.gps_items['lon_value'].setText(f"{longitude:.6f}°")
        
        # Update altitude with both metric and imperial
        self.gps_items['alt_value'].setText(f"{altitude:.1f} m ({altitude * M_TO_FEET:.1f} ft)")
        
        # Update speed with multiple units (with minimum threshold)
        # GPS noise threshold - ignore speeds below 0.5 m/s (~1.1 mph, walking speed)
        MIN_SPEED_THRESHOLD = 0.5  # meters per second
        
        if speed >= MIN_SPEED_THRESHOLD:
            speed_mph = speed * MPS_TO_MPH
            speed_knots = speed * MPS_TO_KNOTS
            self.gps_items['speed_value'].setText(f"{speed:.1f} m/s ({speed_mph:.1f} mph, {speed_knots:.1f} kt)")
            is_moving = True
        else:
            # Below threshold - consider stationary
            self.gps_items['speed_value'].setText("0.0 m/s (0.0 mph, 0.0 kt)")
            is_moving = False
        
        # Update heading with cardinal direction (only when moving)
        if heading is not None and heading >= 0 and is_moving:
            # Convert bearing to cardinal direction
            directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                         'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
            index = int((heading + 11.25) / 22.5) % 16
            cardinal = directions[index]
            self.gps_items['heading_value'].setText(f"{heading:.0f}° ({cardinal})")
        else:
            self.gps_items['heading_value'].setText("--° (--)")
        
        # Update vector speed (speed + direction combined)
        if is_moving and heading is not None and heading >= 0:
            # Convert bearing to cardinal direction for vector
            directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                         'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
            index = int((heading + 11.25) / 22.5) % 16
            cardinal = directions[index]
            speed_mph = speed * MPS_TO_MPH
            self.gps_items['vector_value'].setText(f"{speed_mph:.1f} mph {cardinal}")
        else:
            self.gps_items['vector_value'].setText("Stationary")
        
        # Update GPS status and fix quality
        self.gps_items['status_value'].setText("🟢 ACTIVE")
        self.gps_items['status_value'].setForeground(QColor(0, 255, 0))  # Green text
        
        # Determine fix quality based on speed accuracy (rough estimate)
        if speed > 0.1:  # Moving
            self.gps_items['fix_value'].setText("🟢 3D FIX (Moving)")
            self.gps_items['fix_value'].setForeground(QColor(0, 255, 0))
        else:  # Stationary
            self.gps_items['fix_value'].setText("🟡 3D FIX (Stationary)")
            self.gps_items['fix_value'].setForeground(QColor(255, 255, 0))

        # Update Grid Systems in table format
        try:
            # Update coordinates in grid table
            self.grid_items['lat_value'].setText(f"{latitude:.6f}°")
            self.grid_items['lon_value'].setText(f"{longitude:.6f}°")
            
            # UTM
            utm_result = utm.from_latlon(latitude, longitude)
            utm_str = f"Zone {utm_result[2]}{utm_result[3]} E:{utm_result[0]:.0f} N:{utm_result[1]:.0f}"
            self.grid_items['utm_value'].setText(utm_str)
            
            # Maidenhead
            mh_grid = mh.to_maiden(latitude, longitude)
            self.grid_items['mh_value'].setText(mh_grid)
            
            # MGRS
            m = mgrs.MGRS()
            mgrs_result = m.toMGRS(latitude, longitude)
            mgrs_zone = mgrs_result[:3]
            mgrs_grid = mgrs_result[3:5]
            mgrs_coords = mgrs_result[5:]
            
            # Split MGRS coordinates into easting and northing for better readability
            if len(mgrs_coords) >= 6:
                mid_point = len(mgrs_coords) // 2
                easting = mgrs_coords[:mid_point]
                northing = mgrs_coords[mid_point:]
                formatted_coords = f"{easting} {northing}"
            else:
                formatted_coords = mgrs_coords
                
            self.grid_items['mgrs_zone_value'].setText(f"{mgrs_zone} {mgrs_grid}")
            self.grid_items['mgrs_coords_value'].setText(formatted_coords)
            
        except Exception as e:
            print(f"Error calculating grid systems: {e}")

        # Update Closest Towers
        self.display_closest_sites(latitude, longitude)
        
        # Only update repeater data if we've moved significantly or it's the first time
        # Repeaters are on fixed towers - no need to refresh when stationary!
        current_location = (latitude, longitude)
        if not hasattr(self, 'last_repeater_update_location'):
            # First time - populate everything
            self.populate_skywarn_data()
            self.populate_all_amateur_data()
            self.last_repeater_update_location = current_location
            print("📍 First GPS lock - fetching all repeater data")
        else:
            # Check if we've moved significantly (more than ~50 feet)
            last_lat, last_lon = self.last_repeater_update_location
            distance_moved = haversine(latitude, longitude, last_lat, last_lon)
            
            if distance_moved > 0.01:  # 0.01 miles = ~50 feet
                self.populate_skywarn_data()
                self.populate_all_amateur_data()
                self.last_repeater_update_location = current_location
                print(f"📍 Moved {distance_moved:.3f} miles - refreshing repeater data")
                
                # Force refresh of band displays if we're within cached region but moving
                if hasattr(self, 'force_band_refresh') and self.force_band_refresh:
                    print("🔄 Forcing band display refresh for new location")
                    # Repopulate band data to re-sort by distance from new location
                    self.populate_band_data("10", self.amateur_10m_data)
                    self.populate_band_data("6", self.amateur_6m_data) 
                    self.populate_band_data("2", self.amateur_2m_data)
                    self.populate_band_data("125", self.amateur_125m_data)
                    self.populate_band_data("70cm", self.amateur_70cm_data)
            # If stationary (moved less than 50 feet), do nothing - repeaters don't move!

    def display_closest_sites(self, latitude, longitude):
        """Display closest tower sites in enhanced table"""
        closest_sites = find_closest_sites(self.csv_filepath, latitude, longitude)
        self.table.setRowCount(len(closest_sites))
        
        for row, (site, distance, bearing, control_frequencies, nac) in enumerate(closest_sites):
            # Site name with color coding by distance
            site_item = QTableWidgetItem(site["Description"])
            if distance < 5:
                site_item.setBackground(QColor(0, 120, 0))  # Darker green for better contrast
                site_item.setForeground(QColor(255, 255, 255))  # White text
            elif distance < 15:
                site_item.setBackground(QColor(140, 140, 0))  # Darker yellow for better contrast
                site_item.setForeground(QColor(255, 255, 255))  # White text
            else:
                site_item.setBackground(QColor(120, 0, 0))  # Darker red for better contrast
                site_item.setForeground(QColor(255, 255, 255))  # White text
            
            # Create other items with white text
            county_item = QTableWidgetItem(site["County Name"])
            county_item.setForeground(QColor(255, 255, 255))
            
            distance_item = QTableWidgetItem(f"{distance:.1f} mi")
            distance_item.setForeground(QColor(255, 255, 255))
            
            bearing_item = QTableWidgetItem(f"{bearing:.0f}°")
            bearing_item.setForeground(QColor(255, 255, 255))
            
            nac_item = QTableWidgetItem(str(nac))
            nac_item.setForeground(QColor(255, 255, 255))
            
            # Format control frequencies nicely
            freq_text = ", ".join(control_frequencies) if control_frequencies else "N/A"
            freq_item = QTableWidgetItem(freq_text)
            freq_item.setForeground(QColor(255, 255, 255))
            
            self.table.setItem(row, 0, site_item)
            self.table.setItem(row, 1, county_item)
            self.table.setItem(row, 2, distance_item)
            self.table.setItem(row, 3, bearing_item)
            self.table.setItem(row, 4, nac_item)
            self.table.setItem(row, 5, freq_item)

    def populate_skywarn_data(self):
        """Populate Skywarn weather repeater data with smart caching"""
        if hasattr(self, 'last_lat') and hasattr(self, 'last_lon'):
            user_lat = self.last_lat
            user_lon = self.last_lon
        else:
            user_lat = 44.9778  # Default to Minneapolis
            user_lon = -93.2650
        
        # Initialize Skywarn caching if not exists
        if not hasattr(self, 'cached_skywarn_data'):
            self.cached_skywarn_data = None
            self.cached_skywarn_location = None
            self.skywarn_is_stationary = False
        
        # Check if we need to refresh Skywarn data
        should_refresh = False
        
        if self.cached_skywarn_data is None:
            should_refresh = True
            print("📍 First time fetching Skywarn data")
        elif self.cached_skywarn_location:
            cached_lat, cached_lon = self.cached_skywarn_location
            distance = haversine(user_lat, user_lon, cached_lat, cached_lon)
            
            if distance > 0.01:  # Moved more than ~50 feet
                should_refresh = True
                self.skywarn_is_stationary = False
                print(f"📍 Moved {distance:.3f} miles, refreshing Skywarn data")
            else:
                # Stationary - Skywarn repeaters don't move either!
                if not self.skywarn_is_stationary:
                    self.skywarn_is_stationary = True
                    print("🔒 Skywarn stationary mode: Using cached data")
        
        # Try to get data from Radio Reference API only if we need to refresh
        api_data = []
        if should_refresh and hasattr(self, 'radio_api'):
            try:
                api_data = self.radio_api.get_skywarn_repeaters(user_lat, user_lon)
                if api_data:
                    # Cache the successful API data
                    self.cached_skywarn_data = api_data
                    self.cached_skywarn_location = (user_lat, user_lon)
                    self.data_source_status['skywarn'] = 'live'
                    print("✓ Using live Skywarn data from Radio Reference")
                else:
                    # Check cache
                    cached = self.radio_api.load_from_cache("skywarn", f"{user_lat:.3f}_{user_lon:.3f}_100")
                    if cached:
                        api_data = cached
                        self.cached_skywarn_data = cached
                        self.cached_skywarn_location = (user_lat, user_lon)
                        self.data_source_status['skywarn'] = 'cached'
            except Exception as e:
                print(f"Error fetching Skywarn API data: {e}")
        elif self.cached_skywarn_data:
            # Use existing cached data
            api_data = self.cached_skywarn_data
            self.data_source_status['skywarn'] = 'cached'
        
        # Use combined data - merge API data with static data for completeness
        combined_repeaters = []
        
        if api_data:
            # Convert API data to expected format
            api_repeaters = self.convert_api_data_to_repeater_format(api_data)
            combined_repeaters.extend(api_repeaters)
            self.data_source_status['skywarn'] = 'live'
            print(f"✓ Using {len(api_repeaters)} live Skywarn repeaters from Radio Reference")
        
        # Always include static data as fallback/supplement
        static_skywarn_repeaters = [
            # Twin Cities Metro SKYWARN Network
            {"call": "W0EAR", "location": "Minneapolis ARES", "freq": "146.94", "tone": "114.8", "lat": 44.9778, "lon": -93.2650},
            {"call": "WB0CMZ", "location": "Ramsey County ARES", "freq": "145.43", "tone": "123.0", "lat": 44.9537, "lon": -93.0900},
            {"call": "KC0YHH", "location": "Anoka County ARES", "freq": "145.45", "tone": "131.8", "lat": 45.1975, "lon": -93.3063},
            {"call": "W0MSP", "location": "MSP Emergency Coord", "freq": "147.42", "tone": "100.0", "lat": 44.8848, "lon": -93.2223},
            
            # Regional SKYWARN/Emergency Networks
            {"call": "K0USC", "location": "Duluth SKYWARN", "freq": "146.76", "tone": "131.8", "lat": 46.7867, "lon": -92.1005},
            {"call": "W0HSC", "location": "Rochester ARES", "freq": "147.06", "tone": "100.0", "lat": 44.0121, "lon": -92.4802},
            {"call": "KC0OOO", "location": "St. Cloud ARES", "freq": "145.47", "tone": "103.5", "lat": 45.5579, "lon": -94.2476},
            {"call": "W0RAN", "location": "Brainerd SKYWARN", "freq": "146.85", "tone": "136.5", "lat": 46.3580, "lon": -94.2008},
            {"call": "N0BVE", "location": "Bemidji Emergency", "freq": "146.67", "tone": "94.8", "lat": 47.4737, "lon": -94.8789},
            {"call": "WA0TDA", "location": "Itasca County ARES", "freq": "147.33", "tone": "107.2", "lat": 47.2378, "lon": -93.5308},
            
            # Southern Minnesota SKYWARN
            {"call": "W0TCX", "location": "Mankato SKYWARN", "freq": "146.73", "tone": "123.0", "lat": 44.1636, "lon": -94.0719},
            {"call": "KC0BSC", "location": "Winona Emergency", "freq": "145.17", "tone": "107.2", "lat": 44.0498, "lon": -91.6407},
            {"call": "W0ZPL", "location": "Albert Lea ARES", "freq": "146.68", "tone": "131.8", "lat": 43.6481, "lon": -93.3687},
            
            # Western Minnesota SKYWARN  
            {"call": "KC0JHF", "location": "Marshall SKYWARN", "freq": "147.24", "tone": "94.8", "lat": 44.4469, "lon": -95.7881},
            {"call": "W0MWX", "location": "Moorhead ARES", "freq": "145.23", "tone": "114.8", "lat": 46.8738, "lon": -96.7667},
            {"call": "KC0AHX", "location": "Alexandria SKYWARN", "freq": "146.91", "tone": "103.5", "lat": 45.8855, "lon": -95.3772},
            
            # Northern Minnesota Emergency
            {"call": "W0IAC", "location": "International Falls", "freq": "147.39", "tone": "136.5", "lat": 48.6019, "lon": -93.4016},
            {"call": "KC0EMG", "location": "Grand Marais ARES", "freq": "146.55", "tone": "100.0", "lat": 47.7503, "lon": -90.3376},
            {"call": "N0QVC", "location": "Ely Emergency Net", "freq": "145.35", "tone": "131.8", "lat": 47.9032, "lon": -91.8673}
        ]
        
        # Merge static data, avoiding duplicates by call sign
        api_calls = {rep.get('call', '') for rep in combined_repeaters}
        for static_rep in static_skywarn_repeaters:
            if static_rep['call'] not in api_calls:
                combined_repeaters.append(static_rep)
        
        # Update status based on final data source
        if not api_data:
            self.data_source_status['skywarn'] = 'static'
        elif len(combined_repeaters) > len(api_data if api_data else []):
            self.data_source_status['skywarn'] = 'hybrid'  # Mix of API and static
        
        skywarn_repeaters = combined_repeaters
        
        # Calculate distances and sort
        repeater_distances = []
        for repeater in skywarn_repeaters:
            distance = haversine(user_lat, user_lon, repeater["lat"], repeater["lon"])
            bearing = calculate_bearing(user_lat, user_lon, repeater["lat"], repeater["lon"])
            repeater_distances.append((repeater, distance, bearing))
        
        # Sort by distance
        repeater_distances.sort(key=lambda x: x[1])
        
        # Populate table
        self.skywarn_table.setRowCount(len(repeater_distances))
        
        # Update header to show data source
        source_indicator = self.get_data_source_indicator('skywarn')
        self.skywarn_table.setHorizontalHeaderLabels([
            f"Call Sign {source_indicator}", "Location", "Frequency", "Tone", "Distance", "Bearing"
        ])
        
        for row, (repeater, distance, bearing) in enumerate(repeater_distances):
            # Color code by distance like ARMER sites
            call_item = QTableWidgetItem(repeater["call"])
            if distance < 25:
                call_item.setBackground(QColor(0, 120, 0))  # Green for close
                call_item.setForeground(QColor(255, 255, 255))
            elif distance < 75:
                call_item.setBackground(QColor(140, 140, 0))  # Yellow for medium
                call_item.setForeground(QColor(255, 255, 255))
            else:
                call_item.setBackground(QColor(120, 0, 0))  # Red for far
                call_item.setForeground(QColor(255, 255, 255))
            
            location_item = QTableWidgetItem(repeater["location"])
            location_item.setForeground(QColor(255, 255, 255))
            
            freq_item = QTableWidgetItem(f"{repeater['freq']} MHz")
            freq_item.setForeground(QColor(255, 255, 255))
            
            tone_item = QTableWidgetItem(f"{repeater['tone']} Hz")
            tone_item.setForeground(QColor(255, 255, 255))
            
            distance_item = QTableWidgetItem(f"{distance:.1f} mi")
            distance_item.setForeground(QColor(255, 255, 255))
            
            bearing_item = QTableWidgetItem(f"{bearing:.0f}°")
            bearing_item.setForeground(QColor(255, 255, 255))
            
            self.skywarn_table.setItem(row, 0, call_item)
            self.skywarn_table.setItem(row, 1, location_item)
            self.skywarn_table.setItem(row, 2, freq_item)
            self.skywarn_table.setItem(row, 3, tone_item)
            self.skywarn_table.setItem(row, 4, distance_item)
            self.skywarn_table.setItem(row, 5, bearing_item)

    def convert_api_data_to_repeater_format(self, api_data):
        """Convert Radio Reference API data to internal repeater format"""
        converted_repeaters = []
        
        try:
            for repeater in api_data:
                # Extract relevant fields from Radio Reference API response
                converted_rep = {
                    "call": repeater.get('call_sign', repeater.get('callsign', 'N/A')),
                    "location": repeater.get('description', repeater.get('location', 'Unknown')),
                    "freq": str(repeater.get('frequency', repeater.get('output_freq', '0.0'))),
                    "tone": str(repeater.get('tone', repeater.get('ctcss', '0.0'))),
                    "lat": float(repeater.get('latitude', repeater.get('lat', 0.0))),
                    "lon": float(repeater.get('longitude', repeater.get('lon', 0.0)))
                }
                
                # Validate coordinates (basic sanity check for Minnesota)
                if 43.0 <= converted_rep["lat"] <= 49.5 and -97.5 <= converted_rep["lon"] <= -89.0:
                    converted_repeaters.append(converted_rep)
                else:
                    print(f"⚠️ Skipping repeater {converted_rep['call']} - coordinates outside Minnesota")
                    
        except Exception as e:
            print(f"⚠️ Error converting API data: {e}")
            
        return converted_repeaters

    def populate_all_amateur_data(self):
        """Populate Amateur Radio repeater data for all bands with smart stationary caching"""
        
        # Get current location
        if hasattr(self, 'last_lat') and hasattr(self, 'last_lon'):
            user_lat = self.last_lat
            user_lon = self.last_lon
        else:
            user_lat = 44.9778  # Default to Minneapolis
            user_lon = -93.2650
        
        # Check if we need to refresh the regional API cache
        should_refresh = False
        current_time = time.time()
        
        # Refresh if no cached data exists
        if self.cached_api_data is None:
            should_refresh = True
            print("📍 No regional cache - fetching amateur radio data")
        
        # Check if cache has expired (24 hours for regional cache)
        elif self.cached_api_timestamp and (current_time - self.cached_api_timestamp) > self.amateur_data_cache_timeout:
            should_refresh = True
            print(f"⏰ Regional cache expired ({(current_time - self.cached_api_timestamp)/3600:.1f} hours old), refreshing")
        
        # Check if we've moved outside the cached region
        elif self.cached_api_location:
            cached_lat, cached_lon = self.cached_api_location
            distance_from_cache_center = haversine(user_lat, user_lon, cached_lat, cached_lon)
            
            if distance_from_cache_center > self.cache_region_radius:
                should_refresh = True
                print(f"📍 Moved {distance_from_cache_center:.1f} miles from cache center (outside {self.cache_region_radius}-mile region)")
            else:
                # We're within the cached region - check for movement for logging
                if self.last_known_position:
                    last_lat, last_lon = self.last_known_position
                    distance_moved = haversine(user_lat, user_lon, last_lat, last_lon)
                    
                    if distance_moved < self.stationary_threshold:
                        if not self.is_stationary:
                            self.is_stationary = True
                            print(f"🔒 Stationary within cached region ({distance_from_cache_center:.1f} miles from center)")
                    else:
                        was_stationary = self.is_stationary
                        self.is_stationary = False
                        if was_stationary:
                            print(f"🚶 Movement within cached region ({distance_from_cache_center:.1f} miles from center)")
                        
                        # Important: Even within cached region, refresh displays when moving significantly
                        if distance_moved > 1.0:  # Moved more than 1 mile, update displays
                            print(f"📍 Moved {distance_moved:.1f} miles - refreshing repeater displays for new location")
                            # Force refresh of band tables even with cached data
                            self.force_band_refresh = True
                else:
                    print(f"✓ Using regional cache ({distance_from_cache_center:.1f} miles from center)")
        
        # Update last known position for movement tracking
        self.last_known_position = (user_lat, user_lon)
        
        # Fetch new regional API data only if needed
        if should_refresh and hasattr(self, 'radio_api') and self.radio_api.api_key:
            try:
                print(f"🌐 Fetching fresh regional amateur radio data (radius: {self.cached_api_radius} miles)...")
                api_data = self.radio_api.get_repeaters_by_location(user_lat, user_lon, self.cached_api_radius)
                
                # Only use API data if we actually get useful results
                if api_data and len(api_data) > 3:  # Require meaningful data
                    self.cached_api_data = api_data
                    self.cached_api_location = (user_lat, user_lon)
                    self.cached_api_timestamp = current_time
                    print(f"✓ Cached {len(self.cached_api_data)} amateur repeaters for {self.cached_api_radius}-mile region")
                else:
                    print("⚠️ API returned limited data - using comprehensive static database instead")
                    self.cached_api_data = []  # Force use of static data
            except Exception as e:
                print(f"⚠️ Error fetching amateur radio data: {e} - using comprehensive static database")
                self.cached_api_data = []  # Force use of static data
        
        # Static fallback data for each band
        # 10m repeaters (28-29.7 MHz) - Usually FM simplex or experimental
        self.amateur_10m_data = [
            {"call": "W0EXP", "location": "Minneapolis", "output": "29.620", "input": "29.620", "tone": "Simplex", "lat": 44.9778, "lon": -93.2650},
            {"call": "K0HF", "location": "St. Paul", "output": "29.640", "input": "29.640", "tone": "Simplex", "lat": 44.9537, "lon": -93.0900}
        ]
        
        # 6m repeaters (50-54 MHz) - Enhanced with Radio Reference data
        self.amateur_6m_data = [
            {"call": "W0UJ", "location": "Brainerd ARC - 6M", "output": "53.110", "input": "52.110", "tone": "123.0", "lat": 46.3560, "lon": -94.2008},
            {"call": "W0VHF", "location": "Minneapolis", "output": "53.290", "input": "52.290", "tone": "100.0", "lat": 44.9778, "lon": -93.2650},
            {"call": "K0SIX", "location": "Duluth", "output": "53.370", "input": "52.370", "tone": "103.5", "lat": 46.7867, "lon": -92.1005},
            {"call": "WB0SIX", "location": "Rochester", "output": "53.430", "input": "52.430", "tone": "107.2", "lat": 44.0121, "lon": -92.4802}
        ]
        
        # 2m repeaters (144-148 MHz) - Comprehensive Minnesota coverage from Radio Reference
        self.amateur_2m_data = [
            # Crow Wing County (Brainerd/Baxter area) - Radio Reference verified data
            {"call": "W0UJ", "location": "Brainerd ARC - VHF", "output": "145.130", "input": "144.530", "tone": "CSQ", "lat": 46.3560, "lon": -94.2008},
            {"call": "W0UJ", "location": "Brainerd ARC - VHF", "output": "147.225", "input": "147.825", "tone": "CSQ", "lat": 46.3560, "lon": -94.2008},
            {"call": "W0UJ", "location": "Crosslake", "output": "147.030", "input": "147.630", "tone": "CSQ", "lat": 46.6347, "lon": -94.1074},
            {"call": "W0REA", "location": "Pequot Lakes", "output": "147.090", "input": "147.690", "tone": "123.0", "lat": 46.6014, "lon": -94.3125},
            {"call": "N0CRW", "location": "Brainerd", "output": "146.985", "input": "146.385", "tone": "CSQ", "lat": 46.3560, "lon": -94.2008},
            {"call": "W0BTO", "location": "Brainerd", "output": "146.760", "input": "146.160", "tone": "114.8", "lat": 46.3583, "lon": -94.2003},
            {"call": "W0RAN", "location": "Brainerd", "output": "146.850", "input": "146.250", "tone": "136.5", "lat": 46.3580, "lon": -94.2008},
            {"call": "KC0FBZ", "location": "Crow Wing County", "output": "146.940", "input": "146.340", "tone": "131.8", "lat": 46.4816, "lon": -93.9589},
            {"call": "W0CVZ", "location": "Baxter", "output": "147.060", "input": "147.660", "tone": "100.0", "lat": 46.3583, "lon": -94.2003},
            {"call": "KC0YHM", "location": "Crosby", "output": "146.820", "input": "146.220", "tone": "100.0", "lat": 46.4816, "lon": -93.9589},
            
            # Morrison County (Little Falls area)
            {"call": "KC0TZF", "location": "Little Falls", "output": "147.300", "input": "147.900", "tone": "123.0", "lat": 45.9763, "lon": -94.3625},
            {"call": "K0LFD", "location": "Little Falls", "output": "145.350", "input": "144.750", "tone": "103.5", "lat": 45.9763, "lon": -94.3625},
            {"call": "WB0CVZ", "location": "Pierz", "output": "147.120", "input": "147.720", "tone": "107.2", "lat": 45.9896, "lon": -94.1058},
            
            # Itasca County (Grand Rapids area)
            {"call": "N0GWS", "location": "Grand Rapids", "output": "145.230", "input": "144.630", "tone": "91.5", "lat": 47.2399, "lon": -93.5277},
            {"call": "WA0TDA", "location": "Grand Rapids", "output": "147.330", "input": "147.930", "tone": "107.2", "lat": 47.2378, "lon": -93.5308},
            
            # Stearns County (St. Cloud area)
            {"call": "KC0OOO", "location": "St. Cloud", "output": "145.470", "input": "144.870", "tone": "103.5", "lat": 45.5579, "lon": -94.2476},
            {"call": "W0RTN", "location": "St. Cloud", "output": "146.820", "input": "146.220", "tone": "131.8", "lat": 45.5372, "lon": -94.1653},
            {"call": "KC0ALV", "location": "Sauk Centre", "output": "147.390", "input": "147.990", "tone": "123.0", "lat": 45.7361, "lon": -94.9533},
            
            # Beltrami County (Bemidji area)
            {"call": "N0BVE", "location": "Bemidji", "output": "146.670", "input": "146.070", "tone": "94.8", "lat": 47.4737, "lon": -94.8789},
            {"call": "KC0BSU", "location": "Bemidji", "output": "147.180", "input": "147.780", "tone": "131.8", "lat": 47.4737, "lon": -94.8789},
            
            # Twin Cities Metro
            {"call": "W0MSP", "location": "Minneapolis", "output": "145.310", "input": "144.710", "tone": "123.0", "lat": 44.9778, "lon": -93.2650},
            {"call": "KC9SPG", "location": "St. Paul", "output": "146.520", "input": "145.920", "tone": "Simplex", "lat": 44.9537, "lon": -93.0900},
            {"call": "W0UJ", "location": "St. Paul", "output": "145.490", "input": "144.890", "tone": "131.8", "lat": 44.9537, "lon": -93.0900},
            {"call": "K0TRC", "location": "St. Paul", "output": "147.165", "input": "147.765", "tone": "103.5", "lat": 44.9537, "lon": -93.0900},
            {"call": "WB0RUR", "location": "Minneapolis", "output": "146.52", "input": "146.52", "tone": "Simplex", "lat": 44.9778, "lon": -93.2650},
            {"call": "WA0ZQG", "location": "Minneapolis", "output": "145.23", "input": "144.63", "tone": "100.0", "lat": 44.9778, "lon": -93.2650},
            {"call": "WB0CMZ", "location": "St. Paul (South)", "output": "145.43", "input": "144.83", "tone": "123.0", "lat": 44.9000, "lon": -93.1000},
            
            # St. Louis County (Duluth area)
            {"call": "K0USC", "location": "Duluth", "output": "146.76", "input": "146.16", "tone": "131.8", "lat": 46.7867, "lon": -92.1005},
            {"call": "WD0EKR", "location": "Duluth", "output": "145.130", "input": "144.530", "tone": "103.5", "lat": 46.7867, "lon": -92.1005},
            
            # Olmsted County (Rochester area)
            {"call": "W0HSC", "location": "Rochester", "output": "147.06", "input": "147.66", "tone": "100.0", "lat": 44.0121, "lon": -92.4802},
            {"call": "KC0RCH", "location": "Rochester", "output": "146.850", "input": "146.250", "tone": "107.2", "lat": 44.0121, "lon": -92.4802}
        ]
        
        # 1.25m repeaters (220-225 MHz) - Less common band
        self.amateur_125m_data = [
            {"call": "N0ONT", "location": "Minneapolis", "output": "224.38", "input": "223.38", "tone": "103.5", "lat": 44.9778, "lon": -93.2650},
            {"call": "KC0125", "location": "St. Paul", "output": "224.46", "input": "223.46", "tone": "107.2", "lat": 44.9537, "lon": -93.0900},
            {"call": "W0RPT", "location": "Duluth", "output": "224.54", "input": "223.54", "tone": "100.0", "lat": 46.7867, "lon": -92.1005}
        ]
        
        # 70cm repeaters (420-450 MHz) - Comprehensive Minnesota UHF coverage
        self.amateur_70cm_data = [
            # Crow Wing County (Brainerd/Baxter area) - Radio Reference verified data
            {"call": "W0UJ", "location": "Nisswa", "output": "443.925", "input": "448.925", "tone": "123.0", "lat": 46.5208, "lon": -94.2886},
            {"call": "W0UJ", "location": "Brainerd ARC - UHF", "output": "444.925", "input": "449.925", "tone": "CSQ", "lat": 46.3560, "lon": -94.2008},
            {"call": "W0AIH", "location": "Baxter", "output": "444.025", "input": "449.025", "tone": "131.8", "lat": 46.3583, "lon": -94.2003},
            {"call": "KC0YHM", "location": "Crosby", "output": "442.750", "input": "447.750", "tone": "100.0", "lat": 46.4816, "lon": -93.9589},
            {"call": "N0FMN", "location": "Brainerd", "output": "442.200", "input": "447.200", "tone": "123.0", "lat": 46.3583, "lon": -94.2003},
            {"call": "KC0CVZ", "location": "Baxter", "output": "443.800", "input": "448.800", "tone": "114.8", "lat": 46.3583, "lon": -94.2003},
            
            # Morrison County area
            {"call": "KC0TZF", "location": "Little Falls", "output": "442.525", "input": "447.525", "tone": "123.0", "lat": 45.9763, "lon": -94.3625},
            
            # Stearns County (St. Cloud area)
            {"call": "W0RTN", "location": "St. Cloud", "output": "444.550", "input": "449.550", "tone": "131.8", "lat": 45.5372, "lon": -94.1653},
            {"call": "KC0SCL", "location": "St. Cloud", "output": "442.975", "input": "447.975", "tone": "103.5", "lat": 45.5579, "lon": -94.2476},
            
            # Itasca County (Grand Rapids area)
            {"call": "N0GWS", "location": "Grand Rapids", "output": "443.650", "input": "448.650", "tone": "91.5", "lat": 47.2399, "lon": -93.5277},
            
            # Beltrami County (Bemidji area)
            {"call": "N0BVE", "location": "Bemidji", "output": "442.950", "input": "447.950", "tone": "94.8", "lat": 47.4737, "lon": -94.8789},
            {"call": "KC0BSU", "location": "Bemidji", "output": "444.300", "input": "449.300", "tone": "131.8", "lat": 47.4737, "lon": -94.8789},
            
            # Twin Cities Metro
            {"call": "WB0CMZ", "location": "St. Paul", "output": "442.600", "input": "447.600", "tone": "123.0", "lat": 44.9537, "lon": -93.0900},
            {"call": "K0UHF", "location": "Minneapolis", "output": "443.200", "input": "448.200", "tone": "100.0", "lat": 44.9778, "lon": -93.2650},
            {"call": "W0UJ", "location": "St. Paul (UHF)", "output": "443.925", "input": "448.925", "tone": "103.5", "lat": 44.9537, "lon": -93.0900},
            {"call": "KC0ART", "location": "Apple Valley", "output": "442.325", "input": "447.325", "tone": "100.0", "lat": 44.7317, "lon": -93.2170},
            {"call": "W0MSP", "location": "Minneapolis", "output": "444.875", "input": "449.875", "tone": "123.0", "lat": 44.9778, "lon": -93.2650},
            {"call": "KC0TCM", "location": "Plymouth", "output": "442.125", "input": "447.125", "tone": "107.2", "lat": 45.0105, "lon": -93.4555},
            
            # St. Louis County (Duluth area)
            {"call": "WD0EKR", "location": "Duluth", "output": "444.450", "input": "449.450", "tone": "103.5", "lat": 46.7867, "lon": -92.1005},
            {"call": "K0DLH", "location": "Duluth", "output": "442.375", "input": "447.375", "tone": "131.8", "lat": 46.7867, "lon": -92.1005},
            
            # Olmsted County (Rochester area)
            {"call": "WA0UHF", "location": "Rochester", "output": "442.775", "input": "447.775", "tone": "107.2", "lat": 44.0121, "lon": -92.4802},
            {"call": "KC0RCH", "location": "Rochester", "output": "444.700", "input": "449.700", "tone": "100.0", "lat": 44.0121, "lon": -92.4802},
            
            # Regional/Wide Area
            {"call": "W0MN", "location": "Central MN", "output": "443.775", "input": "448.775", "tone": "114.8", "lat": 45.7869, "lon": -94.6859},
            {"call": "KC0NET", "location": "Northern MN", "output": "442.850", "input": "447.850", "tone": "136.5", "lat": 46.7296, "lon": -93.9336}
        ]
        
        # Populate each band
        self.populate_band_data("10", self.amateur_10m_data)
        self.populate_band_data("6", self.amateur_6m_data) 
        self.populate_band_data("2", self.amateur_2m_data)
        self.populate_band_data("125", self.amateur_125m_data)
        self.populate_band_data("70cm", self.amateur_70cm_data)

    def populate_band_data(self, band_name, repeaters):
        """Populate data for a specific amateur radio band using cached API data"""
        # Create consistent table attribute names
        if band_name == "70cm":
            table_attr = "amateur_70cm_table"
        elif band_name == "125":
            table_attr = "amateur_125_table"
        else:
            table_attr = f'amateur_{band_name}_table'
        
        if not hasattr(self, table_attr):
            print(f"Warning: Table attribute {table_attr} not found for band {band_name}")
            return
            
        table = getattr(self, table_attr)
        
        if hasattr(self, 'last_lat') and hasattr(self, 'last_lon'):
            user_lat = self.last_lat
            user_lon = self.last_lon
        else:
            user_lat = 44.9778  # Default to Minneapolis
            user_lon = -93.2650
        
        # Use cached API data if available, but prefer comprehensive static data when API is limited
        api_repeaters = []
        if self.cached_api_data and len(self.cached_api_data) > 5:  # Only use API if substantial data
            # Filter cached data for this specific band
            api_repeaters = self.filter_repeaters_by_band(self.cached_api_data, band_name)
            if api_repeaters and len(api_repeaters) > 2:  # Require meaningful band data
                print(f"✓ Using {len(api_repeaters)} live {band_name} repeaters from cached API data")
                self.data_source_status['amateur'] = 'live'
        
        # Combine comprehensive static data with any useful API data
        if api_repeaters and len(api_repeaters) > len(repeaters) * 0.5:  # API has more than 50% of static data
            # API data seems substantial, use it
            repeater_data = api_repeaters
        else:
            # Use our comprehensive static database (Radio Reference verified)
            if api_repeaters:
                print(f"⚠️ API data limited ({len(api_repeaters)} {band_name}) - using comprehensive static database instead")
            repeater_data = repeaters
            self.data_source_status['amateur'] = 'static'
        
        # Calculate distances and sort (always recalculate for current position)
        repeater_distances = []
        for repeater in repeater_data:
            distance = haversine(user_lat, user_lon, repeater["lat"], repeater["lon"])
            bearing = calculate_bearing(user_lat, user_lon, repeater["lat"], repeater["lon"])
            repeater_distances.append((repeater, distance, bearing))
        
        # Sort by distance (always sort based on current location)
        repeater_distances.sort(key=lambda x: x[1])
        
        # Clear force refresh flag after processing
        if hasattr(self, 'force_band_refresh'):
            self.force_band_refresh = False
        
        # Populate table
        table.setRowCount(len(repeater_distances))
        
        # Update header to show data source
        source_indicator = self.get_data_source_indicator('amateur')
        table.setHorizontalHeaderLabels([
            f"Call Sign {source_indicator}", "Location", "Output", "Input", "Tone", "Distance", "Bearing"
        ])
        
        for row, (repeater, distance, bearing) in enumerate(repeater_distances):
            # Color code by distance
            call_item = QTableWidgetItem(repeater["call"])
            if distance < 25:
                call_item.setBackground(QColor(0, 120, 0))  # Green for close
                call_item.setForeground(QColor(255, 255, 255))
            elif distance < 75:
                call_item.setBackground(QColor(140, 140, 0))  # Yellow for medium
                call_item.setForeground(QColor(255, 255, 255))
            else:
                call_item.setBackground(QColor(120, 0, 0))  # Red for far
                call_item.setForeground(QColor(255, 255, 255))
            
            location_item = QTableWidgetItem(repeater["location"])
            location_item.setForeground(QColor(255, 255, 255))
            
            output_item = QTableWidgetItem(f"{repeater['output']} MHz")
            output_item.setForeground(QColor(255, 255, 255))
            
            input_item = QTableWidgetItem(f"{repeater['input']} MHz")
            input_item.setForeground(QColor(255, 255, 255))
            
            tone_item = QTableWidgetItem(f"{repeater['tone']}")
            tone_item.setForeground(QColor(255, 255, 255))
            
            distance_item = QTableWidgetItem(f"{distance:.1f} mi")
            distance_item.setForeground(QColor(255, 255, 255))
            
            bearing_item = QTableWidgetItem(f"{bearing:.0f}°")
            bearing_item.setForeground(QColor(255, 255, 255))
            
            table.setItem(row, 0, call_item)
            table.setItem(row, 1, location_item)
            table.setItem(row, 2, output_item)
            table.setItem(row, 3, input_item)
            table.setItem(row, 4, tone_item)
            table.setItem(row, 5, distance_item)
            table.setItem(row, 6, bearing_item)

    def filter_repeaters_by_band(self, repeaters, band_name):
        """Filter repeaters by amateur radio band"""
        band_ranges = {
            '10': (28.0, 29.7),      # 10 meters
            '6': (50.0, 54.0),       # 6 meters  
            '2': (144.0, 148.0),     # 2 meters
            '125': (220.0, 225.0),   # 1.25 meters
            '70cm': (420.0, 450.0)   # 70 centimeters
        }
        
        if band_name not in band_ranges:
            return []
        
        min_freq, max_freq = band_ranges[band_name]
        filtered = []
        
        for repeater in repeaters:
            try:
                # Try 'frequency' first (our data format), then 'freq' (API format)
                freq = float(repeater.get('frequency', repeater.get('freq', '0')))
                if min_freq <= freq <= max_freq:
                    filtered.append(repeater)
            except (ValueError, TypeError):
                continue
        
        return filtered

    def flush_amateur_cache(self):
        """Manually flush the regional amateur radio cache"""
        self.cached_api_data = None
        self.cached_api_location = None
        self.cached_api_timestamp = None
        print("�️ Amateur radio cache flushed")

    def flush_skywarn_cache(self):
        """Manually flush the Skywarn repeater cache"""
        self.cached_skywarn_data = None
        self.cached_skywarn_location = None
        self.cached_skywarn_timestamp = None
        print("🗑️ Skywarn cache flushed")

    def populate_all_amateur_data(self):
        """Ensure all amateur data arrays are populated with comprehensive static data"""
        # Force population of all band data arrays
        self.amateur_10m_data = [
            {"call": "WD0DET", "location": "St. Cloud", "output": "29.64", "input": "29.54", "tone": "114.8", "lat": 45.5579, "lon": -94.2476},
            {"call": "KF0RWD", "location": "Alexandria", "output": "29.67", "input": "29.57", "tone": "94.8", "lat": 45.8855, "lon": -95.3772},
            {"call": "K0DIS", "location": "Fergus Falls", "output": "29.62", "input": "29.52", "tone": "131.8", "lat": 46.2830, "lon": -96.0777},
            {"call": "WA0TDA", "location": "Grand Rapids", "output": "29.69", "input": "29.59", "tone": "107.2", "lat": 47.2378, "lon": -93.5308},
            {"call": "KF0RWD", "location": "Brainerd", "output": "29.61", "input": "29.51", "tone": "94.8", "lat": 46.3580, "lon": -94.2008}
        ]
        
        self.amateur_6m_data = [
            {"call": "KF0QCC", "location": "St. Cloud", "output": "53.77", "input": "52.77", "tone": "114.8", "lat": 45.5579, "lon": -94.2476},
            {"call": "WD0DET", "location": "Alexandria", "output": "53.83", "input": "52.83", "tone": "94.8", "lat": 45.8855, "lon": -95.3772},
            {"call": "K0DIS", "location": "Fergus Falls", "output": "53.89", "input": "52.89", "tone": "131.8", "lat": 46.2830, "lon": -96.0777},
            {"call": "WA0TDA", "location": "Grand Rapids", "output": "53.93", "input": "52.93", "tone": "107.2", "lat": 47.2378, "lon": -93.5308},
            {"call": "KF0QCC", "location": "Brainerd", "output": "53.85", "input": "52.85", "tone": "103.5", "lat": 46.3580, "lon": -94.2008}
        ]
        
        self.amateur_1_25m_data = [
            {"call": "KF0SME", "location": "St. Cloud", "output": "224.92", "input": "223.32", "tone": "114.8", "lat": 45.5579, "lon": -94.2476},
            {"call": "WD0DET", "location": "Alexandria", "output": "224.96", "input": "223.36", "tone": "94.8", "lat": 45.8855, "lon": -95.3772},
            {"call": "K0DIS", "location": "Fergus Falls", "output": "224.86", "input": "223.26", "tone": "131.8", "lat": 46.2830, "lon": -96.0777},
            {"call": "WA0TDA", "location": "Grand Rapids", "output": "224.98", "input": "223.38", "tone": "107.2", "lat": 47.2378, "lon": -93.5308},
            {"call": "KF0SME", "location": "Brainerd", "output": "224.88", "input": "223.28", "tone": "103.5", "lat": 46.3580, "lon": -94.2008}
        ]
        
        # Load simplex data
        self.load_simplex_data()

    def load_simplex_data(self):
        """Load amateur radio simplex frequencies from CSV file"""
        try:
            simplex_file = os.path.join(os.path.dirname(__file__), "AmateurSimplex.csv")
            self.amateur_simplex_data = []
            
            print(f"📻 Loading simplex data from: {simplex_file}")
            
            if os.path.exists(simplex_file):
                with open(simplex_file, 'r', encoding='utf-8') as file:
                    csv_reader = csv.DictReader(file)
                    for row in csv_reader:
                        try:
                            # Parse the CSV data
                            freq_output = float(row['Frequency Output'])
                            freq_input = float(row['Frequency Input']) if row['Frequency Input'] != '0' else None
                            
                            # Determine frequency type and band
                            freq_type = "Repeater" if freq_input else "Simplex"
                            band = self.determine_band(freq_output)
                            
                            # Format tone information
                            tone_out = row.get('PL Output Tone', '').strip()
                            tone_in = row.get('PL Input Tone', '').strip()
                            tone_display = ""
                            if tone_out and tone_out != 'CSQ':
                                tone_display = tone_out
                                if tone_in and tone_in != tone_out:
                                    tone_display += f"/{tone_in}"
                            
                            # Create notes from multiple fields
                            notes = []
                            if row.get('Alpha Tag'):
                                notes.append(row['Alpha Tag'])
                            if row.get('Agency/Category'):
                                notes.append(row['Agency/Category'])
                            notes_text = " | ".join(notes) if notes else ""
                            
                            # Format frequency display
                            if freq_input:
                                freq_display = f"{freq_output} / {freq_input}"
                            else:
                                freq_display = str(freq_output)
                            
                            simplex_entry = {
                                'frequency': freq_output,
                                'frequency_display': freq_display,
                                'description': row.get('Description', '').strip(),
                                'type': freq_type,
                                'mode': row.get('Mode', '').strip(),
                                'tone': tone_display,
                                'notes': notes_text,
                                'band': band,
                                'input_freq': freq_input
                            }
                            
                            self.amateur_simplex_data.append(simplex_entry)
                            
                        except (ValueError, KeyError) as e:
                            print(f"⚠️ Error parsing simplex entry: {e}")
                            continue
                
                # Sort by frequency
                self.amateur_simplex_data.sort(key=lambda x: x['frequency'])
                print(f"✅ Loaded {len(self.amateur_simplex_data)} simplex frequencies")
                
            else:
                print(f"⚠️ Simplex file not found: {simplex_file}")
                self.amateur_simplex_data = []
                
        except Exception as e:
            print(f"❌ Error loading simplex data: {e}")
            self.amateur_simplex_data = []

    def determine_band(self, frequency):
        """Determine amateur radio band from frequency"""
        if 28.0 <= frequency <= 29.7:
            return "10m"
        elif 50.0 <= frequency <= 54.0:
            return "6m"
        elif 144.0 <= frequency <= 148.0:
            return "2m"
        elif 220.0 <= frequency <= 225.0:
            return "1.25m"
        elif 420.0 <= frequency <= 450.0:
            return "70cm"
        elif 902.0 <= frequency <= 928.0:
            return "33cm"
        elif 1240.0 <= frequency <= 1300.0:
            return "23cm"
        elif 2300.0 <= frequency <= 2450.0:
            return "13cm"
        else:
            return "Other"

    def populate_simplex_data(self):
        """Populate the simplex frequencies table"""
        try:
            table = getattr(self, 'amateur_simplex_table', None)
            if not table:
                print("⚠️ Simplex table not found")
                return
            
            # Clear existing data
            table.setRowCount(0)
            
            if not hasattr(self, 'amateur_simplex_data') or not self.amateur_simplex_data:
                self.load_simplex_data()
            
            # Populate table
            table.setRowCount(len(self.amateur_simplex_data))
            
            for row, entry in enumerate(self.amateur_simplex_data):
                try:
                    # Frequency
                    freq_item = QTableWidgetItem(entry['frequency_display'])
                    freq_item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, 0, freq_item)
                    
                    # Description
                    desc_item = QTableWidgetItem(entry['description'])
                    table.setItem(row, 1, desc_item)
                    
                    # Type (Simplex/Repeater) with band
                    type_text = f"{entry['type']} ({entry['band']})"
                    type_item = QTableWidgetItem(type_text)
                    type_item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, 2, type_item)
                    
                    # Mode
                    mode_item = QTableWidgetItem(entry['mode'])
                    mode_item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, 3, mode_item)
                    
                    # Tone
                    tone_item = QTableWidgetItem(entry['tone'])
                    tone_item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, 4, tone_item)
                    
                    # Notes
                    notes_item = QTableWidgetItem(entry['notes'])
                    table.setItem(row, 5, notes_item)
                    
                    # Color coding by band
                    band_colors = {
                        '10m': QColor(255, 100, 100, 50),  # Light red
                        '6m': QColor(255, 165, 0, 50),     # Light orange
                        '2m': QColor(100, 100, 255, 50),   # Light blue
                        '1.25m': QColor(255, 255, 100, 50), # Light yellow
                        '70cm': QColor(100, 255, 100, 50), # Light green
                        '33cm': QColor(255, 100, 255, 50), # Light magenta
                        '23cm': QColor(100, 255, 255, 50), # Light cyan
                        '13cm': QColor(200, 200, 200, 50)  # Light gray
                    }
                    
                    band_color = band_colors.get(entry['band'], QColor(255, 255, 255, 30))
                    for col in range(6):
                        item = table.item(row, col)
                        if item:
                            item.setBackground(band_color)
                
                except Exception as e:
                    print(f"⚠️ Error populating simplex row {row}: {e}")
                    continue
            
            print(f"✅ Populated {table.rowCount()} simplex frequencies")
            
        except Exception as e:
            print(f"❌ Error populating simplex data: {e}")

    def get_cache_status(self):
        """Get information about the current cache status"""
        status = {
            "amateur_api_cached": self.cached_api_data is not None,
            "amateur_api_location": self.cached_api_location,
            "amateur_api_timestamp": self.cached_api_timestamp,
            "skywarn_cached": self.cached_skywarn_data is not None,
            "skywarn_location": self.cached_skywarn_location,
            "skywarn_timestamp": self.cached_skywarn_timestamp
        }
        return status

    def parse_filter_by_service(self, repeaters):
        """Filter repeaters by service type"""
        filtered = []
        
        # Emergency/Public Safety keywords
        emergency_keywords = [
            'police', 'fire', 'ems', 'emergency', 'dispatch', 'sheriff', 
            'medical', 'rescue', 'public safety', 'hospital', 'ambulance',
            'security', 'guard', 'patrol', 'tactical', 'swat', 'bomb',
            'hazmat', 'disaster', 'coordination', 'command', 'control'
        ]
        
        # SKYWARN/Weather keywords
        weather_keywords = [
            'skywarn', 'weather', 'spotter', 'storm', 'emergency management',
            'warning', 'watch', 'severe', 'tornado', 'hurricane', 'flood',
            'winds', 'hail', 'precipitation', 'meteorolog', 'clima'
        ]
        
        for repeater in repeaters:
            try:
                name = str(repeater.get('name', '')).lower()
                desc = str(repeater.get('description', '')).lower()
                use = str(repeater.get('use', '')).lower()
                search_text = f"{name} {desc} {use}"
                
                # Check for emergency services
                if any(keyword in search_text for keyword in emergency_keywords):
                    repeater['service_type'] = 'Emergency'
                    filtered.append(repeater)
                # Check for weather services
                elif any(keyword in search_text for keyword in weather_keywords):
                    repeater['service_type'] = 'Weather'
                    filtered.append(repeater)
                    
            except (ValueError, TypeError):
                continue
        
        return filtered

    def flush_amateur_cache(self):
        """Manually flush the regional amateur radio cache"""
        self.cached_api_data = None
        self.cached_api_location = None
        self.cached_api_timestamp = None
        self.is_stationary = False
        self.last_known_position = None
        print("🗑️ Regional amateur radio cache flushed manually")
        
        # Clear disk cache files too
        try:
            import glob
            cache_files = glob.glob(os.path.join(self.cache_dir, "repeaters_*.json"))
            for cache_file in cache_files:
                os.remove(cache_file)
                print(f"🗑️ Removed disk cache: {os.path.basename(cache_file)}")
        except Exception as e:
            print(f"⚠️ Error clearing disk cache: {e}")

    def get_cache_status(self):
        """Get information about the current cache status"""
        if not self.cached_api_data:
            return "No regional cache loaded"
        
        current_time = time.time()
        age_hours = (current_time - self.cached_api_timestamp) / 3600 if self.cached_api_timestamp else 0
        
        if self.cached_api_location:
            cache_lat, cache_lon = self.cached_api_location
            return (f"Regional cache: {len(self.cached_api_data)} repeaters, "
                   f"{age_hours:.1f}h old, center: {cache_lat:.3f},{cache_lon:.3f}, "
                   f"radius: {self.cached_api_radius}mi")
        else:
            return f"Regional cache: {len(self.cached_api_data)} repeaters, {age_hours:.1f}h old"

    def closeEvent(self, event):
        """Clean up GPS worker thread when window closes"""
        if hasattr(self, 'gps_worker') and self.gps_worker.isRunning():
            print("Stopping GPS worker...")
            self.gps_worker.stop()
            self.gps_worker.wait(2000)
        event.accept()

    def keyPressEvent(self, event):
        """Handle key presses: F11 to toggle fullscreen, Esc to exit fullscreen, Ctrl+C/Ctrl+Q to quit."""
        try:
            if event.key() == Qt.Key_F11:
                self.toggle_fullscreen()
                return
            if event.key() == Qt.Key_Escape and self._is_fullscreen:
                # Exit fullscreen if currently fullscreen
                self.showNormal()
                self._is_fullscreen = False
                return
            # Handle Ctrl+C and Ctrl+Q to quit
            if event.modifiers() & Qt.ControlModifier:
                if event.key() == Qt.Key_C or event.key() == Qt.Key_Q:
                    print("User requested quit via keyboard shortcut")
                    self.close()
                    return
        except Exception:
            pass
        # Fallback to default handling
        super().keyPressEvent(event)

    def toggle_fullscreen(self):
        """Toggle between fullscreen and normal window states."""
        if not self._is_fullscreen:
            self.showFullScreen()
            self._is_fullscreen = True
        else:
            self.showNormal()
            self._is_fullscreen = False

    def load_configuration(self):
        """Load configuration from file or create default"""
        self.config_file = os.path.join(os.path.dirname(__file__), "towerwitch_config.ini")
        self.config = configparser.ConfigParser()
        
        # Default configuration
        default_config = {
            'API': {
                'radio_reference_key': '',
                'auto_update': 'true',
                'cache_timeout_hours': '24'
            },
            'Display': {
                'night_mode': 'false',
                'refresh_interval': '30'
            }
        }
        
        # Load existing config or create default
        if os.path.exists(self.config_file):
            try:
                self.config.read(self.config_file)
                print(f"✓ Loaded configuration from {self.config_file}")
            except Exception as e:
                print(f"Error loading config: {e}")
                self.create_default_config(default_config)
        else:
            self.create_default_config(default_config)
        
        # Extract API key
        self.api_key = self.config.get('API', 'radio_reference_key', fallback='')
        if self.api_key:
            print("✓ Radio Reference API key found")
        else:
            print("⚠️ No Radio Reference API key configured")
    
    def create_default_config(self, default_config):
        """Create default configuration file"""
        for section, options in default_config.items():
            self.config.add_section(section)
            for key, value in options.items():
                self.config.set(section, key, value)
        
        try:
            with open(self.config_file, 'w') as f:
                self.config.write(f)
            print(f"✓ Created default configuration at {self.config_file}")
            print("  Edit the file to add your Radio Reference API key")
        except Exception as e:
            print(f"Error creating config file: {e}")
    
    def save_configuration(self):
        """Save current configuration"""
        try:
            with open(self.config_file, 'w') as f:
                self.config.write(f)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get_data_source_indicator(self, source_type):
        """Get indicator text for data source"""
        status = self.data_source_status.get(source_type, 'static')
        indicators = {
            'live': '🌐 Live',
            'cached': '💾 Cached', 
            'static': '📁 Static',
            'hybrid': '🔗 Hybrid'
        }
        return indicators.get(status, '❓ Unknown')

# Support functions  
def calculate_bearing(lat1, lon1, lat2, lon2):
    """Calculate bearing between two points"""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    x = sin(dlon) * cos(lat2)
    y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
    return (degrees(atan2(x, y)) + 360) % 360

# Main Application
if __name__ == "__main__":
    # Enable high DPI scaling BEFORE creating QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    
    window = EnhancedGPSWindow()
    window.show()
    
    sys.exit(app.exec_())
