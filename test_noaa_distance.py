#!/usr/bin/env python3
"""
Test script to verify NOAA Weather Radio distance calculations
using current approximate coordinates vs. user's actual location
"""

import math

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points using Haversine formula"""
    R = 3959  # Earth radius in miles
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c

# Test coordinates - current location (Brainerd area from GPS)
current_lat = 46.599
current_lon = -94.315

# Current NOAA stations with approximate coordinates
noaa_stations = [
    ("KEC47", "Minneapolis/St. Paul", "162.550", "027017", "45.1", "-93.3"),
    ("WWG56", "Duluth", "162.475", "027017,027037,027137", "46.8", "-92.1"),
    ("WXM65", "Mankato", "162.425", "027013,027103,027143", "44.2", "-94.0"),
    ("KZZ34", "Rochester", "162.525", "027009,027045,027157", "44.0", "-92.5"),
    ("KIF73", "St. Cloud", "162.525", "027145,027171", "45.6", "-94.2"),
]

print("NOAA Weather Radio Distance Test")
print("=================================")
print(f"Current GPS Location: {current_lat:.3f}, {current_lon:.3f}")
print()

distances = []
for call, location, freq, same, lat, lon in noaa_stations:
    distance = calculate_distance(current_lat, current_lon, float(lat), float(lon))
    distances.append((distance, call, location, freq))
    print(f"{call:6} {location:20} {freq} MHz - {distance:5.1f} miles")

print()
print("Sorted by distance:")
distances.sort()
for distance, call, location, freq in distances:
    print(f"{distance:5.1f} mi - {call} {location} ({freq} MHz)")