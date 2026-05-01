#!/usr/bin/env python3
"""
Convert TowerWitch CSV data files to unified JSON format with pre-geocoded coordinates.
This eliminates network calls during app startup.
"""

import json
import csv
import os
import time
from urllib import request, parse
from urllib.error import URLError

def geocode_location(city, county, state='Minnesota'):
    """Geocode a location using Nominatim (OpenStreetMap)"""
    try:
        queries = []
        if city and city.strip():
            queries.append(f"{city}, {county} County, {state}")
            queries.append(f"{city}, {state}")
        if county and county.strip():
            queries.append(f"{county} County, {state}")
        
        headers = {'User-Agent': 'TowerWitch-Data-Converter/1.0'}
        
        for query in queries:
            try:
                url = f"https://nominatim.openstreetmap.org/search?format=json&q={parse.quote(query)}&limit=1"
                req = request.Request(url, headers=headers)
                
                with request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode())
                    
                    if data and len(data) > 0:
                        lat = float(data[0]['lat'])
                        lon = float(data[0]['lon'])
                        print(f"  [OK] Geocoded: {query} -> {lat:.4f}, {lon:.4f}")
                        time.sleep(2.0)  # Respect Nominatim rate limit - be conservative
                        return lat, lon
            except Exception as e:
                print(f"  [WARN] Failed: {query} - {str(e)[:50]}")
                time.sleep(2.0)  # Wait before trying next query
                continue
        
        # Fallback to Minnesota center
        print(f"  [INFO] Using fallback coordinates for {city}, {county}")
        return 46.0, -94.0
        
    except Exception as e:
        print(f"  [ERROR] Geocoding error: {str(e)[:50]}")
        return 46.0, -94.0

def load_existing_coords():
    """Load existing coordinate mappings to avoid re-geocoding"""
    coords_file = 'data/location_coordinates.json'
    if os.path.exists(coords_file):
        with open(coords_file, 'r') as f:
            return json.load(f)
    return {}

def save_coords_cache(coords_cache):
    """Save coordinate cache for future use"""
    with open('data/location_coordinates.json', 'w') as f:
        json.dump(coords_cache, f, indent=2)
    print(f"\n[OK] Saved {len(coords_cache)} locations to coordinate cache")

def get_coords_with_cache(city, county, state, coords_cache):
    """Get coordinates with caching to avoid repeated API calls"""
    cache_key = f"{city}|{county}|{state}".lower()
    
    if cache_key in coords_cache:
        return coords_cache[cache_key]['lat'], coords_cache[cache_key]['lon']
    
    lat, lon = geocode_location(city, county, state)
    coords_cache[cache_key] = {'lat': lat, 'lon': lon}
    return lat, lon

def convert_skywarn_csv():
    """Convert sky_warn.csv to JSON"""
    print("\n=== Converting Skywarn/ARES Repeaters ===")
    csv_file = 'data/sky_warn.csv'
    
    if not os.path.exists(csv_file):
        print(f"[WARN] File not found: {csv_file}")
        return []
    
    coords_cache = load_existing_coords()
    repeaters = []
    
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                output_freq = row.get('Output Freq', '0')
                if not output_freq or float(output_freq) == 0:
                    continue
                
                city = row.get('Location', '').strip()
                county = row.get('County', '').strip()
                state = row.get('State', 'Minnesota').strip()
                
                # Get coordinates
                lat, lon = get_coords_with_cache(city, county, state, coords_cache)
                
                repeater = {
                    'type': 'skywarn',
                    'call': row.get('Call', 'N0CALL').strip(),
                    'location': city,
                    'county': county,
                    'state': state,
                    'output_freq': float(output_freq),
                    'input_freq': float(row.get('Input Freq', '0') or '0'),
                    'offset': row.get('Offset', '').strip(),
                    'uplink_tone': row.get('Uplink Tone', '').strip() or 'CSQ',
                    'downlink_tone': row.get('Downlink Tone', '').strip() or 'CSQ',
                    'modes': row.get('Modes', 'FM').strip(),
                    'digital_access': row.get('Digital Access', '').strip(),
                    'lat': lat,
                    'lon': lon
                }
                repeaters.append(repeater)
                
            except (ValueError, KeyError) as e:
                print(f"  [SKIP] Skipping row: {e}")
                continue
    
    save_coords_cache(coords_cache)
    print(f"[OK] Converted {len(repeaters)} Skywarn repeaters")
    return repeaters

def convert_fusion_csv():
    """Convert fusion_repeater_boook.csv to JSON"""
    print("\n=== Converting Fusion Repeaters ===")
    csv_file = 'data/fusion_repeater_boook.csv'
    
    if not os.path.exists(csv_file):
        print(f"[WARN] File not found: {csv_file}")
        return []
    
    coords_cache = load_existing_coords()
    repeaters = []
    
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                output_freq = row.get('Output Freq', '0')
                if not output_freq or float(output_freq) == 0:
                    continue
                
                city = row.get('Location', '').strip()
                county = row.get('County', '').strip()
                state = row.get('State', 'Minnesota').strip()
                
                # Get coordinates
                lat, lon = get_coords_with_cache(city, county, state, coords_cache)
                
                repeater = {
                    'type': 'fusion',
                    'call': row.get('Call', 'N0CALL').strip(),
                    'location': city,
                    'county': county,
                    'state': state,
                    'output_freq': float(output_freq),
                    'input_freq': float(row.get('Input Freq', '0') or '0'),
                    'offset': row.get('Offset', '').strip(),
                    'uplink_tone': row.get('Uplink Tone', '').strip() or 'CSQ',
                    'downlink_tone': row.get('Downlink Tone', '').strip() or 'CSQ',
                    'modes': row.get('Modes', 'FM').strip(),
                    'digital_access': row.get('Digital Access', '').strip(),
                    'lat': lat,
                    'lon': lon
                }
                repeaters.append(repeater)
                
            except (ValueError, KeyError) as e:
                print(f"  [SKIP] Skipping row: {e}")
                continue
    
    save_coords_cache(coords_cache)
    print(f"[OK] Converted {len(repeaters)} Fusion repeaters")
    return repeaters

def convert_county_csv(csv_file, county_name):
    """Convert county radio reference CSV to JSON"""
    print(f"\n=== Converting {county_name} County Data ===")
    
    if not os.path.exists(csv_file):
        print(f"[WARN] File not found: {csv_file}")
        return []
    
    coords_cache = load_existing_coords()
    frequencies = []
    
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                output_freq = row.get('Frequency Output', '0')
                if not output_freq or float(output_freq) == 0:
                    continue
                
                category = row.get('Agency/Category', '').strip()
                tag = row.get('Tag', '').strip()
                description = row.get('Description', '').strip()
                
                # Determine type
                freq_type = 'other'
                if 'amateur' in category.lower() or 'ham' in tag.lower():
                    freq_type = 'amateur'
                elif 'aircraft' in tag.lower() or 'aviation' in category.lower():
                    freq_type = 'aviation'
                
                # Try to extract location from description
                location = description
                
                # Get coordinates - use county as location for county-wide systems
                lat, lon = get_coords_with_cache(county_name, county_name, 'Minnesota', coords_cache)
                
                entry = {
                    'type': freq_type,
                    'call': row.get('FCC Callsign', '').strip(),
                    'location': location,
                    'county': county_name,
                    'state': 'Minnesota',
                    'category': category,
                    'description': description,
                    'alpha_tag': row.get('Alpha Tag', '').strip(),
                    'output_freq': float(output_freq),
                    'input_freq': float(row.get('Frequency Input', '0') or '0'),
                    'uplink_tone': row.get('PL Input Tone', '').strip() or 'CSQ',
                    'downlink_tone': row.get('PL Output Tone', '').strip() or 'CSQ',
                    'mode': row.get('Mode', 'FM').strip(),
                    'tag': tag,
                    'lat': lat,
                    'lon': lon
                }
                frequencies.append(entry)
                
            except (ValueError, KeyError) as e:
                print(f"  [SKIP] Skipping row: {e}")
                continue
    
    save_coords_cache(coords_cache)
    print(f"[OK] Converted {len(frequencies)} {county_name} County frequencies")
    return frequencies

def convert_simplex_csv():
    """Convert amateur_simplex.csv to JSON"""
    print("\n=== Converting Amateur Simplex Frequencies ===")
    csv_file = 'data/amateur_simplex.csv'
    
    if not os.path.exists(csv_file):
        print(f"[WARN] File not found: {csv_file}")
        return []
    
    frequencies = []
    
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                output_freq = row.get('Frequency Output', '0')
                if not output_freq or float(output_freq) == 0:
                    continue
                
                entry = {
                    'type': 'simplex',
                    'call': row.get('FCC Callsign', '').strip(),
                    'description': row.get('Description', '').strip(),
                    'alpha_tag': row.get('Alpha Tag', '').strip(),
                    'output_freq': float(output_freq),
                    'input_freq': float(row.get('Frequency Input', '0') or '0'),
                    'mode': row.get('Mode', 'FM').strip(),
                    'tag': row.get('Tag', '').strip(),
                    'lat': 44.9778,  # Center on Minneapolis (simplex is not location-specific)
                    'lon': -93.2650
                }
                frequencies.append(entry)
                
            except (ValueError, KeyError) as e:
                print(f"  [SKIP] Skipping row: {e}")
                continue
    
    print(f"[OK] Converted {len(frequencies)} simplex frequencies")
    return frequencies

def convert_interop_csv():
    """Convert interoperability.csv to JSON"""
    print("\n=== Converting Interoperability Channels ===")
    csv_file = 'data/interoperability.csv'
    
    if not os.path.exists(csv_file):
        print(f"[WARN] File not found: {csv_file}")
        return []
    
    frequencies = []
    
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                output_freq = row.get('Frequency Output', '0')
                if not output_freq or float(output_freq) == 0:
                    continue
                
                entry = {
                    'type': 'interop',
                    'description': row.get('Description', '').strip(),
                    'alpha_tag': row.get('Alpha Tag', '').strip(),
                    'output_freq': float(output_freq),
                    'input_freq': float(row.get('Frequency Input', '0') or '0'),
                    'uplink_tone': row.get('PL Input Tone', '').strip() or 'CSQ',
                    'downlink_tone': row.get('PL Output Tone', '').strip() or 'CSQ',
                    'mode': row.get('Mode', 'FM').strip(),
                    'category': row.get('Agency/Category', '').strip(),
                    'tag': row.get('Tag', '').strip(),
                    'lat': 44.9778,  # Statewide channels
                    'lon': -93.2650
                }
                frequencies.append(entry)
                
            except (ValueError, KeyError) as e:
                print(f"  [SKIP] Skipping row: {e}")
                continue
    
    print(f"[OK] Converted {len(frequencies)} interop channels")
    return frequencies

def main():
    """Main conversion function"""
    print("=" * 60)
    print("TowerWitch CSV to JSON Converter")
    print("=" * 60)
    
    all_data = {
        'skywarn': convert_skywarn_csv(),
        'fusion': convert_fusion_csv(),
        'amateur_crow_wing': convert_county_csv('data/crow_wing_county_radio_reference.csv', 'Crow Wing'),
        'amateur_cass': convert_county_csv('data/cass_county_radio_reference.csv', 'Cass'),
        'simplex': convert_simplex_csv(),
        'interop': convert_interop_csv()
    }
    
    # Save unified JSON file
    output_file = 'data/frequencies.json'
    with open(output_file, 'w') as f:
        json.dump(all_data, f, indent=2)
    
    print("\n" + "=" * 60)
    print(f"[OK] Conversion complete! Saved to {output_file}")
    print("=" * 60)
    
    # Print summary
    total = sum(len(data) for data in all_data.values())
    print(f"\nTotal frequencies: {total}")
    for category, data in all_data.items():
        print(f"  - {category}: {len(data)}")
    
    print("\n[INFO] You can now update TowerWitch_Tkinter.py to load from frequencies.json")
    print("[INFO] This eliminates network calls during startup!")

if __name__ == '__main__':
    main()
