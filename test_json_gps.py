#!/usr/bin/env python3
"""Test direct JSON socket connection to gpsd"""
import socket
import json
import time

print("Testing direct JSON socket to gpsd...")
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 2947))
    sock.settimeout(2.0)
    
    # Enable watch mode and request JSON
    sock.sendall(b'?WATCH={"enable":true,"json":true}\n')
    print("✓ Connected to gpsd on port 2947")
    print("Listening for GPS data...\n")
    
    buffer = b''
    packets_received = 0
    tpv_count = 0
    
    for i in range(20):  # Read for ~10 seconds
        try:
            data = sock.recv(4096)
            if not data:
                print("Socket closed")
                break
            
            buffer += data
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                if not line:
                    continue
                
                try:
                    msg = json.loads(line.decode('utf-8'))
                    packets_received += 1
                    
                    # Look for TPV (Time-Position-Velocity) messages
                    if msg.get('class') == 'TPV':
                        tpv_count += 1
                        lat = msg.get('lat', 0.0)
                        lon = msg.get('lon', 0.0)
                        mode = msg.get('mode', 0)
                        alt = msg.get('alt', 0.0)
                        
                        print(f"TPV #{tpv_count}:")
                        print(f"  Mode: {mode} ({'No Fix' if mode < 2 else '2D' if mode == 2 else '3D'})")
                        print(f"  Lat:  {lat:.6f}")
                        print(f"  Lon:  {lon:.6f}")
                        print(f"  Alt:  {alt:.1f}m")
                        
                        if lat != 0.0 or lon != 0.0:
                            print("  ✓ Valid coordinates received!")
                        else:
                            print("  ✗ Still showing 0,0")
                        print()
                        
                        if tpv_count >= 3:
                            print(f"✓ Received {tpv_count} TPV packets, test complete!")
                            sock.close()
                            exit(0)
                            
                except json.JSONDecodeError:
                    pass
                    
        except socket.timeout:
            print(f"[{i+1}/20] Waiting for data...")
            
    sock.close()
    print(f"\nReceived {packets_received} total packets, {tpv_count} TPV packets")
    
    if tpv_count == 0:
        print("\n✗ No TPV packets received!")
        print("Try: sudo systemctl restart gpsd")
    
except Exception as e:
    print(f"✗ Error: {e}")
