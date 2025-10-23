#!/usr/bin/env python3
"""
Simple UDP listener to test TowerWitch UDP broadcasting
"""
import socket
import json
import sys
from datetime import datetime

def listen_for_udp():
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        # Bind to all interfaces on port 12345
        sock.bind(('', 12345))
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Listening for UDP broadcasts on port 12345...")
        print("Press Ctrl+C to stop")
        print("-" * 60)
        
        while True:
            try:
                # Receive data
                data, addr = sock.recvfrom(1024)
                timestamp = datetime.now().strftime('%H:%M:%S')
                
                print(f"[{timestamp}] Received from {addr[0]}:{addr[1]}")
                
                # Try to decode as JSON
                try:
                    json_data = json.loads(data.decode('utf-8'))
                    print(f"JSON Data: {json.dumps(json_data, indent=2)}")
                except json.JSONDecodeError:
                    print(f"Raw Data: {data.decode('utf-8', errors='replace')}")
                except UnicodeDecodeError:
                    print(f"Binary Data: {data}")
                
                print("-" * 60)
                
            except socket.timeout:
                continue
            except KeyboardInterrupt:
                print("\nStopping listener...")
                break
            except Exception as e:
                print(f"Error receiving data: {e}")
                
    except Exception as e:
        print(f"Error setting up listener: {e}")
        sys.exit(1)
    finally:
        sock.close()

if __name__ == "__main__":
    listen_for_udp()