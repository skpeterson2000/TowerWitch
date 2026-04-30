#!/usr/bin/env python3
"""Test GPS connection"""
import sys
import time
sys.path.insert(0, '/home/pi/TowerWitch/.venv/lib/python3.11/site-packages')

try:
    import gpsd
    print("✓ gpsd module imported successfully")
    
    # Try different connection methods
    connection_methods = [
        ("Default (localhost:2947)", lambda: gpsd.connect()),
        ("Explicit localhost", lambda: gpsd.connect(host="localhost")),
        ("127.0.0.1", lambda: gpsd.connect(host="127.0.0.1")),
        ("localhost:2947", lambda: gpsd.connect(host="localhost", port=2947)),
    ]
    
    connected = False
    for method_name, connect_func in connection_methods:
        try:
            print(f"\nTrying: {method_name}...")
            connect_func()
            print(f"✓ Connected using: {method_name}")
            connected = True
            break
        except Exception as e:
            print(f"✗ Failed: {e}")
    
    if connected:
        # Try to get GPS data
        for i in range(5):
            try:
                packet = gpsd.get_current()
                print(f"\n✓ GPS Data (attempt {i+1}):")
                print(f"  Mode: {packet.mode} ({'No Fix' if packet.mode < 2 else '2D Fix' if packet.mode == 2 else '3D Fix'})")
                print(f"  Latitude: {packet.lat}")
                print(f"  Longitude: {packet.lon}")
                print(f"  Altitude: {packet.alt}m")
                print(f"  Satellites: {getattr(packet, 'sats', 'N/A')}")
                
                if packet.mode >= 2:
                    print("\n✓ GPS is working correctly!")
                    sys.exit(0)
                else:
                    print("  Waiting for fix...")
                    time.sleep(2)
                    
            except Exception as e:
                print(f"✗ Error reading GPS: {e}")
                time.sleep(1)
        
        print("\n✗ GPS connected but no fix acquired")
    else:
        print("\n✗ Could not connect to gpsd")
        print("\nTroubleshooting:")
        print("1. Check if gpsd is running: sudo systemctl status gpsd")
        print("2. Check if cgps works: cgps -s")
        print("3. Check listening port: sudo netstat -tlnp | grep gpsd")
        
except ImportError as e:
    print(f"✗ Could not import gpsd: {e}")
    print("Install with: pip install gpsd-py3")
