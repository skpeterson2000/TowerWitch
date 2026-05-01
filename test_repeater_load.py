#!/usr/bin/env python3
"""Test script to verify Repeater_Book_Minnesota.csv loading"""

import csv
import os

# Count repeaters in the file
csv_file = 'data/Repeater_Book_Minnesota.csv'

if os.path.exists(csv_file):
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        print(f"[OK] Found {len(rows)} total rows in {csv_file}")
        
        # Show first 3 entries
        print("\nFirst 3 repeaters:")
        for i, row in enumerate(rows[:3]):
            print(f"  {i+1}. {row.get('Call')} @ {row.get('Output Freq')} MHz - {row.get('Location')}, {row.get('County')}")
        
        # Count by band
        bands = {}
        for row in rows:
            freq = float(row.get('Output Freq', '0'))
            if 28 <= freq <= 30:
                band = '10m'
            elif 50 <= freq <= 54:
                band = '6m'
            elif 144 <= freq <= 148:
                band = '2m'
            elif 220 <= freq <= 225:
                band = '1.25m'
            elif 420 <= freq <= 450:
                band = '70cm'
            elif 1240 <= freq <= 1300:
                band = '23cm'
            else:
                band = 'other'
            
            bands[band] = bands.get(band, 0) + 1
        
        print(f"\nBand breakdown:")
        for band, count in sorted(bands.items()):
            print(f"  {band}: {count} repeaters")
else:
    print(f"[ERROR] File not found: {csv_file}")
