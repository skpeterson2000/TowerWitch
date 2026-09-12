#!/usr/bin/env python3
"""Says why the GPS is or is not tracking, in one run.

    python3 gps_doctor.py            # watch gpsd for 15 s and give a verdict
    python3 gps_doctor.py -s 30      # watch longer
    python3 gps_doctor.py --host pi  # a gpsd on another machine

Checks, in the order they fail in practice: is gpsd there, does it have a
receiver, is the receiver talking, is there a fix, does the position move,
and does the fix carry speed and heading. Each verdict names the next thing
to do. Exit status 0 means tracking.
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time

WATCH = b'?WATCH={"enable":true,"json":true}\n'


def say(tag, text):
    print(f"[{tag:>4}] {text}")


def gpsd_options():
    """GPSD_OPTIONS from /etc/default/gpsd, or None if unreadable."""
    try:
        with open('/etc/default/gpsd') as f:
            m = re.search(r'^GPSD_OPTIONS="?([^"\n]*)"?', f.read(), re.M)
            return m.group(1) if m else ''
    except OSError:
        return None


def gpsd_version():
    try:
        out = subprocess.run(['gpsd', '-V'], capture_output=True, text=True, timeout=5)
        return (out.stdout or out.stderr).strip()
    except Exception:
        return 'unknown'


def collect(host, port, seconds):
    """Everything gpsd says in the window, sorted by class."""
    got = {'DEVICES': [], 'DEVICE': [], 'TPV': [], 'SKY': [], 'VERSION': []}
    sock = socket.create_connection((host, port), timeout=5.0)
    sock.settimeout(1.0)
    sock.sendall(WATCH)
    buffer = b''
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            data = sock.recv(4096)
        except socket.timeout:
            continue
        if not data:
            break
        buffer += data
        while b'\n' in buffer:
            line, buffer = buffer.split(b'\n', 1)
            try:
                msg = json.loads(line.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            got.setdefault(msg.get('class'), []).append(msg)
    sock.close()
    return got


def last_log_lines(path, patterns, count=3):
    """The last few lines of TowerWitch's log that match any pattern."""
    try:
        with open(path, errors='replace') as f:
            lines = [l.rstrip() for l in f if any(p in l for p in patterns)]
        return lines[-count:]
    except OSError:
        return []


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--host', default='localhost')
    ap.add_argument('--port', type=int, default=2947)
    ap.add_argument('-s', '--seconds', type=int, default=15, help='how long to watch (15)')
    args = ap.parse_args()

    opts = gpsd_options()
    say('gpsd', f"{gpsd_version()}; GPSD_OPTIONS={opts!r}" if opts is not None
        else f"{gpsd_version()}; /etc/default/gpsd not readable")

    here = os.path.dirname(os.path.abspath(__file__))
    for line in last_log_lines(os.path.join(here, 'logs', 'towerwitch.log'),
                               ['gpsd device', 'gpsd devices', '[GPS]', 'No report', 'fix lost']):
        say('log', line)

    say('...', f"watching gpsd at {args.host}:{args.port} for {args.seconds}s")
    try:
        got = collect(args.host, args.port, args.seconds)
    except OSError as e:
        say('FAIL', f"cannot reach gpsd: {e}")
        say('next', "systemctl status gpsd gpsd.socket; is it listening on 2947?")
        return 1

    devices = []
    for msg in got['DEVICES']:
        devices = msg.get('devices', [])
    for msg in got['DEVICE']:
        if msg.get('activated'):
            devices = [msg]
    if not devices:
        say('FAIL', "gpsd has no receiver")
        say('next', "ls /dev/ttyACM* /dev/ttyUSB*; lsusb; journalctl -u gpsd -b; "
                    "unplug and replug the receiver")
        return 1
    dev = devices[-1]
    driver = dev.get('driver', 'not identified yet')
    say('dev', f"{dev.get('path')} driver={driver} bps={dev.get('bps')}")

    tpv = got['TPV']
    used = seen = 0
    for msg in got['SKY']:
        sats = msg.get('satellites', [])
        seen = len(sats)
        used = sum(1 for s in sats if s.get('used'))
    if not tpv:
        say('FAIL', f"receiver attached but silent for {args.seconds}s (driver {driver})")
        say('next', "the receiver is not producing sentences; power, cable, port; "
                    "gpsmon shows what arrives")
        return 1

    fixes = [m for m in tpv if m.get('mode', 0) >= 2 and m.get('lat') is not None]
    say('tpv', f"{len(tpv)} reports, {len(fixes)} with a fix; satellites used {used} of {seen} seen")
    if not fixes:
        say('FAIL', f"no fix (mode {max(m.get('mode', 0) for m in tpv)})")
        say('next', "sky view and time; a cold receiver can take minutes; "
                    f"{used} of {seen} satellites used says how close it is")
        return 1

    positions = {(m['lat'], m['lon']) for m in fixes}
    if len(fixes) >= 10 and len(positions) == 1:
        # A live receiver jitters by centimetres every second even parked;
        # an identical position ten times running is a stale fix re-stamped.
        say('FAIL', f"position frozen: {len(fixes)} fixes, all at "
                    f"{fixes[0]['lat']:.7f},{fixes[0]['lon']:.7f}")
        if driver.startswith('u-blox'):
            say('why', "gpsd switched the receiver to binary mode and stopped asking "
                       "it where it is (gpsd 3.22 with a u-blox 7)")
            if opts is not None and '-b' not in opts.split():
                say('next', 'put -b in GPSD_OPTIONS in /etc/default/gpsd, then '
                            'sudo systemctl restart gpsd.socket gpsd')
            else:
                say('next', "-b is set; gpsd should not have switched drivers - "
                            "replug the receiver and run this again")
        else:
            say('next', f"driver {driver} is not known to do this; gpsmon shows whether "
                        "the receiver itself is moving")
        return 1

    speeds = [m['speed'] for m in fixes if 'speed' in m]
    tracks = [m['track'] for m in fixes if 'track' in m]
    mph = (max(speeds) * 2.23694) if speeds else 0.0
    say(' ok ', f"tracking: {len(positions)} distinct positions in {len(fixes)} fixes; "
                f"up to {mph:.0f} mph; heading {'present' if tracks else 'absent (standing still)'}")
    if mph > 2 and not tracks:
        say('warn', "moving but gpsd sends no heading; the GPS page will show ---")
    return 0


if __name__ == '__main__':
    sys.exit(main())
