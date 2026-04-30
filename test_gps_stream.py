#!/usr/bin/env python3
"""Test GPS data streaming methods"""
import sys
import time
sys.path.insert(0, '/home/pi/TowerWitch/.venv/lib/python3.11/site-packages')

try:
    import gpsd
    print("Connecting to gpsd...")
    gpsd.connect()
    print("✓ Connected\n")
    
    print("Testing get_current() method:")
    print("-" * 50)
    for i in range(5):
        packet = gpsd.get_current()
        print(f"Packet {i+1}: Mode={packet.mode}, Lat={packet.lat}, Lon={packet.lon}, Sats={getattr(packet, 'sats', 'N/A')}")
        time.sleep(1)
    
    print("\n" + "="*50)
    print("If all packets show 0,0, gpsd needs to be restarted")
    print("Try: sudo systemctl restart gpsd")
    print("Then wait 30 seconds for GPS to get a fix")
    
except Exception as e:
    print(f"Error: {e}")
