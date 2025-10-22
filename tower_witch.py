# Tower Witch Module by KC9SP 
# This module provides GPS coordination between users and listed repeater towers.
# It determines the nearest tower based on user GPS coordinates and provides relevant information to OP25.
# It is designed to retrieve tower data from a predefined list of towers, each with their own GPS coordinates, as well as additional metadata.
# It will read tower data from a JSON or CSV file and use that data to find the nearest tower to the user's current location.

import math
import json
import csv
import sys
import logging
from datetime import datetime

# Earth radius constants for different units
EARTH_RADIUS = {
    'km': 6371.0,      # kilometers
    'mi': 3958.8,      # miles
    'nm': 3440.1       # nautical miles
}

def calculate_distance(lat1, lon1, lat2, lon2, unit='mi'):
    """
    Calculate the great-circle distance between two points on the Earth's surface
    
    Args:
        lat1, lon1: Latitude and longitude of first point
        lat2, lon2: Latitude and longitude of second point
        unit: Distance unit - 'km' (kilometers), 'mi' (miles), or 'nm' (nautical miles)
    
    Returns:
        Distance in the specified unit
    """
    if unit not in EARTH_RADIUS:
        raise ValueError(f"Invalid unit '{unit}'. Use 'km', 'mi', or 'nm'")
    
    R = EARTH_RADIUS[unit]
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c
    return distance

def find_nearest_tower(user_lat, user_lon, towers, unit='mi'):
    """
    Find the nearest tower to the user based on GPS coordinates
    
    Args:
        user_lat, user_lon: User's latitude and longitude
        towers: List of tower dictionaries
        unit: Distance unit - 'km', 'mi', or 'nm'
    
    Returns:
        Dictionary of nearest tower with distance added
    """
    nearest_tower = None
    min_distance = float('inf')
    for tower in towers:
        tower_lat, tower_lon = tower['latitude'], tower['longitude']
        distance = calculate_distance(user_lat, user_lon, tower_lat, tower_lon, unit)
        if distance < min_distance:
            min_distance = distance
            nearest_tower = tower.copy()
            nearest_tower['distance'] = distance
            nearest_tower['distance_unit'] = unit
    return nearest_tower

def find_towers_within_range(user_lat, user_lon, towers, max_range, unit='mi'):
    """
    Find all towers within a specified range of the user
    
    Args:
        user_lat, user_lon: User's latitude and longitude
        towers: List of tower dictionaries
        max_range: Maximum distance to search
        unit: Distance unit - 'km', 'mi', or 'nm'
    
    Returns:
        List of towers within range, sorted by distance
    """
    towers_in_range = []
    for tower in towers:
        tower_lat, tower_lon = tower['latitude'], tower['longitude']
        distance = calculate_distance(user_lat, user_lon, tower_lat, tower_lon, unit)
        if distance <= max_range:
            tower_copy = tower.copy()
            tower_copy['distance'] = distance
            tower_copy['distance_unit'] = unit
            towers_in_range.append(tower_copy)
    # Sort by distance
    towers_in_range.sort(key=lambda x: x['distance'])
    return towers_in_range

def load_towers_from_json(file_path):
    """Load tower data from a JSON file"""
    with open(file_path, 'r') as f:
        towers = json.load(f)
    return towers

def load_towers_from_csv(file_path):
    """Load tower data from trs_sites CSV file (compatible with trs_sites_3508.csv format)"""
    towers = []
    with open(file_path, 'r') as f:
        # Use regular csv.reader to get all columns
        reader = csv.reader(f)
        header = next(reader)  # Skip header
        
        for row in reader:
            try:
                # Skip empty rows
                if len(row) < 9:
                    continue
                
                # Parse the known columns
                rfss = row[0] if len(row) > 0 else ''
                site_dec = row[1] if len(row) > 1 else ''
                site_hex = row[2] if len(row) > 2 else ''
                site_nac = row[3] if len(row) > 3 else ''
                description = row[4] if len(row) > 4 else 'Unknown'
                county = row[5] if len(row) > 5 else ''
                
                # Skip rows with empty coordinates
                if len(row) < 8 or not row[6] or not row[7]:
                    continue
                
                lat = float(row[6])
                lon = float(row[7])
                tower_range = row[8] if len(row) > 8 else ''
                
                # Collect frequencies starting from column 9
                control_channels = []
                all_frequencies = []
                
                for i in range(9, len(row)):
                    value = row[i].strip() if row[i] else ''
                    if value:
                        try:
                            # Remove 'c' suffix and check if it's a valid frequency
                            freq_num_str = value.rstrip('c')
                            if freq_num_str.replace('.', '', 1).isdigit():
                                freq_num = float(freq_num_str)
                                # P25 frequencies are in 800-900 MHz range
                                if 800 <= freq_num <= 900:
                                    all_frequencies.append(freq_num_str)
                                    # Check if it's a control channel (ends with 'c')
                                    if value.endswith('c'):
                                        control_channels.append(freq_num_str)
                        except:
                            pass
                
                # Build tower dictionary
                tower = {
                    'rfss': rfss,
                    'site_dec': site_dec,
                    'site_hex': site_hex,
                    'site_nac': site_nac,
                    'description': description,
                    'county': county,
                    'latitude': lat,
                    'longitude': lon,
                    'range': tower_range,
                    'control_channels': control_channels,
                    'frequencies': all_frequencies
                }
                towers.append(tower)
            except (ValueError, IndexError) as e:
                # Skip rows that can't be parsed
                continue
    return towers

def convert_distance(distance, from_unit, to_unit):
    """
    Convert distance from one unit to another
    
    Args:
        distance: Distance value
        from_unit: Source unit ('km', 'mi', or 'nm')
        to_unit: Target unit ('km', 'mi', or 'nm')
    
    Returns:
        Converted distance
    """
    if from_unit not in EARTH_RADIUS or to_unit not in EARTH_RADIUS:
        raise ValueError("Invalid unit. Use 'km', 'mi', or 'nm'")
    
    # Convert to kilometers first, then to target unit
    if from_unit == to_unit:
        return distance
    
    # Conversion ratios relative to kilometers
    to_km = {
        'km': 1.0,
        'mi': 1.60934,      # 1 mile = 1.60934 km
        'nm': 1.852         # 1 nautical mile = 1.852 km
    }
    
    from_km = {
        'km': 1.0,
        'mi': 0.621371,     # 1 km = 0.621371 miles
        'nm': 0.539957      # 1 km = 0.539957 nautical miles
    }
    
    # Convert to km then to target unit
    distance_km = distance * to_km[from_unit]
    result = distance_km * from_km[to_unit]
    return result

def get_unit_label(unit):
    """Get the full label for a unit abbreviation"""
    labels = {
        'km': 'kilometers',
        'mi': 'miles',
        'nm': 'nautical miles'
    }
    return labels.get(unit, unit)

def get_gps_position_gpsd(host='127.0.0.1', port=2947, timeout=10, debug=False):
    """
    Get GPS position from gpsd using gpspipe (from gpsd-clients package)
    This method doesn't require Python GPS libraries, just gpsd-clients
    
    Args:
        host: gpsd host address
        port: gpsd port
        timeout: Connection timeout in seconds
        debug: Enable debug output
    
    Returns:
        Tuple of (latitude, longitude, altitude, fix_quality) or None if unavailable
    """
    import subprocess
    import time
    
    logger = logging.getLogger('tower_witch')
    
    try:
        # Try using gpspipe from gpsd-clients
        cmd = ['gpspipe', '-w', '-n', '10']  # JSON output, limit to 10 messages
        
        if host != '127.0.0.1' or port != 2947:
            # If non-default, we need to set GPSD_HOST environment
            import os
            env = os.environ.copy()
            env['GPSD_HOST'] = f"{host}:{port}"
            logger.debug(f"Starting gpspipe with GPSD_HOST={host}:{port}")
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                      env=env, text=True)
        else:
            logger.debug(f"Starting gpspipe (default host/port)")
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        start_time = time.time()
        lat, lon, alt, mode = None, None, None, 0
        message_count = 0
        
        logger.info(f"Waiting up to {timeout}s for GPS fix...")
        
        # Read gpspipe output
        for line in process.stdout:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                logger.warning(f"Timeout after {timeout}s waiting for GPS fix")
                break
            
            message_count += 1
            logger.debug(f"GPS message {message_count}: {line.strip()[:100]}")
                
            try:
                data = json.loads(line.strip())
                msg_class = data.get('class', 'UNKNOWN')
                logger.debug(f"Message class: {msg_class}")
                
                # Log VERSION and DEVICE messages
                if msg_class == 'VERSION':
                    logger.info(f"gpsd version: {data.get('release', 'unknown')}")
                elif msg_class == 'DEVICES':
                    devices = data.get('devices', [])
                    for dev in devices:
                        logger.info(f"GPS device: {dev.get('path', 'unknown')} - {dev.get('driver', 'unknown')}")
                elif msg_class == 'WATCH':
                    logger.debug(f"WATCH response: {data}")
                
                # Look for TPV (Time-Position-Velocity) messages
                if msg_class == 'TPV':
                    logger.debug(f"TPV message: lat={data.get('lat')}, lon={data.get('lon')}, mode={data.get('mode')}")
                    
                    if 'lat' in data and 'lon' in data and 'mode' in data:
                        lat = data['lat']
                        lon = data['lon']
                        alt = data.get('alt')
                        mode = data['mode']
                        
                        logger.info(f"Got position: lat={lat:.6f}, lon={lon:.6f}, alt={alt}, mode={mode}")
                        
                        # mode: 0=no fix, 1=no fix, 2=2D, 3=3D
                        if mode >= 2:
                            logger.info(f"✓ Valid GPS fix obtained (mode {mode})")
                            process.terminate()
                            return (lat, lon, alt, mode)
                        else:
                            logger.warning(f"GPS position available but no fix (mode {mode})")
                            
            except json.JSONDecodeError as e:
                logger.debug(f"JSON decode error: {e}")
                continue
            except Exception as e:
                logger.error(f"Error parsing GPS message: {e}")
                continue
        
        # Check stderr for errors
        stderr_output = process.stderr.read()
        if stderr_output:
            logger.error(f"gpspipe stderr: {stderr_output}")
        
        process.terminate()
        
        if lat is not None and lon is not None:
            logger.warning(f"Returning position without proper fix: mode={mode}")
            return (lat, lon, alt, mode)
        
        logger.error(f"No GPS position obtained after {message_count} messages")
        return None
        
    except FileNotFoundError:
        logger.error("gpspipe not found!")
        print("\n❌ Error: gpspipe not found. Install gpsd-clients package:")
        print("  sudo apt-get install gpsd-clients  # Debian/Ubuntu")
        print("  sudo yum install gpsd-clients      # RHEL/CentOS")
        return None
    except Exception as e:
        logger.error(f"Exception reading from gpsd: {e}", exc_info=True)
        print(f"\n❌ Error reading from gpsd: {e}")
        return None

def get_gps_position_nmea(device='/dev/ttyUSB0', baudrate=9600, timeout=10):
    """
    Get GPS position directly from NMEA GPS device via serial port
    Requires pyserial package installed
    
    Args:
        device: Serial device path
        baudrate: Serial baudrate
        timeout: Read timeout in seconds
    
    Returns:
        Tuple of (latitude, longitude) or None if unavailable
    """
    try:
        import serial
        import time
        
        ser = serial.Serial(device, baudrate=baudrate, timeout=1)
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            line = ser.readline().decode('ascii', errors='ignore').strip()
            
            # Look for GPGGA or GPRMC sentences
            if line.startswith('$GPGGA') or line.startswith('$GNGGA'):
                parts = line.split(',')
                if len(parts) > 6 and parts[2] and parts[4]:
                    # Parse latitude
                    lat_str = parts[2]
                    lat_dir = parts[3]
                    lat = float(lat_str[:2]) + float(lat_str[2:]) / 60.0
                    if lat_dir == 'S':
                        lat = -lat
                    
                    # Parse longitude
                    lon_str = parts[4]
                    lon_dir = parts[5]
                    lon = float(lon_str[:3]) + float(lon_str[3:]) / 60.0
                    if lon_dir == 'W':
                        lon = -lon
                    
                    ser.close()
                    return (lat, lon, None, None)
        
        ser.close()
        return None
    except ImportError:
        print("Warning: pyserial module not installed. Install with: pip install pyserial")
        return None
    except Exception as e:
        print(f"Error reading from GPS device: {e}")
        return None

def get_gps_position_file(filepath):
    """
    Read GPS position from a file
    File should contain: latitude,longitude
    or JSON: {"latitude": lat, "longitude": lon}
    
    Args:
        filepath: Path to GPS position file
    
    Returns:
        Tuple of (latitude, longitude) or None if unavailable
    """
    try:
        with open(filepath, 'r') as f:
            content = f.read().strip()
            
            # Try JSON first
            try:
                data = json.loads(content)
                if 'latitude' in data and 'longitude' in data:
                    return (float(data['latitude']), float(data['longitude']), None, None)
                elif 'lat' in data and 'lon' in data:
                    return (float(data['lat']), float(data['lon']), None, None)
            except json.JSONDecodeError:
                pass
            
            # Try CSV format
            parts = content.split(',')
            if len(parts) >= 2:
                lat = float(parts[0].strip())
                lon = float(parts[1].strip())
                return (lat, lon, None, None)
        
        return None
    except Exception as e:
        print(f"Error reading GPS position from file: {e}")
        return None

def check_gpsd_running():
    """
    Check if gpsd is running on the system
    
    Returns:
        True if gpsd appears to be running, False otherwise
    """
    import subprocess
    logger = logging.getLogger('tower_witch')
    
    try:
        logger.debug("Checking if gpspipe is available...")
        # Try to connect to gpsd with a quick timeout
        result = subprocess.run(['gpspipe', '-V'], capture_output=True, timeout=2)
        if result.returncode == 0:
            logger.debug(f"gpspipe version: {result.stdout.decode().strip()}")
            # Check if we can actually connect
            logger.debug("Attempting to connect to gpsd...")
            result = subprocess.run(['gpspipe', '-w', '-n', '1'], 
                                  capture_output=True, timeout=3, text=True)
            is_running = result.returncode == 0 or 'class' in result.stdout
            logger.info(f"gpsd running: {is_running}")
            return is_running
        logger.warning("gpspipe not found or failed")
        return False
    except FileNotFoundError:
        logger.error("gpspipe command not found")
        return False
    except subprocess.TimeoutExpired:
        logger.error("Timeout waiting for gpsd")
        return False
    except Exception as e:
        logger.error(f"Error checking gpsd: {e}")
        return False

def get_gps_position(host='127.0.0.1', port=2947, timeout=10):
    """
    Get GPS position from gpsd (simplified wrapper)
    
    Args:
        host: gpsd host address
        port: gpsd port
        timeout: Connection timeout in seconds
    
    Returns:
        Tuple of (latitude, longitude, altitude, fix_quality) or None
    """
    return get_gps_position_gpsd(host, port, timeout)

def save_gps_position_file(latitude, longitude, filepath='gps_position.txt'):
    """
    Save GPS position to a file for later use
    
    Args:
        latitude: Latitude
        longitude: Longitude
        filepath: File path to save to
    """
    try:
        with open(filepath, 'w') as f:
            json.dump({'latitude': latitude, 'longitude': longitude}, f)
        print(f"GPS position saved to {filepath}")
        return True
    except Exception as e:
        print(f"Error saving GPS position: {e}")
        return False

def get_tower_info_string(tower, show_all_units=False):
    """
    Format tower information as a readable string
    
    Args:
        tower: Tower dictionary
        show_all_units: If True, show distance in all units
    
    Returns:
        Formatted string with tower information
    """
    info = f"Tower: {tower['description']}\n"
    info += f"County: {tower['county']}\n"
    info += f"Location: {tower['latitude']}, {tower['longitude']}\n"
    info += f"RFSS: {tower['rfss']}, Site: {tower['site_dec']} (0x{tower['site_hex']})\n"
    info += f"NAC: {tower['site_nac']}\n"
    
    # Range is specified in miles in the CSV (from Radio Reference)
    if tower.get('range'):
        info += f"Tower Range: {tower['range']} miles\n"
    
    if 'distance' in tower:
        unit = tower.get('distance_unit', 'mi')
        info += f"Distance from you: {tower['distance']:.2f} {unit}"
        
        if show_all_units:
            # Show distance in all three units
            dist_km = convert_distance(tower['distance'], unit, 'km')
            dist_mi = convert_distance(tower['distance'], unit, 'mi')
            dist_nm = convert_distance(tower['distance'], unit, 'nm')
            info += f" ({dist_km:.2f} km, {dist_mi:.2f} mi, {dist_nm:.2f} nm)"
        
        info += "\n"
    
    # Show control channels (marked with 'c' in CSV)
    if tower.get('control_channels'):
        info += f"Control Channels: {' MHz, '.join(tower['control_channels'])} MHz"
        info += f" ({len(tower['control_channels'])} total)\n"
    
    # Show total frequency count
    if tower.get('frequencies'):
        info += f"Total Frequencies: {len(tower['frequencies'])}\n"
    
    return info

# Example usage
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Tower Witch - Find nearest P25 towers')
    parser.add_argument('--csv', default='trs_sites_3508.csv', help='CSV file with tower data')
    parser.add_argument('--unit', choices=['km', 'mi', 'nm'], default='mi', help='Distance unit')
    parser.add_argument('--range', type=float, default=30, help='Search range')
    parser.add_argument('--lat', type=float, help='Manual latitude (for testing without GPS)')
    parser.add_argument('--lon', type=float, help='Manual longitude (for testing without GPS)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--log-file', default='tower_witch.log', help='Log file path')
    parser.add_argument('--timeout', type=int, default=10, help='GPS timeout in seconds')
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    
    # Create logger
    logger = logging.getLogger('tower_witch')
    logger.setLevel(log_level)
    
    # File handler with detailed format
    fh = logging.FileHandler(args.log_file)
    fh.setLevel(logging.DEBUG)  # Always log debug to file
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    fh.setFormatter(file_formatter)
    logger.addHandler(fh)
    
    # Console handler
    if args.debug:
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')
        ch.setFormatter(console_formatter)
        logger.addHandler(ch)
    
    logger.info("="*60)
    logger.info(f"Tower Witch started at {datetime.now()}")
    logger.info(f"Arguments: {args}")
    logger.info("="*60)
    
    # Load towers
    try:
        towers = load_towers_from_csv(args.csv)
        print(f"✓ Loaded {len(towers)} towers from {args.csv}")
        logger.info(f"Successfully loaded {len(towers)} towers from {args.csv}")
    except FileNotFoundError:
        print(f"❌ Error: Tower CSV file not found: {args.csv}")
        logger.error(f"Tower CSV file not found: {args.csv}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error loading tower data: {e}")
        logger.error(f"Error loading tower data: {e}", exc_info=True)
        sys.exit(1)
    
    # Get GPS position - use manual if provided, otherwise use gpsd
    print(f"\n=== Getting GPS Position ===")
    logger.info("Starting GPS position acquisition")
    
    gps_result = None
    if args.lat and args.lon:
        # Manual override for testing
        print("📍 Using manual coordinates (testing mode)")
        logger.info(f"Using manual coordinates: {args.lat}, {args.lon}")
        gps_result = (args.lat, args.lon, None, None)
    else:
        # Try to get from gpsd (the normal operating mode)
        print("🛰️  Reading from GPS device via gpsd...")
        logger.info("Attempting to read from gpsd")
        
        # Check if gpsd is running first
        if not check_gpsd_running():
            print("\n⚠️  Warning: Cannot connect to gpsd")
            logger.warning("gpsd does not appear to be running")
        
        gps_result = get_gps_position_gpsd(timeout=args.timeout, debug=args.debug)
    
    if not gps_result:
        print("\n❌ No GPS position available!")
        logger.error("Failed to obtain GPS position")
        
        print("\n📋 Troubleshooting steps:")
        print("\n1. Check if your GPS device is connected:")
        print("   lsusb | grep -i gps")
        print("   ls -la /dev/tty{USB,ACM}*")
        
        print("\n2. Check if you're in the dialout group:")
        print("   groups | grep dialout")
        print("   # If not, add yourself:")
        print("   sudo usermod -a -G dialout $USER")
        print("   # Then log out and back in")
        
        print("\n3. Stop any existing gpsd and start fresh:")
        print("   sudo systemctl stop gpsd")
        print("   sudo killall gpsd")
        print("   sudo gpsd /dev/ttyACM0 -n -N -D 2")
        
        print("\n4. Test GPS data directly:")
        print("   gpspipe -w -n 10")
        print("   # Look for 'TPV' messages with lat/lon")
        
        print("\n5. Check debug log for details:")
        print(f"   tail -f {args.log_file}")
        
        print("\n6. Or test with manual coordinates:")
        print("   python tower_witch.py --lat 44.9778 --lon -93.2650")
        
        sys.exit(1)
    
    user_lat, user_lon, altitude, fix_quality = gps_result
    print(f"✓ GPS Position: {user_lat:.6f}, {user_lon:.6f}")
    logger.info(f"GPS position obtained: {user_lat:.6f}, {user_lon:.6f}")
    
    if altitude:
        print(f"  Altitude: {altitude:.1f} m")
        logger.info(f"Altitude: {altitude:.1f} m")
    if fix_quality:
        fix_types = {0: 'No fix', 1: 'No fix', 2: '2D fix', 3: '3D fix'}
        fix_str = fix_types.get(fix_quality, 'Unknown')
        print(f"  Fix Quality: {fix_str}")
        logger.info(f"Fix quality: {fix_str} (mode {fix_quality})")
    
    # You can specify the unit: 'km' (kilometers), 'mi' (miles), or 'nm' (nautical miles)
    unit = args.unit
    
    print(f"\n=== Using {get_unit_label(unit)} ===\n")
    
    # Find nearest tower
    nearest = find_nearest_tower(user_lat, user_lon, towers, unit=unit)
    if nearest:
        print("Nearest tower:")
        print(get_tower_info_string(nearest, show_all_units=True))
    
    # Find towers within range (adjust value based on your unit)
    search_range = args.range
    nearby = find_towers_within_range(user_lat, user_lon, towers, search_range, unit=unit)
    print(f"Found {len(nearby)} towers within {search_range} {unit}")
    
    if nearby:
        print(f"\nTop 10 nearest towers:")
        for i, tower in enumerate(nearby[:10], 1):
            print(f"{i:2d}. {tower['distance']:6.2f} {unit} - {tower['description']:40s} ({tower['county']})")
    
    # Example: Convert distances between units
    print("\n=== Distance Conversion Examples ===")
    print(f"10 miles = {convert_distance(10, 'mi', 'km'):.2f} km")
    print(f"10 miles = {convert_distance(10, 'mi', 'nm'):.2f} nautical miles")
    print(f"50 km = {convert_distance(50, 'km', 'mi'):.2f} miles")
    print(f"50 km = {convert_distance(50, 'km', 'nm'):.2f} nautical miles")
    print(f"25 nautical miles = {convert_distance(25, 'nm', 'mi'):.2f} miles")
    print(f"25 nautical miles = {convert_distance(25, 'nm', 'km'):.2f} km")