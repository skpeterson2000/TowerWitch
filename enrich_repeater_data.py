#!/usr/bin/env python3
"""
Enrich Repeater_Book_Minnesota.csv with coordinates from existing data sources.
Uses the same 4-tier coordinate matching system as the main app.
"""

import csv
import os

# County center fallbacks (from TowerWitch_Tkinter.py)
COUNTY_CENTERS = {
    'crow wing': (46.450, -94.150),
    'cass': (46.900, -94.350),
    'aitkin': (46.533, -93.717),
    'hennepin': (44.977, -93.265),
    'ramsey': (45.015, -93.100),
    'dakota': (44.668, -93.065),
    'anoka': (45.270, -93.242),
    'washington': (45.050, -92.910),
    'carver': (44.807, -93.798),
    'scott': (44.660, -93.470),
    'olmsted': (44.022, -92.468),
    'st louis': (47.350, -92.450),
    'stearns': (45.558, -94.612),
    'wright': (45.168, -93.965),
    'sherburne': (45.440, -93.767),
    'isanti': (45.487, -93.247),
    'chisago': (45.458, -92.891),
    'pine': (46.083, -92.783),
    'kanabec': (45.950, -93.300),
    'mille lacs': (46.017, -93.650),
    'morrison': (46.017, -94.317),
    'todd': (46.167, -94.933),
    'wadena': (46.433, -95.000),
    'hubbard': (47.017, -94.917),
    'becker': (46.850, -95.717),
    'clay': (46.900, -96.450),
    'beltrami': (47.717, -94.917),
    'itasca': (47.500, -93.500),
    'carlton': (46.583, -92.633),
    'lake': (47.517, -91.183),
}


def load_existing_coordinates():
    """Load coordinates from existing CSV files to build coordinate cache."""
    coord_cache = {
        'frequency': {},  # freq -> (lat, lon)
        'callsign_location': {},  # "callsign|location" -> (lat, lon)
        'city': {}  # city_name -> (lat, lon)
    }
    
    # Load from ARMER (has coordinates)
    armer_file = 'data/trs_sites_3508.csv'
    if os.path.exists(armer_file):
        with open(armer_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('Lat') and row.get('Lon'):
                    try:
                        lat = float(row['Lat'])
                        lon = float(row['Lon'])
                        # Store by description/location
                        if row.get('Description'):
                            city = row['Description'].split('-')[0].strip().lower()
                            coord_cache['city'][city] = (lat, lon)
                    except (ValueError, KeyError):
                        pass
    
    # Load from amateur repeater CSVs
    amateur_files = [
        'data/crow_wing_county_radio_reference.csv',
        'data/cass_county_radio_reference.csv'
    ]
    
    for file_path in amateur_files:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Try to get coordinates if they exist
                    lat = row.get('Latitude') or row.get('Lat')
                    lon = row.get('Longitude') or row.get('Lon')
                    
                    if lat and lon:
                        try:
                            lat_f = float(lat)
                            lon_f = float(lon)
                            
                            # Store by frequency
                            if row.get('Output Frequency'):
                                freq = float(row['Output Frequency'])
                                coord_cache['frequency'][freq] = (lat_f, lon_f)
                            
                            # Store by callsign + location
                            callsign = row.get('Call Sign', '').strip()
                            location = row.get('Location', '').strip()
                            if callsign and location:
                                key = f"{callsign}|{location}".lower()
                                coord_cache['callsign_location'][key] = (lat_f, lon_f)
                            
                            # Store by city
                            if location:
                                city = location.split('-')[0].split(',')[0].strip().lower()
                                if city and city not in coord_cache['city']:
                                    coord_cache['city'][city] = (lat_f, lon_f)
                        except (ValueError, KeyError):
                            pass
    
    print(f"[OK] Loaded coordinate cache:")
    print(f"     - {len(coord_cache['frequency'])} frequency matches")
    print(f"     - {len(coord_cache['callsign_location'])} callsign+location matches")
    print(f"     - {len(coord_cache['city'])} city matches")
    
    return coord_cache


def find_coordinates(row, coord_cache):
    """
    Find coordinates for a repeater using 4-tier matching:
    1. Frequency match
    2. Callsign + Location match
    3. City name match
    4. County center fallback
    """
    output_freq = row.get('Output Freq', '')
    callsign = row.get('Call', '').strip()
    location = row.get('Location', '').strip()
    county = row.get('County', '').strip().lower()
    
    match_method = 'none'
    lat, lon = None, None
    
    # TIER 1: Frequency match
    try:
        freq = float(output_freq)
        if freq in coord_cache['frequency']:
            lat, lon = coord_cache['frequency'][freq]
            match_method = 'frequency'
            return lat, lon, match_method
    except (ValueError, KeyError):
        pass
    
    # TIER 2: Callsign + Location match
    if callsign and location:
        key = f"{callsign}|{location}".lower()
        if key in coord_cache['callsign_location']:
            lat, lon = coord_cache['callsign_location'][key]
            match_method = 'callsign_location'
            return lat, lon, match_method
    
    # TIER 3: City name match
    if location:
        # Clean up location (remove "- Water Tower", "- Hospital", etc.)
        city = location.split('-')[0].split(',')[0].strip().lower()
        if city in coord_cache['city']:
            lat, lon = coord_cache['city'][city]
            match_method = 'city'
            return lat, lon, match_method
    
    # TIER 4: County center fallback
    if county in COUNTY_CENTERS:
        lat, lon = COUNTY_CENTERS[county]
        match_method = 'county_fallback'
        return lat, lon, match_method
    
    return None, None, 'none'


def enrich_repeater_data():
    """Main enrichment function."""
    input_file = 'data/Repeater_Book_Minnesota.csv'
    output_file = 'data/Repeater_Book_Minnesota_enriched.csv'
    
    if not os.path.exists(input_file):
        print(f"[ERROR] Input file not found: {input_file}")
        return
    
    # Load coordinate cache
    coord_cache = load_existing_coordinates()
    
    # Process repeaters
    enriched_rows = []
    match_stats = {
        'frequency': 0,
        'callsign_location': 0,
        'city': 0,
        'county_fallback': 0,
        'none': 0
    }
    
    with open(input_file, 'r') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames + ['Latitude', 'Longitude', 'Match Method']
        
        for row in reader:
            lat, lon, match_method = find_coordinates(row, coord_cache)
            
            # Add coordinate columns
            row['Latitude'] = lat if lat else ''
            row['Longitude'] = lon if lon else ''
            row['Match Method'] = match_method
            
            enriched_rows.append(row)
            match_stats[match_method] += 1
    
    # Write enriched data
    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched_rows)
    
    # Report statistics
    total = len(enriched_rows)
    matched = total - match_stats['none']
    
    print(f"\n[OK] Enrichment complete!")
    print(f"     Total repeaters: {total}")
    print(f"     Successfully matched: {matched} ({100*matched//total}%)")
    print(f"\n     Match breakdown:")
    print(f"     - Frequency matches: {match_stats['frequency']}")
    print(f"     - Callsign+Location: {match_stats['callsign_location']}")
    print(f"     - City matches: {match_stats['city']}")
    print(f"     - County fallbacks: {match_stats['county_fallback']}")
    print(f"     - No match: {match_stats['none']}")
    print(f"\n[OK] Output written to: {output_file}")
    
    # List unmatched for manual review
    if match_stats['none'] > 0:
        print(f"\n[INFO] Unmatched repeaters (need manual coordinate lookup):")
        for row in enriched_rows:
            if row['Match Method'] == 'none':
                print(f"       {row['Call']} @ {row['Output Freq']} MHz - {row['Location']}, {row['County']}")


if __name__ == '__main__':
    enrich_repeater_data()
