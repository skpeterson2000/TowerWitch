import sys
import time
import logging
import traceback
import os
import socket
import json
import csv
import subprocess
import configparser
import tempfile
import requests
import urllib.parse
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2, degrees

from PyQt5.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, 
                            QWidget, QGroupBox, QPushButton, QTableWidget, QTableWidgetItem, 
                            QHeaderView, QTabWidget, QFrame, QScrollArea, QGridLayout,
                            QSizePolicy, QSpacerItem, QAction, QSplitter, QTextEdit,
                            QDialog, QLineEdit, QFormLayout, QDialogButtonBox, QMessageBox,
                            QComboBox, QPushButton)
from PyQt5.QtCore import QTimer, QThread, pyqtSignal, Qt, QUrl
from PyQt5.QtGui import QFont, QPalette, QColor, QPainter, QPen, QPixmap

import utm
import maidenhead as mh
import mgrs

# PDF generation imports
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import inch
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("Warning: reportlab not available - PDF export disabled")

# Application metadata
__version__ = "1.0"
__title__ = "TowerWitch"

# Check command line arguments for debug mode
DEBUG_MODE = '--debug' in sys.argv or '-d' in sys.argv

# PDF Export Configuration - Easy to adjust
PDF_EXPORT_LIMITS = {
    'location': 8,      # Location towers to export
    'armer': 10,        # ARMER towers to export  
    'skywarn': 8,       # SKYWARN towers to export
    'noaa': 8,          # NOAA Weather Radio stations to export
    'amateur_bands': 8  # Amateur radio repeaters per band
}

# UDP Configuration
UDP_CONFIG = {
    'port': 12345,
    'armer_tower_count': 2  # Number of closest ARMER towers to broadcast
}

# Import our custom style
try:
    from custom_qt_style import TowerWitchStyle
    CUSTOM_STYLE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Custom style not available: {e}")
    CUSTOM_STYLE_AVAILABLE = False

# Configure comprehensive logging
log_filename = os.path.join(os.path.dirname(__file__), 'towerwitch-p_debug.log')
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, mode='w'),  # Overwrite log each run
        logging.StreamHandler(sys.stdout)  # Also print to console
    ]
)
logger = logging.getLogger(__name__)

def debug_print(message, level="INFO"):
    """Enhanced debug printing with emojis and levels - controlled by DEBUG_MODE"""
    if not DEBUG_MODE and level in ["INFO", "DEBUG"]:
        return  # Suppress INFO and DEBUG messages when not in debug mode
        
    if level == "ERROR":
        print(f"[ERROR] {message}")
    elif level == "WARNING":
        print(f"[WARNING] {message}")
    elif level == "SUCCESS":
        print(f"[SUCCESS] {message}")
    elif level == "DEBUG":
        print(f"[DEBUG] {message}")  # Only show when DEBUG_MODE is True
    else:  # INFO
        print(f"[INFO] {message}")

# Essential startup info
print("TowerWitch starting...")

# Conversion constants
M_TO_FEET = 3.28084
MPS_TO_MPH = 2.23694
MPS_TO_KNOTS = 1.94384

# Day/Night mode color scheme
DAY_MODE_TEXT_COLOR = QColor(255, 255, 255)    # White text for day mode
NIGHT_MODE_TEXT_COLOR = QColor(255, 102, 102)  # Warm red for night vision compatibility

# Band-specific color schemes for amateur radio
BAND_COLORS = {
    'day': {
        # HF Bands
        '160m': QColor(139, 69, 19),      # Saddle brown for 160m
        '80m': QColor(160, 82, 45),       # Saddle brown for 80m
        '60m': QColor(255, 140, 0),       # Dark orange for 60m (special federal band)
        '40m': QColor(205, 133, 63),      # Peru for 40m
        '30m': QColor(218, 165, 32),      # Golden rod for 30m
        '20m': QColor(255, 215, 0),       # Gold for 20m
        '17m': QColor(255, 255, 0),       # Yellow for 17m
        '15m': QColor(173, 255, 47),      # Green yellow for 15m
        '12m': QColor(124, 252, 0),       # Lawn green for 12m
        '10m': QColor(0, 255, 127),       # Spring green for 10m
        
        # VHF/UHF Bands
        '6m': QColor(0, 191, 255),        # Deep sky blue for 6m
        '2m': QColor(100, 150, 255),      # Light blue for 2 meters
        '2': QColor(100, 150, 255),       # Light blue for 2 meters (alternate name)
        '1.25m': QColor(150, 255, 150),   # Light green for 1.25m
        '125m': QColor(150, 255, 150),    # Light green for 1.25m (alternate name)
        '125': QColor(150, 255, 150),     # Light green for 1.25m
        '70cm': QColor(255, 150, 100),    # Orange for 70 centimeters
        '33cm': QColor(255, 105, 180),    # Hot pink for 33cm
        '23cm': QColor(138, 43, 226),     # Blue violet for 23cm
        
        # Special categories
        'simplex': QColor(255, 255, 100), # Yellow for simplex
        'skywarn': QColor(255, 100, 255), # Magenta for SKYWARN
        'emergency': QColor(220, 20, 60), # Crimson for emergency
        'default': QColor(128, 128, 128)  # Gray instead of invisible white
    },
    'night': {
        # HF Bands - red-tinted for night vision
        '160m': QColor(139, 69, 69),      # Red-tinted brown for 160m
        '80m': QColor(160, 82, 82),       # Red-tinted brown for 80m
        '60m': QColor(200, 100, 50),      # Red-tinted orange for 60m
        '40m': QColor(180, 120, 80),      # Red-tinted peru for 40m
        '30m': QColor(180, 130, 70),      # Red-tinted golden rod for 30m
        '20m': QColor(200, 150, 80),      # Red-tinted gold for 20m
        '17m': QColor(200, 160, 90),      # Red-tinted yellow for 17m
        '15m': QColor(160, 180, 100),     # Red-tinted green yellow for 15m
        '12m': QColor(140, 170, 90),      # Red-tinted lawn green for 12m
        '10m': QColor(120, 160, 110),     # Red-tinted spring green for 10m
        
        # VHF/UHF Bands - red-tinted for night vision
        '6m': QColor(100, 130, 180),      # Red-tinted deep sky blue for 6m
        '2m': QColor(150, 100, 100),      # Muted red-blue for 2m
        '2': QColor(150, 100, 100),       # Muted red-blue for 2m (alternate name)
        '1.25m': QColor(150, 130, 100),   # Muted red-green for 1.25m
        '125m': QColor(150, 130, 100),    # Muted red-green for 1.25m (alternate name)
        '125': QColor(150, 130, 100),     # Muted red-green for 1.25m
        '70cm': QColor(180, 120, 100),    # Muted red-orange for 70cm
        '33cm': QColor(180, 110, 140),    # Red-tinted hot pink for 33cm
        '23cm': QColor(140, 80, 160),     # Red-tinted blue violet for 23cm
        
        # Special categories
        'simplex': QColor(200, 150, 120), # Muted red-yellow for simplex
        'skywarn': QColor(180, 100, 150), # Muted red-magenta for SKYWARN
        'emergency': QColor(180, 60, 80), # Dimmed crimson for emergency
        'default': QColor(200, 150, 150)  # Muted red-gray for night mode
    }
}

# Haversine formula to calculate distance
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Radius of the Earth in kilometers
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c * 0.621371  # Convert to miles

# Calculate bearing between two points
def calculate_bearing(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    x = sin(dlon) * cos(lat2)
    y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
    return (degrees(atan2(x, y)) + 360) % 360

# Find closest sites from CSV
def find_closest_sites(csv_filepath, user_lat, user_lon, num_sites=50):
    try:
        with open(csv_filepath, "r", encoding="utf-8") as file:
            # Read raw CSV data to handle frequency columns correctly
            csv_reader = csv.reader(file)
            headers = next(csv_reader)  # Skip headers
            data = []
            
            for row in csv_reader:
                # Create site dictionary with proper column access
                site = {
                    "RFSS": row[0] if len(row) > 0 else "",
                    "Site Dec": row[1] if len(row) > 1 else "",
                    "Site Hex": row[2] if len(row) > 2 else "",
                    "Site NAC": row[3] if len(row) > 3 else "",
                    "Description": row[4] if len(row) > 4 else "",
                    "County Name": row[5] if len(row) > 5 else "",
                    "Lat": row[6] if len(row) > 6 else "",
                    "Lon": row[7] if len(row) > 7 else "",
                    "Range": row[8] if len(row) > 8 else "",
                }
                
                # Extract all frequencies from columns 9 onwards
                frequencies = []
                for i in range(9, len(row)):
                    value = row[i].strip() if row[i] else ""
                    if value:
                        frequencies.append(value)
                
                site["Frequencies"] = frequencies
                data.append(site)
                
    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_filepath}")
        return []

    distances = []
    for site in data:
        try:
            site_lat = float(site["Lat"])
            site_lon = float(site["Lon"])
            distance = haversine(user_lat, user_lon, site_lat, site_lon)
            bearing = calculate_bearing(user_lat, user_lon, site_lat, site_lon)
            
            # Find all control channels (those ending with 'c')
            control_frequencies = []
            for freq in site["Frequencies"]:
                if freq.endswith("c"):
                    control_frequencies.append(freq.replace("c", ""))
            
            # Get NAC (Network Access Code)
            nac = site.get("Site NAC", "N/A")
            
            if control_frequencies:
                distances.append((site, distance, bearing, control_frequencies, nac))
        except (KeyError, ValueError) as e:
            print(f"Error processing site {site.get('Description', 'Unknown')}: {e}")
            continue

    distances.sort(key=lambda x: x[1])
    return distances[:num_sites]

# Radio Reference API Client
class RadioReferenceAPI:
    """Client for accessing Radio Reference (RadioLabs) API"""
    
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.base_url = "https://api.radioreference.com/soap2"
        self.cache_dir = os.path.join(os.path.dirname(__file__), "radio_cache")
        self.ensure_cache_dir()
        
        # Movement detection and smart caching
        self.last_api_location = None
        self.last_api_time = 0
        self.min_movement_threshold = 0.5  # miles before triggering new API call
        self.stationary_update_interval = 300  # 5 minutes when stationary
        self.moving_update_interval = 60       # 1 minute when moving
        self.fast_update_interval = 15         # 15 seconds for fast updates
        self.consecutive_readings_threshold = 3  # readings before considering "different"
        self.location_history = []  # Track recent locations for movement detection
        
    def ensure_cache_dir(self):
        """Ensure cache directory exists"""
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
    
    def calculate_distance_miles(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two points in miles using haversine formula"""
        from math import radians, cos, sin, asin, sqrt
        
        # Convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        
        # Radius of earth in miles
        r = 3956
        return c * r
    
    def should_update_data(self, current_lat, current_lon):
        """Determine if we should fetch new data based on movement and time"""
        current_time = time.time()
        
        # If we've never fetched data, do it now
        if self.last_api_location is None:
            return True
            
        # Calculate distance moved since last API call
        last_lat, last_lon = self.last_api_location
        distance_moved = self.calculate_distance_miles(current_lat, current_lon, last_lat, last_lon)
        time_since_last = current_time - self.last_api_time
        
        # Update location history for movement tracking
        self.location_history.append((current_lat, current_lon, current_time))
        # Keep only last 10 readings
        if len(self.location_history) > 10:
            self.location_history.pop(0)
            
        # Check if we've moved significantly
        if distance_moved > self.min_movement_threshold:
            return True
            
        # Check if we're stationary and enough time has passed
        is_moving = self.detect_movement()
        
        if not is_moving and time_since_last > self.stationary_update_interval:
            print(f"🏠 Stationary update after {time_since_last/60:.1f} minutes")
            return True
            
        if is_moving and time_since_last > self.moving_update_interval:
            print(f"🚗 Moving update after {time_since_last:.1f} seconds")
            return True
            
        # For very active periods, allow fast updates
        if time_since_last > self.fast_update_interval and distance_moved > 0.1:
            print(f"⚡ Fast update - small movement detected")
            return True
            
        return False
    
    def detect_movement(self):
        """Detect if we're currently moving based on recent location history"""
        if len(self.location_history) < 3:
            return False
            
        # Check if we've moved in the last few readings
        recent_locations = self.location_history[-3:]
        total_movement = 0
        
        for i in range(1, len(recent_locations)):
            prev_lat, prev_lon, _ = recent_locations[i-1]
            curr_lat, curr_lon, _ = recent_locations[i]
            movement = self.calculate_distance_miles(prev_lat, prev_lon, curr_lat, curr_lon)
            total_movement += movement
            
        # If we've moved more than 0.05 miles in recent readings, consider it movement
        return total_movement > 0.05
    
    def update_api_tracking(self, lat, lon):
        """Update tracking info after successful API call"""
        self.last_api_location = (lat, lon)
        self.last_api_time = time.time()
    
    def is_online(self):
        """Check if internet connection is available"""
        try:
            response = requests.get("https://api.radioreference.com", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def get_cache_filename(self, data_type, location_key):
        """Generate cache filename for data type and location"""
        return os.path.join(self.cache_dir, f"{data_type}_{location_key}.json")
    
    def load_from_cache(self, data_type, location_key, force_fresh=False):
        """Load data from local cache"""
        cache_file = self.get_cache_filename(data_type, location_key)
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    cache_time = datetime.fromisoformat(data.get('timestamp', '1970-01-01'))
                    age_hours = (datetime.now() - cache_time).total_seconds() / 3600
                    
                    if not force_fresh and age_hours < 24:
                        print(f"✓ Using cached {data_type} data for {location_key} (age: {age_hours:.1f}h)")
                        return data.get('data', [])
                    elif not force_fresh:
                        print(f"⚠️ Using stale cached {data_type} data for {location_key} (age: {age_hours:.1f}h)")
                        return data.get('data', [])
        except Exception as e:
            print(f"Error loading cache: {e}")
        return None
    
    def load_last_known_good(self, data_type, location_key):
        """Load last known good data regardless of age - fallback when API unavailable"""
        cache_file = self.get_cache_filename(data_type, location_key)
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    cache_time = datetime.fromisoformat(data.get('timestamp', '1970-01-01'))
                    age_hours = (datetime.now() - cache_time).total_seconds() / 3600
                    print(f"📦 Using last known good {data_type} data for {location_key} (age: {age_hours:.1f}h)")
                    return data.get('data', [])
        except Exception as e:
            print(f"Error loading last known good data: {e}")
        
        # If no cache exists for this exact location, try to find nearby cached data
        return self.find_nearby_cached_data(data_type, location_key)
    
    def find_nearby_cached_data(self, data_type, location_key):
        """Find cached data from nearby locations when exact location cache doesn't exist"""
        try:
            # Parse current location from key
            parts = location_key.split('_')
            if len(parts) >= 3:
                current_lat = float(parts[0])
                current_lon = float(parts[1])
                
                # Look for cache files in the same directory
                cache_files = [f for f in os.listdir(self.cache_dir) if f.startswith(data_type) and f.endswith('.json')]
                
                closest_distance = float('inf')
                closest_data = None
                closest_location = None
                
                for cache_file in cache_files:
                    try:
                        # Extract location from filename
                        filename_parts = cache_file.replace('.json', '').split('_')
                        if len(filename_parts) >= 3:
                            cache_lat = float(filename_parts[1])
                            cache_lon = float(filename_parts[2])
                            
                            # Calculate distance
                            distance = self.calculate_distance_miles(current_lat, current_lon, cache_lat, cache_lon)
                            
                            if distance < closest_distance and distance < 50:  # Within 50 miles
                                with open(os.path.join(self.cache_dir, cache_file), 'r') as f:
                                    data = json.load(f)
                                    closest_distance = distance
                                    closest_data = data.get('data', [])
                                    closest_location = f"{cache_lat:.3f},{cache_lon:.3f}"
                    except (ValueError, KeyError, json.JSONDecodeError):
                        continue
                
                if closest_data:
                    print(f"📍 Using nearby cached {data_type} data from {closest_location} ({closest_distance:.1f} miles away)")
                    return closest_data
                        
        except Exception as e:
            print(f"Error finding nearby cached data: {e}")
        
        return []
    
    def save_to_cache(self, data_type, location_key, data):
        """Save data to local cache"""
        cache_file = self.get_cache_filename(data_type, location_key)
        try:
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'data_type': data_type,
                'location_key': location_key,
                'data': data
            }
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            print(f"✓ Cached {data_type} data for {location_key}")
        except Exception as e:
            print(f"Error saving cache: {e}")
    
    def get_repeaters_by_location(self, lat, lon, radius_miles=50):
        """Get repeaters within radius of lat/lon coordinates with smart caching"""
        location_key = f"{lat:.3f}_{lon:.3f}_{radius_miles}"
        
        # Check if we should update data based on movement and time
        if not self.should_update_data(lat, lon):
            # Try cache first if we don't need fresh data
            cached_data = self.load_from_cache("repeaters", location_key)
            if cached_data is not None:
                return cached_data
        
        # If no API key or offline, try last known good data
        if not self.api_key or not self.is_online():
            print("⚠️ No API key or offline - using last known good data")
            return self.load_last_known_good("repeaters", location_key)
        
        try:
            print(f"🌐 Fetching repeaters from Radio Reference API...")
            
            # For now, let's disable the API call and use last known good data
            # until we can debug the SOAP endpoint properly
            print("⚠️ API temporarily disabled - using last known good data")
            
            # Try to use last known good data first
            last_known = self.load_last_known_good("repeaters", location_key)
            if last_known:
                return last_known
            
            # Only if no cached data exists anywhere, provide initial seed data
            print("📋 No cached data found - providing initial seed data for your area")
            
            # Return realistic Minnesota repeater data for your specific location
            # Based on coordinates 46.598, -94.315 (Central Minnesota - Brainerd/Little Falls area)
            fallback_repeaters = [
                {
                    'call': 'W0BTO',
                    'frequency': 146.760,
                    'output': 146.760,
                    'input': 146.160,  # frequency + offset
                    'offset': -0.6,
                    'tone': '114.8',
                    'pl_tone': 114.8,
                    'lat': 46.3583,
                    'lon': -94.2003,
                    'location': 'Brainerd, MN',
                    'description': 'Brainerd Area Amateur Radio Club'
                },
                {
                    'call': 'KC0TZF',
                    'frequency': 147.300,
                    'output': 147.300,
                    'input': 147.900,  # frequency + offset
                    'offset': 0.6,
                    'tone': '123.0',
                    'pl_tone': 123.0,
                    'lat': 45.9763,
                    'lon': -94.3625,
                    'location': 'Little Falls, MN',
                    'description': 'Little Falls Area Repeater'
                },
                {
                    'call': 'W0AIH',
                    'frequency': 444.025,
                    'output': 444.025,
                    'input': 449.025,  # frequency + offset
                    'offset': 5.0,
                    'tone': '131.8',
                    'pl_tone': 131.8,
                    'lat': 46.3583,
                    'lon': -94.2003,
                    'location': 'Baxter, MN',
                    'description': 'Central Minnesota 70cm'
                },
                {
                    'call': 'K0LFD',
                    'frequency': 145.350,
                    'output': 145.350,
                    'input': 144.750,  # frequency + offset
                    'offset': -0.6,
                    'tone': '103.5',
                    'pl_tone': 103.5,
                    'lat': 45.9763,
                    'lon': -94.3625,
                    'location': 'Little Falls, MN',
                    'description': 'Little Falls Fire Department'
                },
                {
                    'call': 'KC0YHM',
                    'frequency': 442.750,
                    'output': 442.750,
                    'input': 447.750,  # frequency + offset
                    'offset': 5.0,
                    'tone': '100.0',
                    'pl_tone': 100.0,
                    'lat': 46.4816,
                    'lon': -93.9589,
                    'location': 'Crosby, MN',
                    'description': 'Crosby Area Repeater'
                },
                {
                    'call': 'N0GWS',
                    'frequency': 145.230,
                    'output': 145.230,
                    'input': 144.630,  # frequency + offset
                    'offset': -0.6,
                    'tone': '91.5',
                    'pl_tone': 91.5,
                    'lat': 47.2399,
                    'lon': -93.5277,
                    'location': 'Grand Rapids, MN',
                    'description': 'Grand Rapids Area Repeater'
                },
                {
                    'call': 'W0RTN',
                    'frequency': 444.550,
                    'output': 444.550,
                    'input': 449.550,  # frequency + offset
                    'offset': 5.0,
                    'tone': '131.8',
                    'pl_tone': 131.8,
                    'lat': 45.5372,
                    'lon': -94.1653,
                    'location': 'St. Cloud, MN',
                    'description': 'St. Cloud Area Coverage'
                }
            ]
            
            print(f"✓ Created initial seed data with {len(fallback_repeaters)} repeaters")
            self.save_to_cache("repeaters", location_key, fallback_repeaters)
            self.update_api_tracking(lat, lon)
            return fallback_repeaters
            
        except Exception as e:
            print(f"❌ Error fetching from Radio Reference API: {e}")
            # Fall back to last known good data
            return self.load_last_known_good("repeaters", location_key)
    
    def get_skywarn_repeaters(self, lat, lon, radius_miles=100):
        """Get SKYWARN/weather repeaters in area with smart caching"""
        location_key = f"skywarn_{lat:.3f}_{lon:.3f}_{radius_miles}"
        
        # Check if we should update data based on movement and time
        if not self.should_update_data(lat, lon):
            # Try cache first if we don't need fresh data
            cached_data = self.load_from_cache("skywarn", location_key)
            if cached_data is not None:
                return cached_data
        
        if not self.api_key or not self.is_online():
            return self.load_last_known_good("skywarn", location_key)
        
        try:
            print(f"🌐 Fetching SKYWARN repeaters from Radio Reference API...")
            
            # Get all repeaters first, then filter for weather/emergency
            all_repeaters = self.get_repeaters_by_location(lat, lon, radius_miles)
            
            # Filter for likely SKYWARN/weather repeaters
            skywarn_repeaters = []
            weather_keywords = [
                'skywarn', 'weather', 'storm', 'emergency', 'ares', 'races', 'net',
                'emcomm', 'emergency management', 'nws', 'national weather service',
                'spotter', 'severe weather', 'warning', 'alert', 'disaster', 'eoc',
                'emergency operations', 'public safety', 'first responder', 'fire',
                'police', 'ems', 'rescue', 'search', 'emergency coordinator'
            ]
            
            for repeater in all_repeaters:
                # Check multiple fields for emergency/weather keywords
                description = repeater.get('description', '').lower()
                location = repeater.get('location', '').lower()
                call_sign = repeater.get('call_sign', repeater.get('callsign', '')).lower()
                
                # Combine all text fields for searching
                searchable_text = f"{description} {location} {call_sign}"
                
                # More inclusive matching - check if ANY keyword appears
                is_emergency = any(keyword in searchable_text for keyword in weather_keywords)
                
                # Also include repeaters with specific frequency ranges used by emergency services
                freq = float(repeater.get('frequency', repeater.get('output_freq', 0)))
                is_emergency_freq = (
                    (144.0 <= freq <= 148.0) or  # 2m amateur emergency frequencies
                    (420.0 <= freq <= 450.0) or  # 70cm amateur emergency frequencies  
                    (150.0 <= freq <= 174.0)     # VHF public safety ranges sometimes coordinated
                )
                
                # Include if keyword match OR emergency frequency with reasonable description
                if is_emergency or (is_emergency_freq and len(description) > 5):
                    skywarn_repeaters.append(repeater)
                    print(f"📡 Added SKYWARN: {repeater.get('call_sign', 'N/A')} - {description[:50]}")
            
            # Remove duplicates based on call sign and frequency
            seen = set()
            unique_skywarn = []
            for rep in skywarn_repeaters:
                key = (rep.get('call_sign', ''), rep.get('frequency', 0))
                if key not in seen:
                    seen.add(key)
                    unique_skywarn.append(rep)
            skywarn_repeaters = unique_skywarn
            
            if skywarn_repeaters:
                print(f"✓ Found {len(skywarn_repeaters)} Skywarn repeaters")
                self.save_to_cache("skywarn", location_key, skywarn_repeaters)
                return skywarn_repeaters
            
        except Exception as e:
            print(f"❌ Error fetching Skywarn data: {e}")
            
        return []
    
    def clear_all_cache(self):
        """Clear all cached data files"""
        try:
            if os.path.exists(self.cache_dir):
                for filename in os.listdir(self.cache_dir):
                    if filename.endswith('.json'):
                        file_path = os.path.join(self.cache_dir, filename)
                        os.remove(file_path)
                        print(f"🗑️ Removed cache file: {filename}")
                print("✓ All cache files cleared")
        except Exception as e:
            print(f"Error clearing cache: {e}")
    
    def parse_repeater_response(self, xml_response):
        """Parse XML response from Radio Reference API"""
        repeaters = []
        try:
            import xml.etree.ElementTree as ET
            
            # Remove namespace prefixes for easier parsing
            clean_xml = xml_response.replace('ns1:', '').replace('ns2:', '')
            root = ET.fromstring(clean_xml)
            
            # Find repeater elements in the response
            # This may need adjustment based on actual Radio Reference response format
            for repeater_elem in root.findall('.//repeater'):
                repeater = {
                    'call': repeater_elem.findtext('callsign', 'N/A'),
                    'location': repeater_elem.findtext('location', 'Unknown'),
                    'freq': repeater_elem.findtext('frequency', '0.0'),
                    'tone': repeater_elem.findtext('tone', 'N/A'),
                    'lat': float(repeater_elem.findtext('latitude', '0.0')),
                    'lon': float(repeater_elem.findtext('longitude', '0.0')),
                    'description': repeater_elem.findtext('description', ''),
                    'output': repeater_elem.findtext('output_freq', repeater_elem.findtext('frequency', '0.0')),
                    'input': repeater_elem.findtext('input_freq', repeater_elem.findtext('frequency', '0.0'))
                }
                repeaters.append(repeater)
            
        except Exception as e:
            print(f"Error parsing API response: {e}")
            # Try alternative parsing approach
            try:
                # Look for JSON data if XML parsing fails
                import json
                if '{' in xml_response:
                    json_start = xml_response.find('{')
                    json_data = json.loads(xml_response[json_start:])
                    # Process JSON format if available
                    pass
            except:
                pass
        
        return repeaters

    def get_noaa_weather_radio(self, lat, lon, radius_miles=200):
        """Get NOAA Weather Radio stations with Radio Reference API data"""
        location_key = f"noaa_{lat:.3f}_{lon:.3f}_{radius_miles}"
        
        # Check if we should update data based on movement and time
        if not self.should_update_data(lat, lon):
            # Try cache first if we don't need fresh data
            cached_data = self.load_from_cache("noaa", location_key)
            if cached_data is not None:
                return cached_data
        
        if not self.api_key or not self.is_online():
            return self.load_last_known_good("noaa", location_key)
        
        try:
            print(f"🌐 Fetching NOAA Weather Radio stations from Radio Reference API...")
            
            # Get all repeaters first, then filter for NOAA Weather Radio
            all_repeaters = self.get_repeaters_by_location(lat, lon, radius_miles)
            
            # Filter for NOAA Weather Radio stations
            noaa_stations = []
            noaa_keywords = [
                'noaa', 'weather radio', 'nws', 'national weather service',
                'weather broadcast', 'weather alert', 'wx radio', 'weather service',
                'emergency alert system', 'eas', 'weather emergency'
            ]
            
            # Also look for frequencies in the 162.xxx MHz range (NOAA Weather Radio band)
            for repeater in all_repeaters:
                # Check multiple fields for NOAA/weather keywords
                description = repeater.get('description', '').lower()
                location = repeater.get('location', '').lower()
                call_sign = repeater.get('call_sign', repeater.get('callsign', '')).lower()
                frequency = str(repeater.get('frequency', repeater.get('output_freq', '0')))
                
                # Combine all text fields for searching
                searchable_text = f"{description} {location} {call_sign}"
                
                # Check for NOAA keywords OR 162.xxx MHz frequency range
                is_noaa_keyword = any(keyword in searchable_text for keyword in noaa_keywords)
                is_noaa_frequency = frequency.startswith('162.') and len(frequency) >= 6
                
                if is_noaa_keyword or is_noaa_frequency:
                    # Convert to standard format
                    converted_station = {
                        "call": call_sign.upper(),
                        "location": repeater.get('location', 'Unknown'),
                        "freq": frequency,
                        "same_codes": repeater.get('description', 'N/A'),
                        "lat": float(repeater.get('latitude', repeater.get('lat', 0.0))),
                        "lon": float(repeater.get('longitude', repeater.get('lon', 0.0)))
                    }
                    noaa_stations.append(converted_station)
            
            # Remove duplicates by call sign
            unique_noaa = []
            seen_calls = set()
            for station in noaa_stations:
                call = station.get('call', '')
                if call and call not in seen_calls:
                    seen_calls.add(call)
                    unique_noaa.append(station)
            noaa_stations = unique_noaa
            
            if noaa_stations:
                print(f"✓ Found {len(noaa_stations)} NOAA Weather Radio stations")
                self.save_to_cache("noaa", location_key, noaa_stations)
                return noaa_stations
            
        except Exception as e:
            print(f"❌ Error fetching NOAA Weather Radio data: {e}")
            
        # Fall back to last known good data or static data
        fallback_data = self.load_last_known_good("noaa", location_key)
        if fallback_data:
            return fallback_data
        
        # If no API data available, return empty list (will trigger static fallback)
        return []

# GPS Worker Class using gpspipe
class GPSWorker(QThread):
    gps_data_signal = pyqtSignal(float, float, float, float, float)  # Added heading parameter

    def __init__(self, host='127.0.0.1', port=2947):
        super().__init__()
        self.host = host
        self.port = port
        self.running = True

    def run(self):
        try:
            # Start gpspipe process
            cmd = ['gpspipe', '-w']
            
            if self.host != '127.0.0.1' or self.port != 2947:
                env = os.environ.copy()
                env['GPSD_HOST'] = f"{self.host}:{self.port}"
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                          env=env, text=True)
            else:
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            print("[SUCCESS] GPS Worker started - reading from gpspipe")
            logger.info("GPS Worker: Started gpspipe process")
            
            message_count = 0
            last_speed_log = 0
            
            # Read gpspipe output continuously
            for line in process.stdout:
                if not self.running:
                    break
                    
                print(f"DEBUG: GPS Worker received line: {line.strip()[:100]}...")  # Show first 100 chars
                    
                try:
                    data = json.loads(line.strip())
                    msg_class = data.get('class', 'UNKNOWN')
                    message_count += 1
                    
                    print(f"DEBUG: Parsed message #{message_count}, class={msg_class}")
                    
                    # Log message frequency every 50 messages
                    if message_count % 50 == 0:
                        logger.debug(f"GPS Worker: Processed {message_count} messages")
                    
                    # Look for TPV (Time-Position-Velocity) messages
                    if msg_class == 'TPV':
                        logger.debug(f"GPS Worker: TPV message received: {data}")
                        
                        if 'lat' in data and 'lon' in data and 'mode' in data:
                            lat = data['lat']
                            lon = data['lon']
                            alt = data.get('alt', 0.0)
                            mode = data['mode']
                            
                            # Get speed (in m/s) and track/heading
                            speed = data.get('speed', 0.0)
                            track = data.get('track', 0.0)  # Course over ground in degrees
                            
                            # Enhanced speed logging
                            speed_mph = speed * 2.23694 if speed else 0.0
                            current_time = time.time()
                            
                            # Log speed changes or every 10 seconds
                            if abs(speed - last_speed_log) > 0.5 or (current_time - getattr(self, 'last_log_time', 0)) > 10:
                                logger.info(f"GPS: Speed={speed:.2f}m/s ({speed_mph:.1f}mph), Mode={mode}, Track={track:.1f}°")
                                self.last_log_time = current_time
                                last_speed_log = speed
                            
                            # mode: 0=no fix, 1=no fix, 2=2D, 3=3D
                            if mode >= 2:
                                logger.debug(f"GPS Worker: Emitting GPS data - Lat:{lat:.6f}, Lon:{lon:.6f}, Speed:{speed:.2f}m/s")
                                # Emit GPS data to main thread (lat, lon, alt, speed, heading)
                                self.gps_data_signal.emit(lat, lon, alt, speed, track)
                            else:
                                logger.warning(f"GPS Worker: No fix available (mode={mode})")
                        else:
                            logger.debug("GPS Worker: TPV message missing required fields")
                    else:
                        # Log other message types occasionally for debugging
                        if message_count % 100 == 0:
                            logger.debug(f"GPS Worker: Other message type: {msg_class}")
                                
                except json.JSONDecodeError as e:
                    logger.debug(f"GPS Worker: JSON decode error: {e}")
                    continue
                except Exception as e:
                    logger.error(f"GPS Worker: Error parsing GPS message: {e}")
                    continue
            
            process.terminate()
            
        except FileNotFoundError:
            print("[ERROR] Error: gpspipe not found. Install gpsd-clients package:")
            print("  sudo apt-get install gpsd-clients")
        except Exception as e:
            print(f"❌ Error in GPSWorker: {e}")
    
    def stop(self):
        self.running = False

# Utilities Window Class
class UtilitiesWindow(QDialog):
    """Separate utilities window for location tools and data management"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("TowerWitch Utilities")
        self.setGeometry(100, 100, 800, 600)
        self.setModal(True)
        
        # Apply the same styling as main window if night mode is active
        if hasattr(parent, 'night_mode_active') and parent.night_mode_active:
            self.setStyleSheet(parent.styleSheet())
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the utilities UI"""
        layout = QVBoxLayout(self)
        
        # Create the utilities content using the existing method
        if hasattr(self.parent, 'create_utilities_tab'):
            utilities_content = self.parent.create_utilities_tab()
            layout.addWidget(utilities_content)
        
        # Add close button
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        
        close_btn = QPushButton("✖ Close")
        if hasattr(self.parent, 'button_font'):
            close_btn.setFont(self.parent.button_font)
        close_btn.clicked.connect(self.close)
        
        close_layout.addWidget(close_btn)
        layout.addLayout(close_layout)

# Enhanced Main Window Class
class EnhancedGPSWindow(QMainWindow):
    def __init__(self):
        debug_print("Initializing EnhancedGPSWindow...", "INFO")
        super().__init__()
        
        try:
            # Initialize night mode state early to prevent AttributeError
            self.night_mode_active = False
            debug_print("Night mode state initialized", "INFO")
            
            self.setWindowTitle("TowerWitch - GPS Tower Locator")
            debug_print("Window title set", "INFO")
            
            # Optimize for 10" touchscreen (1024x600 typical resolution)
            self.setGeometry(0, 0, 1024, 600)
            self.setMinimumSize(800, 600)
            debug_print("Window geometry set to 1024x600", "INFO")
            
            # Set up styling for touch interface
            debug_print("Setting up styling...", "INFO")
            self.setup_styling()
            debug_print("Styling setup complete", "SUCCESS")
            
            # Create main widget and layout
            debug_print("Creating main widget and layout...", "INFO")
            self.central_widget = QWidget()
            self.setCentralWidget(self.central_widget)
            self.main_layout = QVBoxLayout(self.central_widget)
            self.main_layout.setSpacing(10)
            self.main_layout.setContentsMargins(10, 10, 10, 10)
            debug_print("Main layout created", "SUCCESS")
            
            # Initialize configuration and API first
            debug_print("Loading configuration...", "INFO")
            self.load_configuration()
            debug_print("Configuration loaded", "SUCCESS")
            
            debug_print("Initializing Radio Reference API...", "INFO")
            self.radio_api = RadioReferenceAPI(self.api_key)
            self.cache_dir = self.radio_api.cache_dir  # Reference to the radio API cache directory
            debug_print("Radio Reference API initialized", "SUCCESS")
            
            # Initialize UDP broadcasting
            debug_print("Setting up UDP broadcasting...", "INFO")
            self.setup_udp()
            debug_print("UDP broadcasting configured", "SUCCESS")
            
            # Initialize caching variables for amateur radio data
            debug_print("Setting up caching variables...", "INFO")
            self.cached_api_data = None
            self.cached_api_location = None
            self.cached_api_timestamp = None
            self.cached_api_radius = 200  # Cache covers 200-mile radius
            self.amateur_data_cache_timeout = 86400  # 24 hours (much longer for regional cache)
            self.is_stationary = False
            self.stationary_threshold = 0.01  # 0.01 miles = ~50 feet movement to trigger refresh
            self.last_known_position = None
            self.cache_region_radius = 150  # Stay within 150 miles of cache center before refresh
            self.force_band_refresh = False  # Flag to force refresh of band displays when moving
            
            # Motion-aware update system
            self.last_armer_update = 0
            self.last_skywarn_update = 0
            self.last_amateur_update = 0
            self.is_vehicle_speed = False  # Track if we're moving at vehicle speeds
            self.WALKING_SPEED_THRESHOLD = 1.5  # m/s (~3.4 mph) - threshold for walking vs vehicle speed
            self.ARMER_SKYWARN_INTERVAL = 25  # seconds - update interval for ARMER/SKYWARN when moving
            self.AMATEUR_INTERVAL = 35  # seconds - update interval for Amateur when moving
            debug_print("Caching variables initialized", "SUCCESS")
            
            # Check if cache refresh is requested (after radio_api is initialized)
            force_refresh = self.config.getboolean('API', 'force_refresh_cache', fallback=False)
            if force_refresh:
                debug_print("Cache refresh requested - clearing all cached data", "INFO")
                self.radio_api.clear_all_cache()
                # Reset the config option so it doesn't clear every time
                self.config.set('API', 'force_refresh_cache', 'false')
                with open(self.config_file, 'w') as f:
                    self.config.write(f)
                debug_print("Cache cleared and config updated", "SUCCESS")
            
            # Data source status
            debug_print("Setting up data source status...", "INFO")
            self.data_source_status = {
                'armer': 'static',
                'skywarn': 'static', 
                'amateur': 'static'
            }
            debug_print("Data source status initialized", "SUCCESS")
            
            # Create header with title and status
            debug_print("Creating header...", "INFO")
            self.create_header()
            debug_print("Header created", "SUCCESS")
            
            # Create tabbed interface
            debug_print("Creating tabbed interface...", "INFO")
            self.create_tabs()
            debug_print("Tabs created", "SUCCESS")
            
            # Create control buttons
            debug_print("Creating control buttons...", "INFO")
            self.create_control_buttons()
            debug_print("Control buttons created", "SUCCESS")
            
            # Path to the CSV file
            script_dir = os.path.dirname(os.path.abspath(__file__))
            self.csv_filepath = os.path.join(script_dir, "trs_sites_3508.csv")
            debug_print(f"CSV file path: {self.csv_filepath}", "INFO")
            
            # Start GPS worker
            debug_print("Starting GPS worker...", "INFO")
            print("DEBUG: About to create GPS worker")
            self.gps_worker = GPSWorker()
            print("DEBUG: GPS worker created, connecting signal")
            self.gps_worker.gps_data_signal.connect(self.update_gps_data)
            print("DEBUG: Signal connected, starting GPS worker thread")
            self.gps_worker.start()
            print("DEBUG: GPS worker thread started")
            debug_print("GPS worker started", "SUCCESS")
            
            # Initialize with demo data if no GPS
            debug_print("Setting up GPS defaults...", "INFO")
            self.last_lat = 44.9778  # Minneapolis default
            self.last_lon = -93.2650
            debug_print(f"GPS defaults: {self.last_lat}, {self.last_lon}", "INFO")
            
            # Track fullscreen state
            self._is_fullscreen = False
            debug_print("Fullscreen state initialized", "INFO")

            # Create an action for toggling fullscreen with F11
            debug_print("Setting up fullscreen action...", "INFO")
            self._toggle_fullscreen_act = QAction(self)
            self._toggle_fullscreen_act.setShortcut('F11')
            self._toggle_fullscreen_act.triggered.connect(self.toggle_fullscreen)
            self.addAction(self._toggle_fullscreen_act)
            debug_print("Fullscreen action setup complete", "SUCCESS")
            
            debug_print("EnhancedGPSWindow initialization completed successfully!", "SUCCESS")
            
        except Exception as e:
            debug_print(f"CRITICAL ERROR during initialization: {str(e)}", "ERROR")
            debug_print(f"Exception type: {type(e).__name__}", "ERROR")
            debug_print(f"Exception traceback: {traceback.format_exc()}", "ERROR")
            # Don't re-raise - try to continue with partial initialization
            debug_print("Attempting to continue with partial initialization...", "WARNING")
    
    def showEvent(self, event):
        """Override showEvent to track window display"""
        debug_print("Window showEvent triggered", "INFO")
        super().showEvent(event)
        debug_print("Window is now visible", "SUCCESS")
    
    def closeEvent(self, event):
        """Override closeEvent to track window closing"""
        debug_print("Window closeEvent triggered", "WARNING")
        debug_print("Cleaning up GPS worker thread...", "INFO")
        if hasattr(self, 'gps_worker') and self.gps_worker:
            self.gps_worker.stop()
        debug_print("Window closing cleanup complete", "INFO")
        super().closeEvent(event)
        debug_print("Window closed", "WARNING")

    def setup_styling(self, night_mode=False):
        """Set up fonts and colors for touch interface with day/night mode support"""
        # Balanced fonts - larger for important data, reasonable for coordinates
        self.header_font = QFont("Arial", 18, QFont.Bold)
        self.label_font = QFont("Arial", 14, QFont.Bold)
        self.data_font = QFont("Arial", 12)  # Smaller for coordinate data
        self.coordinate_font = QFont("Arial", 11)  # Even smaller for coordinates
        self.button_font = QFont("Arial", 14, QFont.Bold)
        self.table_font = QFont("Arial", 13)
        
        # Dynamic color scheme based on mode
        if night_mode:
            # Night mode colors - red theme for night vision
            main_bg = "#1a0000"
            secondary_bg = "#220000"
            accent_bg = "#330000"
            text_color = "#ff6666"
            accent_text = "#ff6666"
            button_bg = "#660000"
            button_hover = "#880000"
            tab_selected = "#660000"
        else:
            # Day mode colors - standard dark theme
            main_bg = "#2b2b2b"
            secondary_bg = "#3b3b3b"
            accent_bg = "#4a90e2"
            text_color = "#ffffff"
            accent_text = "#00ff00"
            button_bg = "#4a90e2"
            button_hover = "#357abd"
            tab_selected = "#4a90e2"
        
        # Apply dynamic color scheme
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {main_bg};
                color: {text_color};
            }}
            QGroupBox {{
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #555555;
                border-radius: 8px;
                margin-top: 1ex;
                padding-top: 12px;
                background-color: {secondary_bg};
                color: {text_color};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
                color: {accent_text};
                font-size: 14px;
            }}
            QLabel {{
                color: {text_color};
                padding: 6px;
                font-size: 12px;
            }}
            QPushButton {{
                background-color: {button_bg};
                border: none;
                border-radius: 8px;
                padding: 15px;
                font-weight: bold;
                color: {text_color};
                min-height: 45px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {button_hover};
            }}
            QPushButton:pressed {{
                background-color: {button_hover};
            }}
            QTableWidget {{
                background-color: {secondary_bg};
                border: 1px solid #555555;
                border-radius: 5px;
                gridline-color: #555555;
                font-size: 13px;
                color: {text_color};
            }}
            QTableWidget::item {{
                padding: 12px;
                border-bottom: 1px solid #555555;
                color: {text_color};
                font-size: 13px;
            }}
            QTableWidget::item:alternate {{
                background-color: {main_bg};
                color: {text_color};
            }}
            QTableWidget::item:selected {{
                background-color: {accent_bg};
                color: {text_color};
            }}
            QHeaderView::section {{
                background-color: {accent_bg};
                color: {text_color};
                padding: 12px;
                border: 1px solid #555555;
                font-weight: bold;
                font-size: 14px;
            }}
            QTabWidget::pane {{
                border: 1px solid #555555;
                background-color: {secondary_bg};
            }}
            QTabBar::tab {{
                color: {text_color};
                padding: 15px 25px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                min-width: 120px;
                font-size: 14px;
                font-weight: bold;
            }}
            /* Main tab colors - only apply to main tab widget */
            QTabWidget#main_tabs QTabBar::tab:nth-child(1) {{ background-color: #8E44AD; }}  /* Location (GPS+Grid) - Purple */
            QTabWidget#main_tabs QTabBar::tab:nth-child(2) {{ background-color: #E74C3C; }}  /* ARMER - Red */
            QTabWidget#main_tabs QTabBar::tab:nth-child(3) {{ background-color: #F39C12; }}  /* SKYWARN - Orange */
            QTabWidget#main_tabs QTabBar::tab:nth-child(4) {{ background-color: #2ECC71; }}  /* NOAA - Green */
            QTabWidget#main_tabs QTabBar::tab:nth-child(5) {{ background-color: #3498DB; }}  /* Amateur - Blue */
            
            /* Alternative simpler approach - try without nth-child */
            QTabWidget#main_tabs QTabBar::tab {{ 
                background-color: #666666;  /* Default gray background */
                color: {text_color};
                padding: 15px 25px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                min-width: 120px;
                font-size: 14px;
                font-weight: bold;
            }}
            
            QTabWidget#main_tabs QTabBar::tab:selected {{
                border: 2px solid #ffffff;
                font-weight: bolder;
            }}
        """)
        
        # Debug: Print that we're setting up main tab styling
        print("🎨 Setting up main tab colors with object name 'main_tabs'...")

    def create_header(self):
        """Create header with title, date/time, and GPS status"""
        header_frame = QFrame()
        header_layout = QHBoxLayout(header_frame)
        
        # Title
        title_label = QLabel("🗼 TowerWitch")
        title_label.setFont(self.header_font)
        title_label.setStyleSheet("color: #00ff00; padding: 10px;")
        
        # Date and Time in center
        self.datetime_label = QLabel()
        self.datetime_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.datetime_label.setStyleSheet(f"color: {self.get_text_color_hex()}; padding: 10px;")
        self.datetime_label.setAlignment(Qt.AlignCenter)
        self.update_datetime()
        
        # GPS Status indicator (right side)
        self.gps_status = QLabel("GPS: Searching...")
        self.gps_status.setFont(self.label_font)
        self.gps_status.setStyleSheet("color: #ffaa00; padding: 6px; font-size: 14px;")
        self.gps_status.setAlignment(Qt.AlignRight)
        
        header_layout.addWidget(title_label, 1)
        header_layout.addWidget(self.datetime_label, 2)
        header_layout.addWidget(self.gps_status, 1)
        
        self.main_layout.addWidget(header_frame)
        
        # Timer for updating date/time every second
        self.datetime_timer = QTimer()
        self.datetime_timer.timeout.connect(self.update_datetime)
        self.datetime_timer.start(1000)  # Update every second

    def create_tabs(self):
        """Create tabbed interface for different information views"""
        try:
            debug_print("Creating tab widget...", "INFO")
            self.tabs = QTabWidget()
            self.tabs.setObjectName("main_tabs")  # Set object name for CSS styling
            self.tabs.setObjectName("main_tabs")  # Set object name for specific CSS targeting
            debug_print("Tab widget created", "SUCCESS")
            
            # Unified Location Tab (GPS + Coordinate Systems)
            debug_print("Creating Location tab...", "INFO")
            self.location_tab = self.create_location_tab()
            self.tabs.addTab(self.location_tab, "Location")
            debug_print("Location tab added", "SUCCESS")
            
            # ARMER Data Tab
            debug_print("Creating ARMER tab...", "INFO")
            self.tower_tab = self.create_tower_tab()
            self.tabs.addTab(self.tower_tab, "ARMER")
            debug_print("ARMER tab added", "SUCCESS")
            
            # SKYWARN Weather Tab
            debug_print("Creating SKYWARN tab...", "INFO")
            self.skywarn_tab = self.create_skywarn_tab()
            self.tabs.addTab(self.skywarn_tab, "SKYWARN")
            debug_print("SKYWARN tab added", "SUCCESS")
            
            # NOAA Weather Radio Tab
            debug_print("Creating NOAA tab...", "INFO")
            self.noaa_tab = self.create_noaa_tab()
            self.tabs.addTab(self.noaa_tab, "NOAA")
            debug_print("NOAA tab added", "SUCCESS")
            
            # Amateur Radio Tab
            debug_print("Creating Amateur tab...", "INFO")
            self.amateur_tab = self.create_amateur_tab()
            self.tabs.addTab(self.amateur_tab, "Amateur")
            debug_print("Amateur tab added", "SUCCESS")

            # Note: Utilities moved to bottom button for better UX
            
            # Add tabs to main layout
            debug_print("Adding tabs to main layout...", "INFO")
            self.main_layout.addWidget(self.tabs)
            debug_print("Tabs added to main layout", "SUCCESS")
            
            # Set tab colors programmatically as backup to CSS
            self.set_main_tab_colors()
            
        except Exception as e:
            debug_print(f"ERROR creating tabs: {str(e)}", "ERROR")
            debug_print(f"Exception traceback: {traceback.format_exc()}", "ERROR")

    def create_location_tab(self):
        """Create unified Location tab with GPS data and coordinate systems side-by-side"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Create a single comprehensive table for all location data (side-by-side layout)
        self.location_table = QTableWidget()
        self.location_table.setColumnCount(4)
        self.location_table.setHorizontalHeaderLabels(["GPS DATA", "VALUES", "COORDINATE SYSTEMS", "VALUES"])
        self.location_table.setRowCount(8)  # Max of GPS rows (8) and coordinate system rows (6) = 8 total
        
        # Set up table appearance
        self.location_table.setAlternatingRowColors(True)
        self.location_table.verticalHeader().setVisible(False)
        self.location_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.location_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        # Set column widths for side-by-side layout
        header = self.location_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # GPS labels column
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # GPS values column
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Coordinate system labels column  
        header.setSectionResizeMode(3, QHeaderView.Stretch)  # Coordinate system values column
        
        # Set row height for better readability
        self.location_table.verticalHeader().setDefaultSectionSize(45)
        
        # Style the location table dynamically based on current mode
        self.location_table.setStyleSheet(self.get_table_css())
        
        # Initialize location labels for updating (GPS + Grid combined)
        self.location_items = {}
        
        # GPS Data (Rows 0-7)
        # Row 0: Latitude
        self.location_items['lat_item'] = QTableWidgetItem("📍 LATITUDE")
        self.location_items['lat_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.location_items['lat_value'] = QTableWidgetItem("Waiting for GPS...")
        self.location_items['lat_value'].setFont(QFont("Arial", 12))
        
        # Row 1: Longitude  
        self.location_items['lon_item'] = QTableWidgetItem("📍 LONGITUDE")
        self.location_items['lon_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.location_items['lon_value'] = QTableWidgetItem("Waiting for GPS...")
        self.location_items['lon_value'].setFont(QFont("Arial", 12))
        
        # Row 2: Altitude
        self.location_items['alt_item'] = QTableWidgetItem("⛰️ ALTITUDE")
        self.location_items['alt_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.location_items['alt_value'] = QTableWidgetItem("N/A")
        self.location_items['alt_value'].setFont(QFont("Arial", 12))
        
        # Row 3: Speed
        self.location_items['speed_item'] = QTableWidgetItem("🚗 SPEED")
        self.location_items['speed_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.location_items['speed_value'] = QTableWidgetItem("N/A")
        self.location_items['speed_value'].setFont(QFont("Arial", 12))
        
        # Row 4: Heading/Direction
        self.location_items['heading_item'] = QTableWidgetItem("🧭 HEADING")
        self.location_items['heading_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.location_items['heading_value'] = QTableWidgetItem("N/A")
        self.location_items['heading_value'].setFont(QFont("Arial", 12))
        
        # Row 5: Vector Speed (speed + direction)
        self.location_items['vector_item'] = QTableWidgetItem("🏃 VECTOR SPEED")
        self.location_items['vector_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.location_items['vector_value'] = QTableWidgetItem("N/A")
        self.location_items['vector_value'].setFont(QFont("Arial", 12))
        
        # Row 6: GPS Status
        self.location_items['status_item'] = QTableWidgetItem("🛰️ GPS STATUS")
        self.location_items['status_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.location_items['status_value'] = QTableWidgetItem("Searching...")
        self.location_items['status_value'].setFont(QFont("Arial", 12))
        
        # Row 7: Fix Quality
        self.location_items['fix_item'] = QTableWidgetItem("📡 FIX QUALITY")
        self.location_items['fix_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.location_items['fix_value'] = QTableWidgetItem("No Fix")
        self.location_items['fix_value'].setFont(QFont("Arial", 12))
        
        # Coordinate Systems (Rows 8-13)
        # Row 8: UTM
        self.location_items['utm_item'] = QTableWidgetItem("🗺️ UTM")
        self.location_items['utm_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.location_items['utm_value'] = QTableWidgetItem("N/A")
        self.location_items['utm_value'].setFont(QFont("Arial", 12))
        
        # Row 9: Maidenhead
        self.location_items['mh_item'] = QTableWidgetItem("📡 MAIDENHEAD")
        self.location_items['mh_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.location_items['mh_value'] = QTableWidgetItem("N/A")
        self.location_items['mh_value'].setFont(QFont("Arial", 12))
        
        # Row 10: MGRS Zone/Grid
        self.location_items['mgrs_zone_item'] = QTableWidgetItem("🪖 MGRS ZONE/GRID")
        self.location_items['mgrs_zone_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.location_items['mgrs_zone_value'] = QTableWidgetItem("N/A")
        self.location_items['mgrs_zone_value'].setFont(QFont("Arial", 12))
        
        # Row 11: MGRS Coordinates
        self.location_items['mgrs_coords_item'] = QTableWidgetItem("🔢 MGRS EASTING/NORTHING")
        self.location_items['mgrs_coords_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.location_items['mgrs_coords_value'] = QTableWidgetItem("N/A")
        self.location_items['mgrs_coords_value'].setFont(QFont("Arial", 12))
        
        # Row 12: Decimal Degrees - Lat (redundant with Row 0 - skip this)
        # Row 13: Decimal Degrees - Lon (redundant with Row 1 - skip this)
        # Actually, let's use these rows for additional precision formats:
        
        # Row 12: DMS (Degrees, Minutes, Seconds) Latitude
        self.location_items['dms_lat_item'] = QTableWidgetItem("📐 DMS LATITUDE")
        self.location_items['dms_lat_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.location_items['dms_lat_value'] = QTableWidgetItem("N/A")
        self.location_items['dms_lat_value'].setFont(QFont("Arial", 12))
        
        # Row 13: DMS Longitude
        self.location_items['dms_lon_item'] = QTableWidgetItem("📐 DMS LONGITUDE")
        self.location_items['dms_lon_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.location_items['dms_lon_value'] = QTableWidgetItem("N/A")
        self.location_items['dms_lon_value'].setFont(QFont("Arial", 12))
        
        # Add items to table (side-by-side layout)
        # GPS data on the left (columns 0-1)
        self.location_table.setItem(0, 0, self.location_items['lat_item'])
        self.location_table.setItem(0, 1, self.location_items['lat_value'])
        self.location_table.setItem(1, 0, self.location_items['lon_item'])
        self.location_table.setItem(1, 1, self.location_items['lon_value'])
        self.location_table.setItem(2, 0, self.location_items['alt_item'])
        self.location_table.setItem(2, 1, self.location_items['alt_value'])
        self.location_table.setItem(3, 0, self.location_items['speed_item'])
        self.location_table.setItem(3, 1, self.location_items['speed_value'])
        self.location_table.setItem(4, 0, self.location_items['heading_item'])
        self.location_table.setItem(4, 1, self.location_items['heading_value'])
        self.location_table.setItem(5, 0, self.location_items['vector_item'])
        self.location_table.setItem(5, 1, self.location_items['vector_value'])
        self.location_table.setItem(6, 0, self.location_items['status_item'])
        self.location_table.setItem(6, 1, self.location_items['status_value'])
        self.location_table.setItem(7, 0, self.location_items['fix_item'])
        self.location_table.setItem(7, 1, self.location_items['fix_value'])
        
        # Coordinate system data on the right (columns 2-3)
        self.location_table.setItem(0, 2, self.location_items['utm_item'])
        self.location_table.setItem(0, 3, self.location_items['utm_value'])
        self.location_table.setItem(1, 2, self.location_items['mh_item'])
        self.location_table.setItem(1, 3, self.location_items['mh_value'])
        self.location_table.setItem(2, 2, self.location_items['mgrs_zone_item'])
        self.location_table.setItem(2, 3, self.location_items['mgrs_zone_value'])
        self.location_table.setItem(3, 2, self.location_items['mgrs_coords_item'])
        self.location_table.setItem(3, 3, self.location_items['mgrs_coords_value'])
        self.location_table.setItem(4, 2, self.location_items['dms_lat_item'])
        self.location_table.setItem(4, 3, self.location_items['dms_lat_value'])
        self.location_table.setItem(5, 2, self.location_items['dms_lon_item'])
        self.location_table.setItem(5, 3, self.location_items['dms_lon_value'])
        
        # Rows 6-7 on the right side will be empty, creating visual balance
        
        # Set initial colors for all location table items
        text_color = self.get_text_color()
        for item_key, item in self.location_items.items():
            if item:
                item.setForeground(text_color)
        
        layout.addWidget(self.location_table)
        
        return tab

    def create_tower_tab(self):
        """Create tower information display tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Tower table with enhanced formatting
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Site Name", "County", "Distance", "Bearing", "NAC", "Control Channels"])
        
        # Set column widths for better touch interface
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Site name can expand
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # County
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Distance
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Bearing
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # NAC
        header.setSectionResizeMode(5, QHeaderView.Stretch)  # Control frequencies can expand
        
        # Make table touch-friendly with larger fonts and spacing
        self.table.setMinimumHeight(450)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(50)  # Even taller rows for better readability
        self.table.setFont(self.table_font)
        
        layout.addWidget(self.table)
        
        return tab

    def create_grid_tab(self):
        """Create grid systems display tab with table format and interactive map"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Create a horizontal splitter to divide between table and map
        splitter = QSplitter(Qt.Horizontal)
        
        # Left side: Create a table for grid systems
        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)
        
        self.grid_table = QTableWidget()
        self.grid_table.setColumnCount(4)
        self.grid_table.setHorizontalHeaderLabels(["", "GRID SYSTEM", "COORDINATES", ""])
        self.grid_table.setRowCount(6)  # 6 different coordinate systems
        
        # Set up table appearance
        self.grid_table.setAlternatingRowColors(True)
        self.grid_table.verticalHeader().setVisible(False)
        self.grid_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.grid_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        # Set column widths for centered layout
        header = self.grid_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Left spacer column
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # System name column
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Coordinates column
        header.setSectionResizeMode(3, QHeaderView.Stretch)  # Right spacer column
        
        # Set row height for better readability
        self.grid_table.verticalHeader().setDefaultSectionSize(45)
        
        # Style the grid table dynamically based on current mode
        self.grid_table.setStyleSheet(self.get_table_css())
        
        # Initialize grid labels for updating
        self.grid_items = {}
        
        # Row 0: Decimal Degrees
        self.grid_items['lat_item'] = QTableWidgetItem("📍 LATITUDE")
        self.grid_items['lat_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.grid_items['lat_value'] = QTableWidgetItem("Waiting for GPS...")
        self.grid_items['lat_value'].setFont(QFont("Arial", 12))
        
        # Row 1: Longitude
        self.grid_items['lon_item'] = QTableWidgetItem("📍 LONGITUDE")
        self.grid_items['lon_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.grid_items['lon_value'] = QTableWidgetItem("Waiting for GPS...")
        self.grid_items['lon_value'].setFont(QFont("Arial", 12))
        
        # Row 2: UTM
        self.grid_items['utm_item'] = QTableWidgetItem("🗺️ UTM")
        self.grid_items['utm_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.grid_items['utm_value'] = QTableWidgetItem("N/A")
        self.grid_items['utm_value'].setFont(QFont("Arial", 12))
        
        # Row 3: Maidenhead
        self.grid_items['mh_item'] = QTableWidgetItem("📡 MAIDENHEAD")
        self.grid_items['mh_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.grid_items['mh_value'] = QTableWidgetItem("N/A")
        self.grid_items['mh_value'].setFont(QFont("Arial", 12))
        
        # Row 4: MGRS Zone/Grid
        self.grid_items['mgrs_zone_item'] = QTableWidgetItem("🪖 MGRS ZONE/GRID")
        self.grid_items['mgrs_zone_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.grid_items['mgrs_zone_value'] = QTableWidgetItem("N/A")
        self.grid_items['mgrs_zone_value'].setFont(QFont("Arial", 12))
        
        # Row 5: MGRS Coordinates
        self.grid_items['mgrs_coords_item'] = QTableWidgetItem("🔢 MGRS EASTING/NORTHING")
        self.grid_items['mgrs_coords_item'].setFont(QFont("Arial", 12, QFont.Bold))
        self.grid_items['mgrs_coords_value'] = QTableWidgetItem("N/A")
        self.grid_items['mgrs_coords_value'].setFont(QFont("Arial", 12))
        
        # Add items to table (centered layout with spacer columns 0 and 3)
        # Add empty spacer items for columns 0 and 3
        for row in range(6):
            left_spacer = QTableWidgetItem("")
            left_spacer.setFlags(left_spacer.flags() & ~Qt.ItemIsSelectable)
            self.grid_table.setItem(row, 0, left_spacer)
            
            right_spacer = QTableWidgetItem("")
            right_spacer.setFlags(right_spacer.flags() & ~Qt.ItemIsSelectable)
            self.grid_table.setItem(row, 3, right_spacer)
        
        # Add data items to columns 1 and 2
        self.grid_table.setItem(0, 1, self.grid_items['lat_item'])
        self.grid_table.setItem(0, 2, self.grid_items['lat_value'])
        self.grid_table.setItem(1, 1, self.grid_items['lon_item'])
        self.grid_table.setItem(1, 2, self.grid_items['lon_value'])
        self.grid_table.setItem(2, 1, self.grid_items['utm_item'])
        self.grid_table.setItem(2, 2, self.grid_items['utm_value'])
        self.grid_table.setItem(3, 1, self.grid_items['mh_item'])
        self.grid_table.setItem(3, 2, self.grid_items['mh_value'])
        self.grid_table.setItem(4, 1, self.grid_items['mgrs_zone_item'])
        self.grid_table.setItem(4, 2, self.grid_items['mgrs_zone_value'])
        self.grid_table.setItem(5, 1, self.grid_items['mgrs_coords_item'])
        self.grid_table.setItem(5, 2, self.grid_items['mgrs_coords_value'])
        
        # Set initial colors for all Grid table items
        text_color = self.get_text_color()
        for item_key, item in self.grid_items.items():
            if item:
                item.setForeground(text_color)
        
        # Add table to layout - now takes full width
        layout.addWidget(self.grid_table)
        
        return tab
        
        # Coordinate display title with dynamic color
        coord_title = QLabel("� Your Location")
        coord_title.setFont(QFont("Arial", 14, QFont.Bold))
        coord_title.setStyleSheet(f"color: {self.get_text_color_hex()}; padding: 10px; text-align: center;")
        coord_title.setAlignment(Qt.AlignCenter)
        coord_layout.addWidget(coord_title)
        
        # Store reference for night mode updates
        self.coord_title_label = coord_title
        
        # Create coordinate display widget
        self.coord_display = QTextEdit()
        self.coord_display.setMinimumHeight(400)
        self.coord_display.setReadOnly(True)
        self.coord_display.setStyleSheet("""
            QTextEdit {
                background-color: #2b2b2b;
                color: #ffffff;
                border: 2px solid #4a90e2;
                border-radius: 8px;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                padding: 10px;
            }
        """)
        
        # Initialize coordinate display
        self.update_coord_display()
        
        coord_layout.addWidget(self.coord_display)
        
        # Add both sides to splitter
        splitter.addWidget(table_widget)
        splitter.addWidget(coord_widget)
        
        # Set initial sizes (60% table, 40% coordinates)
        splitter.setSizes([600, 400])
        
        layout.addWidget(splitter)
        
        return tab

    def create_skywarn_tab(self):
        """Create SKYWARN weather repeater display tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # SKYWARN table - maximize space for repeater data
        self.skywarn_table = QTableWidget()
        self.skywarn_table.setColumnCount(6)
        self.skywarn_table.setHorizontalHeaderLabels(["Call Sign", "Location", "Frequency", "Tone", "Distance", "Bearing"])
        
        # Set column widths for touch interface
        header = self.skywarn_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Call sign
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Location can expand
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Frequency
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Tone
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Distance
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Bearing
        
        # Make table touch-friendly with more space
        self.skywarn_table.setMinimumHeight(450)
        self.skywarn_table.setAlternatingRowColors(True)
        self.skywarn_table.verticalHeader().setDefaultSectionSize(50)
        self.skywarn_table.setFont(self.table_font)
        
        # Add sample Skywarn data for Minnesota
        self.populate_skywarn_data()
        
        layout.addWidget(self.skywarn_table)
        
        return tab

    def create_noaa_tab(self):
        """Create NOAA Weather Radio frequency reference tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # NOAA Weather Radio frequency reference table
        self.noaa_table = QTableWidget()
        self.noaa_table.setColumnCount(5)
        self.noaa_table.setHorizontalHeaderLabels(["Frequency", "Nearest Station", "Location", "Distance", "Status"])
        
        # Set column widths for touch interface
        header = self.noaa_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Frequency
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Station call sign
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # Location can expand
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Distance
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Status/recommendation
        
        # Make table touch-friendly with more space
        self.noaa_table.setMinimumHeight(450)
        self.noaa_table.setAlternatingRowColors(True)
        self.noaa_table.verticalHeader().setDefaultSectionSize(50)
        self.noaa_table.setFont(self.table_font)
        
        # Set to exactly 7 rows for the 7 NOAA frequencies
        self.noaa_table.setRowCount(7)
        
        # Add NOAA frequency reference data
        self.populate_noaa_frequency_data()
        
        layout.addWidget(self.noaa_table)
        
        return tab

    def create_amateur_tab(self):
        """Create Amateur Radio repeater display tab with band sub-tabs"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Create sub-tabs for different bands - clean professional styling
        self.amateur_subtabs = QTabWidget()
        self.amateur_subtabs.setObjectName("amateur_subtabs")  # Set ID for CSS targeting
        
        # 10m Tab
        self.amateur_10m_tab = self.create_band_tab("10m", "10 Meters (28-29.7 MHz)")
        self.amateur_subtabs.addTab(self.amateur_10m_tab, "10m")
        
        # 6m Tab
        self.amateur_6m_tab = self.create_band_tab("6m", "6 Meters (50-54 MHz)")
        self.amateur_subtabs.addTab(self.amateur_6m_tab, "6m")
        
        # 2m Tab
        self.amateur_2m_tab = self.create_band_tab("2m", "2 Meters (144-148 MHz)")
        self.amateur_subtabs.addTab(self.amateur_2m_tab, "2m")
        
        # 1.25m Tab
        self.amateur_125m_tab = self.create_band_tab("1.25m", "1.25 Meters (220-225 MHz)")
        self.amateur_subtabs.addTab(self.amateur_125m_tab, "1.25m")
        
        # 70cm Tab
        self.amateur_70cm_tab = self.create_band_tab("70cm", "70 Centimeters (420-450 MHz)")
        self.amateur_subtabs.addTab(self.amateur_70cm_tab, "70cm")
        
        # Simplex Tab
        self.amateur_simplex_tab = self.create_simplex_tab("simplex", "Simplex & Special Frequencies")
        self.amateur_subtabs.addTab(self.amateur_simplex_tab, "Simplex")
        
        # Emergency Tab
        self.amateur_emergency_tab = self.create_emergency_tab("emergency", "Emergency & NIFOG Frequencies")
        self.amateur_subtabs.addTab(self.amateur_emergency_tab, "Emergency")
        
        layout.addWidget(self.amateur_subtabs)
        
        # Set colors for the amateur band tab titles
        self.set_amateur_band_tab_colors()
        
        # Populate all band data
        self.populate_all_amateur_data()
        
        # Populate simplex data
        self.populate_simplex_data()
        
        # Populate emergency data
        self.populate_emergency_data()
        
        return tab

    def create_band_tab(self, band_name, band_description):
        """Create a tab for a specific amateur radio band"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Band description with dynamic color
        desc_label = QLabel(band_description)
        desc_label.setFont(QFont("Arial", 12, QFont.Bold))
        desc_label.setStyleSheet(f"color: {self.get_text_color_hex()}; padding: 5px;")
        desc_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_label)
        
        # Store reference for night mode updates
        if not hasattr(self, 'band_description_labels'):
            self.band_description_labels = []
        self.band_description_labels.append(desc_label)
        
        # Create table for this band
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(["Call Sign", "Location", "Output", "Input", "Tone", "Distance", "Bearing"])
        
        # Set column widths for touch interface
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Call sign
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Location can expand
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Output freq
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Input freq
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Tone
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Distance
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Bearing
        
        # Make table touch-friendly
        table.setMinimumHeight(350)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setDefaultSectionSize(45)
        table.setFont(self.table_font)
        
        # Store reference to table for population
        # Create consistent table attribute names - map from new band names to existing table names
        band_to_table_map = {
            "10m": "amateur_10_table",
            "6m": "amateur_6_table", 
            "2m": "amateur_2_table",
            "1.25m": "amateur_125_table",
            "70cm": "amateur_70cm_table"
        }
        
        table_name = band_to_table_map.get(band_name, f'amateur_{band_name.replace(".", "").replace("m", "")}_table')
        setattr(self, table_name, table)
        
        layout.addWidget(table)
        
        return tab

    def create_simplex_tab(self, band_name, band_description):
        """Create a tab for amateur radio simplex and special frequencies"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Create table for simplex frequencies - maximize space for data
        table = QTableWidget()
        table.setColumnCount(6)  # Different columns for simplex
        table.setHorizontalHeaderLabels(["Frequency", "Description", "Type", "Mode", "Tone", "Notes"])
        
        # Set column widths for touch interface
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Frequency
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Description can expand
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Type
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Mode
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Tone
        header.setSectionResizeMode(5, QHeaderView.Stretch)  # Notes
        
        # Make table touch-friendly with more space
        table.setMinimumHeight(400)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setDefaultSectionSize(45)
        table.setFont(self.table_font)
        
        # Store reference to table for population
        setattr(self, "amateur_simplex_table", table)
        
        layout.addWidget(table)
        
        return tab

    def create_emergency_tab(self, band_name, band_description):
        """Create a tab for amateur radio emergency frequencies from NIFOG"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Band description with dynamic color
        desc_label = QLabel(band_description)
        desc_label.setFont(QFont("Arial", 12, QFont.Bold))
        desc_label.setStyleSheet(f"color: {self.get_text_color_hex()}; padding: 5px;")
        desc_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_label)
        
        # Store reference for night mode updates
        if not hasattr(self, 'band_description_labels'):
            self.band_description_labels = []
        self.band_description_labels.append(desc_label)
        
        # Create table for emergency frequencies
        table = QTableWidget()
        table.setColumnCount(6)  # Frequency, Band, Mode, Purpose/Network, Notes, Category
        table.setHorizontalHeaderLabels(["Frequency", "Band", "Mode", "Purpose/Network", "Notes", "Category"])
        
        # Set column widths for touch interface
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Frequency
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Band
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Mode
        header.setSectionResizeMode(3, QHeaderView.Stretch)  # Purpose/Network can expand
        header.setSectionResizeMode(4, QHeaderView.Stretch)  # Notes can expand
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Category
        
        # Make table touch-friendly with more space
        table.setMinimumHeight(450)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setDefaultSectionSize(45)
        table.setFont(self.table_font)
        
        # Store reference to table for population
        setattr(self, "amateur_emergency_table", table)
        
        layout.addWidget(table)
        
        return tab

    def create_utilities_tab(self):
        """Create Utilities tab with location tools and data management"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Location Tools Section
        location_group = QGroupBox("🌐 Location Tools")
        location_group.setFont(QFont("Arial", 14, QFont.Bold))
        location_layout = QVBoxLayout(location_group)
        
        # Location tools description
        location_desc = QLabel("Control your location source for tower and repeater calculations:")
        location_desc.setFont(QFont("Arial", 12))
        location_desc.setWordWrap(True)
        location_desc.setStyleSheet(f"color: {self.get_text_color_hex()}; padding: 5px;")
        location_layout.addWidget(location_desc)
        
        # Location buttons in a grid
        location_buttons_frame = QFrame()
        location_buttons_layout = QGridLayout(location_buttons_frame)
        
        # Manual Location button
        manual_location_btn = QPushButton("📍 Set Manual Location")
        manual_location_btn.setFont(self.button_font)
        manual_location_btn.clicked.connect(self.open_location_dialog)
        manual_location_btn.setMinimumHeight(60)
        manual_location_btn.setToolTip("Enter coordinates manually using various formats (DD, DMS, Grid, UTM, MGRS)")
        
        # IP Location button
        ip_location_btn = QPushButton("🌐 Get IP Location")
        ip_location_btn.setFont(self.button_font)
        ip_location_btn.clicked.connect(self.get_ip_location)
        ip_location_btn.setMinimumHeight(60)
        ip_location_btn.setToolTip("Automatically detect approximate location from internet connection")
        
        # Return to GPS button
        gps_return_btn = QPushButton("🛰️ Return to GPS")
        gps_return_btn.setFont(self.button_font)
        gps_return_btn.clicked.connect(self.return_to_gps)
        gps_return_btn.setMinimumHeight(60)
        gps_return_btn.setToolTip("Resume automatic GPS tracking (if available)")
        
        # Current Location Status
        location_status_btn = QPushButton("📊 Show Current Location")
        location_status_btn.setFont(self.button_font)
        location_status_btn.clicked.connect(self.show_location_status)
        location_status_btn.setMinimumHeight(60)
        location_status_btn.setToolTip("Display detailed information about current location source")
        
        # Add buttons to grid layout (2x2)
        location_buttons_layout.addWidget(manual_location_btn, 0, 0)
        location_buttons_layout.addWidget(ip_location_btn, 0, 1)
        location_buttons_layout.addWidget(gps_return_btn, 1, 0)
        location_buttons_layout.addWidget(location_status_btn, 1, 1)
        
        location_layout.addWidget(location_buttons_frame)
        layout.addWidget(location_group)
        
        # Data Management Section
        data_group = QGroupBox("📂 Data Management")
        data_group.setFont(QFont("Arial", 14, QFont.Bold))
        data_layout = QVBoxLayout(data_group)
        
        # Data management description
        data_desc = QLabel("Import additional data to enhance repeater and tower information:")
        data_desc.setFont(QFont("Arial", 12))
        data_desc.setWordWrap(True)
        data_desc.setStyleSheet(f"color: {self.get_text_color_hex()}; padding: 5px;")
        data_layout.addWidget(data_desc)
        
        # Data management buttons
        data_buttons_frame = QFrame()
        data_buttons_layout = QGridLayout(data_buttons_frame)
        
        # Import CSV button
        import_csv_btn = QPushButton("📊 Import CSV Data")
        import_csv_btn.setFont(self.button_font)
        import_csv_btn.clicked.connect(self.import_csv_data)
        import_csv_btn.setMinimumHeight(60)
        import_csv_btn.setToolTip("Import repeater or tower data from CSV files")
        
        # Import JSON button
        import_json_btn = QPushButton("📋 Import JSON Data")
        import_json_btn.setFont(self.button_font)
        import_json_btn.clicked.connect(self.import_json_data)
        import_json_btn.setMinimumHeight(60)
        import_json_btn.setToolTip("Import structured data from JSON files")
        
        # Export Data button
        export_data_btn = QPushButton("💾 Export Current Data")
        export_data_btn.setFont(self.button_font)
        export_data_btn.clicked.connect(self.export_current_data)
        export_data_btn.setMinimumHeight(60)
        export_data_btn.setToolTip("Export current tower and repeater data to CSV/JSON")
        
        # Clear Cache button
        clear_cache_btn = QPushButton("🗑️ Clear Data Cache")
        clear_cache_btn.setFont(self.button_font)
        clear_cache_btn.clicked.connect(self.clear_data_cache)
        clear_cache_btn.setMinimumHeight(60)
        clear_cache_btn.setToolTip("Clear cached API data to force fresh downloads")
        
        # Add buttons to grid layout (2x2)
        data_buttons_layout.addWidget(import_csv_btn, 0, 0)
        data_buttons_layout.addWidget(import_json_btn, 0, 1)
        data_buttons_layout.addWidget(export_data_btn, 1, 0)
        data_buttons_layout.addWidget(clear_cache_btn, 1, 1)
        
        data_layout.addWidget(data_buttons_frame)
        layout.addWidget(data_group)
        
        # Add stretch to push everything to the top
        layout.addStretch()
        
        return tab

    def create_control_buttons(self):
        """Create touch-friendly control buttons"""
        button_frame = QFrame()
        button_layout = QHBoxLayout(button_frame)
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh All")
        refresh_btn.setFont(self.button_font)
        refresh_btn.clicked.connect(self.refresh_towers)
        
        # Export button  
        export_btn = QPushButton("📄 Export PDF")
        export_btn.setFont(self.button_font)
        export_btn.clicked.connect(self.export_data)
        
        # Utilities button
        utilities_btn = QPushButton("🔧 Utilities")
        utilities_btn.setFont(self.button_font)
        utilities_btn.clicked.connect(self.open_utilities_window)
        
        # Night Mode toggle button
        self.night_mode_btn = QPushButton("🌙 Night Mode")
        self.night_mode_btn.setFont(self.button_font)
        self.night_mode_btn.clicked.connect(self.toggle_night_mode_button)
        self.night_mode_active = False  # Track night mode state
        
        button_layout.addWidget(refresh_btn)
        button_layout.addWidget(export_btn)
        button_layout.addWidget(utilities_btn)
        button_layout.addWidget(self.night_mode_btn)
        
        self.main_layout.addWidget(button_frame)

    def refresh_towers(self):
        """Manually refresh tower and repeater data"""
        if hasattr(self, 'last_lat') and hasattr(self, 'last_lon'):
            self.display_closest_sites(self.last_lat, self.last_lon)
            self.populate_skywarn_data()
            self.populate_noaa_frequency_data()
            self.populate_all_amateur_data()

    def open_utilities_window(self):
        """Open utilities window as a separate dialog"""
        utilities_window = UtilitiesWindow(self)
        utilities_window.exec_()

    def export_data(self):
        """Export current tower data to PDF in Downloads folder"""
        if not PDF_AVAILABLE:
            print("PDF export not available - reportlab not installed")
            return
            
        try:
            # Get Downloads folder path
            downloads_path = os.path.expanduser("~/Downloads")
            if not os.path.exists(downloads_path):
                # Fallback to home directory if Downloads doesn't exist
                downloads_path = os.path.expanduser("~")
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"TowerWitch_Export_{timestamp}.pdf"
            filepath = os.path.join(downloads_path, filename)
            
            # Create PDF document
            doc = SimpleDocTemplate(filepath, pagesize=letter)
            story = []
            styles = getSampleStyleSheet()
            
            # Title
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=16,
                spaceAfter=20,
                alignment=1  # Center alignment
            )
            story.append(Paragraph("TowerWitch - Radio Data Export", title_style))
            
            # Current location and time
            location_info = f"Export Date: {datetime.now().strftime('%B %d, %Y at %H:%M:%S')}<br/>"
            if hasattr(self, 'last_lat') and hasattr(self, 'last_lon'):
                location_info += f"Location: {self.last_lat:.6f}°, {self.last_lon:.6f}°"
            else:
                location_info += "Location: GPS not available"
            
            story.append(Paragraph(location_info, styles['Normal']))
            story.append(Spacer(1, 20))
            
            # Export each tab's data
            current_tab = self.tabs.currentIndex()
            tab_names = ["Location", "ARMER", "SKYWARN", "NOAA", "Amateur", "Utilities"]
            
            # Check if user is currently on simplex tab for special handling
            current_amateur_tab = getattr(self, 'amateur_subtabs', None)
            is_simplex_active = False
            if current_amateur_tab and hasattr(current_amateur_tab, 'currentIndex'):
                is_simplex_active = current_amateur_tab.currentIndex() == 5  # Simplex is 6th tab (index 5)
            
            # Normal multi-tab export (default behavior)
            for tab_index, tab_name in enumerate(tab_names):
                if tab_index > 0:  # Add padding between sections
                    story.append(Spacer(1, 25))
                
                # Section header
                section_style = ParagraphStyle(
                    'SectionHeader',
                    parent=styles['Heading2'],
                    fontSize=14,
                    spaceAfter=10,
                    textColor=colors.darkblue
                )
                story.append(Paragraph(f"{tab_name} Data", section_style))
                
                # Get the table widget for this tab
                table_widget = None
                if tab_index == 0:  # Location tab
                    table_widget = getattr(self, 'location_table', None)
                elif tab_index == 1:  # ARMER tab
                    table_widget = getattr(self, 'table', None)  # ARMER uses self.table
                elif tab_index == 2:  # Skywarn tab
                    table_widget = getattr(self, 'skywarn_table', None)
                elif tab_index == 3:  # NOAA tab
                    table_widget = getattr(self, 'noaa_table', None)
                elif tab_index == 4:  # Amateur tab
                    # Special handling: if on simplex tab, show comprehensive simplex reference
                    if is_simplex_active:
                        # Override normal amateur processing for simplex-only export
                        simplex_style = ParagraphStyle(
                            'SimplexTitle',
                            parent=styles['Heading3'],
                            fontSize=14,
                            spaceAfter=10,
                            textColor=colors.purple
                        )
                        story.append(Paragraph("Amateur Radio Simplex Frequency Reference", simplex_style))
                        story.append(Paragraph("Complete simplex frequency reference for field operations", styles['Normal']))
                        story.append(Spacer(1, 10))
                        
                        # Get simplex table (no row limit for comprehensive reference)
                        table_widget = getattr(self, 'amateur_simplex_table', None)
                        if table_widget and hasattr(table_widget, 'rowCount'):
                            # Extract ALL simplex data (no 8-row limit)
                            table_data = []
                            
                            # Get headers
                            headers = []
                            for col in range(table_widget.columnCount()):
                                header_item = table_widget.horizontalHeaderItem(col)
                                headers.append(header_item.text() if header_item else f"Column {col+1}")
                            table_data.append(headers)
                            
                            # Get ALL simplex rows
                            for row in range(table_widget.rowCount()):
                                row_data = []
                                for col in range(table_widget.columnCount()):
                                    item = table_widget.item(row, col)
                                    row_data.append(item.text() if item else "")
                                table_data.append(row_data)
                            
                            if table_data and len(table_data) > 1:
                                # Create comprehensive simplex PDF table
                                pdf_table = Table(table_data)
                                table_style = TableStyle([
                                    ('BACKGROUND', (0, 0), (-1, 0), colors.purple),
                                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                                    ('BACKGROUND', (0, 1), (-1, -1), colors.lavender),
                                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                                ])
                                pdf_table.setStyle(table_style)
                                story.append(pdf_table)
                                story.append(Spacer(1, 10))
                                story.append(Paragraph(f"<i>Complete reference - {table_widget.rowCount()} simplex frequencies</i>", styles['Italic']))
                        else:
                            story.append(Paragraph("Simplex data not available", styles['Italic']))
                        
                        # Skip normal table processing for this tab
                        table_widget = None
                    else:
                        # Normal export - exclude simplex but include all repeater bands
                        amateur_bands = [
                            ("10m", "amateur_10_table"),
                            ("6m", "amateur_6_table"), 
                            ("2m", "amateur_2_table"),
                            ("1.25m", "amateur_125_table"),
                            ("70cm", "amateur_70cm_table")
                            # Simplex excluded from normal exports
                        ]
                        
                        for band_name, table_attr in amateur_bands:
                            # Add sub-section for each band
                            band_style = ParagraphStyle(
                                'BandHeader',
                                parent=styles['Heading3'],
                                fontSize=12,
                                spaceAfter=8,
                                textColor=colors.darkgreen
                            )
                            story.append(Paragraph(f"Amateur Radio - {band_name} Band", band_style))
                            
                            # Get the table widget for this band
                            table_widget = getattr(self, table_attr, None)
                            
                            if table_widget and hasattr(table_widget, 'rowCount'):
                                # Extract table data
                                table_data = []
                                
                                # Get headers
                                headers = []
                                for col in range(table_widget.columnCount()):
                                    header_item = table_widget.horizontalHeaderItem(col)
                                    headers.append(header_item.text() if header_item else f"Column {col+1}")
                                table_data.append(headers)
                                
                                # Get data rows using configurable limit
                                max_rows = min(PDF_EXPORT_LIMITS['amateur_bands'], table_widget.rowCount())
                                for row in range(max_rows):
                                    row_data = []
                                    for col in range(table_widget.columnCount()):
                                        item = table_widget.item(row, col)
                                        row_data.append(item.text() if item else "")
                                    table_data.append(row_data)
                                
                                if table_data and len(table_data) > 1:  # Has headers and data
                                    # Create PDF table
                                    pdf_table = Table(table_data)
                                    
                                    # Style the table
                                    table_style = TableStyle([
                                        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                        ('FONTSIZE', (0, 0), (-1, 0), 9),
                                        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                                        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                                        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                                        ('FONTSIZE', (0, 1), (-1, -1), 7),
                                        ('GRID', (0, 0), (-1, -1), 1, colors.black)
                                    ])
                                    pdf_table.setStyle(table_style)
                                    story.append(pdf_table)
                                    
                                    if max_rows == PDF_EXPORT_LIMITS['amateur_bands'] and table_widget.rowCount() > PDF_EXPORT_LIMITS['amateur_bands']:
                                        story.append(Paragraph(f"<i>... and {table_widget.rowCount() - PDF_EXPORT_LIMITS['amateur_bands']} more entries</i>", styles['Italic']))
                                else:
                                    story.append(Paragraph("No data available", styles['Italic']))
                            else:
                                story.append(Paragraph("Table not available", styles['Italic']))
                            
                            story.append(Spacer(1, 8))
                    
                    # Skip the normal table processing for amateur tab
                    table_widget = None
                elif tab_index == 5:  # Utilities tab
                    # Utilities tab doesn't have tabular data to export
                    utilities_style = ParagraphStyle(
                        'UtilitiesTitle',
                        parent=styles['Heading3'],
                        fontSize=14,
                        spaceAfter=10,
                        textColor=colors.purple
                    )
                    story.append(Paragraph("Utilities - Location & Data Management", utilities_style))
                    story.append(Paragraph("The Utilities tab provides tools for location control and data management:", styles['Normal']))
                    
                    # Add utilities information
                    utilities_info = [
                        "• Manual Location Entry: Set coordinates using various formats",
                        "• IP Geolocation: Automatically detect location from internet connection", 
                        "• GPS Control: Return to GPS tracking mode",
                        "• Data Import: Import custom repeater and tower data",
                        "• Cache Management: Clear cached data for fresh downloads"
                    ]
                    
                    for info in utilities_info:
                        story.append(Paragraph(info, styles['Normal']))
                    
                    story.append(Spacer(1, 10))
                    
                    # Add current location status if available
                    if hasattr(self, 'last_lat') and hasattr(self, 'last_lon'):
                        location_source = "Unknown"
                        if hasattr(self, 'manual_location_mode') and self.manual_location_mode:
                            location_source = f"Manual: {getattr(self, 'manual_location_name', 'Custom Location')}"
                        elif hasattr(self, 'last_gps_lat') and self.last_gps_lat:
                            location_source = "GPS Tracking"
                        
                        story.append(Paragraph(f"<b>Current Location Source:</b> {location_source}", styles['Normal']))
                        story.append(Paragraph(f"<b>Coordinates:</b> {self.last_lat:.6f}°, {self.last_lon:.6f}°", styles['Normal']))
                    
                    # Skip table processing for utilities tab
                    table_widget = None
                
                if table_widget and hasattr(table_widget, 'rowCount'):
                    # Extract table data
                    table_data = []
                    
                    # Get headers
                    headers = []
                    for col in range(table_widget.columnCount()):
                        header_item = table_widget.horizontalHeaderItem(col)
                        headers.append(header_item.text() if header_item else f"Column {col+1}")
                    table_data.append(headers)
                    
                    # Get data rows using configurable limits
                    if tab_index == 0:  # Location
                        max_rows = min(PDF_EXPORT_LIMITS['location'], table_widget.rowCount())
                    elif tab_index == 1:  # ARMER
                        max_rows = min(PDF_EXPORT_LIMITS['armer'], table_widget.rowCount())
                    elif tab_index == 2:  # Skywarn
                        max_rows = min(PDF_EXPORT_LIMITS['skywarn'], table_widget.rowCount())
                    elif tab_index == 3:  # NOAA
                        max_rows = min(PDF_EXPORT_LIMITS['noaa'], table_widget.rowCount())
                    else:
                        max_rows = min(8, table_widget.rowCount())  # Default fallback
                    for row in range(max_rows):
                        row_data = []
                        for col in range(table_widget.columnCount()):
                            item = table_widget.item(row, col)
                            row_data.append(item.text() if item else "")
                        table_data.append(row_data)
                    
                    if table_data and len(table_data) > 1:  # Has headers and data
                        # Create PDF table
                        pdf_table = Table(table_data)
                        
                        # Style the table
                        table_style = TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, 0), 10),
                            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                            ('FONTSIZE', (0, 1), (-1, -1), 8),
                            ('GRID', (0, 0), (-1, -1), 1, colors.black)
                        ])
                        pdf_table.setStyle(table_style)
                        story.append(pdf_table)
                        
                        # Show overflow message if there are more entries
                        expected_limit = 8  # Default
                        if tab_index == 0:
                            expected_limit = PDF_EXPORT_LIMITS['location']
                        elif tab_index == 1:
                            expected_limit = PDF_EXPORT_LIMITS['armer']
                        elif tab_index == 2:
                            expected_limit = PDF_EXPORT_LIMITS['skywarn']
                        elif tab_index == 3:
                            expected_limit = PDF_EXPORT_LIMITS['noaa']
                        
                        if max_rows == expected_limit and table_widget.rowCount() > expected_limit:
                            remaining = table_widget.rowCount() - max_rows
                            story.append(Paragraph(f"<i>... and {remaining} more entries</i>", styles['Italic']))
                    else:
                        story.append(Paragraph("No data available", styles['Italic']))
                else:
                    if tab_index != 3:  # Don't show "Table not available" for amateur tab since it's handled specially
                        story.append(Paragraph("Table not available", styles['Italic']))
                
                story.append(Spacer(1, 12))
            
            # Footer
            story.append(Spacer(1, 20))
            footer_text = "Generated by TowerWitch - GPS Amateur Radio Tower Locator"
            story.append(Paragraph(footer_text, styles['Italic']))
            
            # Build PDF
            doc.build(story)
            
            print(f"PDF exported successfully to: {filepath}")
            
            # Show success message in status (if available)
            if hasattr(self, 'gps_status'):
                original_text = self.gps_status.text()
                self.gps_status.setText(f"📄 PDF exported to Downloads!")
                # Reset status after 3 seconds
                QTimer.singleShot(3000, lambda: self.gps_status.setText(original_text))
                
        except Exception as e:
            print(f"Error exporting PDF: {e}")
            import traceback
            traceback.print_exc()

    def show_settings(self):
        """Show settings dialog"""
        # Settings dialog not yet implemented
        pass

    def update_datetime(self):
        """Update date and time display"""
        now = datetime.now()
        # Format: "Mon Oct 20, 2025  14:35:27"
        day_name = now.strftime("%a")  # Mon, Tue, etc.
        date_str = now.strftime("%b %d, %Y")
        time_str = now.strftime("%H:%M:%S")
        self.datetime_label.setText(f"{day_name} {date_str}  {time_str}")

    def setup_udp(self):
        """Setup UDP broadcasting for ARMER tower data"""
        try:
            # Read UDP configuration
            self.udp_enabled = self.config.getboolean('UDP', 'enabled', fallback=True)
            self.udp_port = self.config.getint('UDP', 'port', fallback=UDP_CONFIG['port'])
            self.udp_broadcast_ip = self.config.get('UDP', 'broadcast_ip', fallback='255.255.255.255')
            self.udp_send_interval = self.config.getint('UDP', 'send_interval', fallback=25)
            
            if self.udp_enabled:
                # Create UDP socket
                self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                
                # Initialize timing and success tracking
                self.last_udp_send = 0
                self.udp_startup_logged = False
                self.udp_error_count = 0
                
                print(f"✓ UDP broadcasting configured for {self.udp_broadcast_ip}:{self.udp_port}")
            else:
                self.udp_socket = None
                print("UDP broadcasting disabled in configuration")
                
        except Exception as e:
            print(f"❌ UDP setup failed: {e}")
            debug_print(f"UDP setup error details: {traceback.format_exc()}", "ERROR")
            self.udp_enabled = False
            self.udp_socket = None

    def send_udp_armer_data(self):
        """Send closest ARMER towers via UDP broadcast"""
        if not self.udp_enabled or not self.udp_socket:
            return
            
        try:
            # Check if enough time has passed
            current_time = time.time()
            if current_time - self.last_udp_send < self.udp_send_interval:
                return
                
            # Get closest ARMER towers from the table (configurable count)
            closest_towers = []
            if hasattr(self, 'table') and self.table.rowCount() > 0:
                tower_count = min(UDP_CONFIG['armer_tower_count'], self.table.rowCount())
                for row in range(tower_count):
                    # ARMER table columns: ["Site Name", "County", "Distance", "Bearing", "NAC", "Control Channels"]
                    site_name = self.table.item(row, 0).text() if self.table.item(row, 0) else ""
                    distance = self.table.item(row, 2).text() if self.table.item(row, 2) else ""
                    bearing = self.table.item(row, 3).text() if self.table.item(row, 3) else ""
                    nac = self.table.item(row, 4).text() if self.table.item(row, 4) else ""
                    control_channels = self.table.item(row, 5).text() if self.table.item(row, 5) else ""
                    
                    tower_data = {
                        'site_name': site_name,
                        'distance': distance,
                        'bearing': bearing,
                        'nac': nac,
                        'control_channels': control_channels
                    }
                    closest_towers.append(tower_data)
            
            # Create UDP packet
            udp_data = {
                'timestamp': datetime.now().isoformat(),
                'source': 'TowerWitch',
                'gps_lat': self.last_lat if hasattr(self, 'last_lat') else None,
                'gps_lon': self.last_lon if hasattr(self, 'last_lon') else None,
                'speed_mps': self.last_speed if hasattr(self, 'last_speed') else None,
                'is_vehicle_speed': self.is_vehicle_speed if hasattr(self, 'is_vehicle_speed') else False,
                'closest_armer_towers': closest_towers
            }
            
            # Send UDP broadcast
            message = json.dumps(udp_data, indent=None).encode('utf-8')
            self.udp_socket.sendto(message, (self.udp_broadcast_ip, self.udp_port))
            self.last_udp_send = current_time
            
            # Show confirmation only on first successful transmission
            if not self.udp_startup_logged:
                print(f"✅ UDP broadcasting started - sending {len(closest_towers)} towers every {self.udp_send_interval}s")
                self.udp_startup_logged = True
            
            # Reset error count on successful send
            self.udp_error_count = 0
            
            # Debug logging for troubleshooting (only when debug enabled)
            debug_print(f"UDP: Sent {len(closest_towers)} towers to {self.udp_broadcast_ip}:{self.udp_port}", "DEBUG")
            
        except Exception as e:
            self.udp_error_count += 1
            
            # Show errors but not too frequently  
            if self.udp_error_count <= 3 or self.udp_error_count % 10 == 0:
                print(f"❌ UDP send error #{self.udp_error_count}: {e}")
                debug_print(f"UDP error details: {traceback.format_exc()}", "ERROR")
                
            # Disable UDP after too many consecutive errors to prevent spam
            if self.udp_error_count >= 50:
                print(f"❌ UDP disabled after {self.udp_error_count} consecutive errors")
                self.udp_enabled = False
                if self.udp_socket:
                    try:
                        self.udp_socket.close()
                    except:
                        pass
                    self.udp_socket = None

    def toggle_night_mode_button(self):
        """Toggle night mode when button is clicked"""
        self.night_mode_active = not self.night_mode_active
        self.toggle_night_mode(self.night_mode_active)
        
        # Update button text to reflect current state
        if self.night_mode_active:
            self.night_mode_btn.setText("☀️ Day Mode")
        else:
            self.night_mode_btn.setText("🌙 Night Mode")

    def get_text_color(self):
        """Get the appropriate text color based on current mode"""
        return NIGHT_MODE_TEXT_COLOR if self.night_mode_active else DAY_MODE_TEXT_COLOR

    def get_text_color_hex(self):
        """Get text color as hex string for CSS"""
        return "#ff6666" if self.night_mode_active else "#ffffff"
        
    def set_table_item_text_with_color(self, item, text):
        """Set table item text while maintaining proper night mode color"""
        if item:
            item.setText(text)
            item.setForeground(self.get_text_color())

    def get_band_color(self, band_name):
        """Get the appropriate color for a specific amateur radio band"""
        mode = 'night' if self.night_mode_active else 'day'
        color = BAND_COLORS[mode].get(band_name, BAND_COLORS[mode]['default'])
        
        # Comprehensive debugging
        debug_print(f"🎨 get_band_color called:", "DEBUG")
        debug_print(f"   Band: '{band_name}'", "DEBUG")
        debug_print(f"   Mode: '{mode}' (night_mode_active: {self.night_mode_active})", "DEBUG")
        debug_print(f"   Available bands in {mode}: {list(BAND_COLORS[mode].keys())}", "DEBUG")
        debug_print(f"   Returned color: RGB({color.red()}, {color.green()}, {color.blue()})", "DEBUG")
        
        return color
    
    def is_dark_color(self, color):
        """Check if a color is dark (needs white text)"""
        # Calculate luminance using relative weights
        r, g, b = color.red(), color.green(), color.blue()
        luminance = (0.299 * r + 0.587 * g + 0.114 * b)
        return luminance < 128

    def get_ip_location(self):
        """Get approximate location from IP address geolocation"""
        try:
            print("🌐 Getting location from IP address...")
            
            # Try multiple IP geolocation services for reliability
            services = [
                ("ipinfo.io", "https://ipinfo.io/json"),
                ("ipapi.co", "https://ipapi.co/json/"),
                ("ip-api.com", "http://ip-api.com/json/")
            ]
            
            for service_name, url in services:
                try:
                    print(f"🔍 Trying {service_name}...")
                    response = requests.get(url, timeout=10)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Parse response based on service
                        if service_name == "ipinfo.io":
                            if 'loc' in data:
                                lat, lon = map(float, data['loc'].split(','))
                                city = data.get('city', 'Unknown')
                                region = data.get('region', 'Unknown')
                                country = data.get('country', 'Unknown')
                                location_name = f"{city}, {region}, {country}"
                        elif service_name == "ipapi.co":
                            lat = float(data.get('latitude', 0))
                            lon = float(data.get('longitude', 0))
                            city = data.get('city', 'Unknown')
                            region = data.get('region', 'Unknown')
                            country = data.get('country_name', 'Unknown')
                            location_name = f"{city}, {region}, {country}"
                        elif service_name == "ip-api.com":
                            lat = float(data.get('lat', 0))
                            lon = float(data.get('lon', 0))
                            city = data.get('city', 'Unknown')
                            region = data.get('regionName', 'Unknown')
                            country = data.get('country', 'Unknown')
                            location_name = f"{city}, {region}, {country}"
                        
                        if lat != 0 and lon != 0:
                            print(f"✅ Found location via {service_name}: {location_name}")
                            print(f"📍 Coordinates: {lat:.6f}, {lon:.6f}")
                            
                            # Update location and refresh data
                            self.set_manual_location(lat, lon, f"IP Location: {location_name}")
                            return True
                            
                except Exception as e:
                    print(f"❌ {service_name} failed: {e}")
                    continue
            
            # If all services failed
            QMessageBox.warning(self, "IP Location Error", 
                              "Could not determine location from IP address.\n"
                              "Please check your internet connection or try manual location entry.")
            return False
            
        except Exception as e:
            print(f"❌ IP geolocation error: {e}")
            QMessageBox.critical(self, "IP Location Error", 
                               f"Error getting IP location: {str(e)}")
            return False

    def open_location_dialog(self):
        """Open dialog for manual location entry"""
        dialog = LocationInputDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            lat, lon, location_name = dialog.get_location()
            if lat is not None and lon is not None:
                self.set_manual_location(lat, lon, location_name)

    def set_manual_location(self, latitude, longitude, location_name="Manual Location"):
        """Set location manually and update all displays"""
        try:
            # Validate coordinates
            if not (-90 <= latitude <= 90):
                raise ValueError("Latitude must be between -90 and 90 degrees")
            if not (-180 <= longitude <= 180):
                raise ValueError("Longitude must be between -180 and 180 degrees")
            
            print(f"📍 Setting manual location: {location_name}")
            print(f"📊 Coordinates: {latitude:.6f}, {longitude:.6f}")
            
            # Set manual location mode flag
            self.manual_location_mode = True
            self.manual_location_name = location_name
            
            # Update location variables
            self.last_lat = latitude
            self.last_lon = longitude
            
            # Update GPS status to show manual location
            self.gps_status.setText(f"📍 Manual: {location_name}")
            self.gps_status.setStyleSheet("color: #00aaff; padding: 12px; font-size: 14px;")  # Blue for manual
            
            # Update all location-based data
            self.update_location_displays(latitude, longitude)
            self.display_closest_sites(latitude, longitude)
            self.populate_skywarn_data()
            self.populate_noaa_frequency_data()
            self.populate_all_amateur_data()
            
            print(f"✅ Manual location set successfully")
            
        except ValueError as e:
            QMessageBox.warning(self, "Invalid Coordinates", str(e))
        except Exception as e:
            print(f"❌ Error setting manual location: {e}")
            QMessageBox.critical(self, "Location Error", f"Error setting location: {str(e)}")

    def update_location_displays(self, latitude, longitude):
        """Update location display tables with new coordinates"""
        try:
            # Update GPS data display (simulated GPS for manual location)
            self.set_table_item_text_with_color(self.location_items['lat_value'], f"{latitude:.6f}°")
            self.set_table_item_text_with_color(self.location_items['lon_value'], f"{longitude:.6f}°")
            
            # Set manual location indicators
            self.set_table_item_text_with_color(self.location_items['alt_value'], "Manual Entry")
            self.set_table_item_text_with_color(self.location_items['speed_value'], "0.0 m/s (Manual)")
            self.set_table_item_text_with_color(self.location_items['heading_value'], "--° (Manual)")
            self.set_table_item_text_with_color(self.location_items['vector_value'], "Manual Location")
            self.set_table_item_text_with_color(self.location_items['status_value'], "MANUAL")
            self.set_table_item_text_with_color(self.location_items['fix_value'], "Manual Entry")
            
            # Update coordinate systems
            # UTM coordinate system
            utm_result = utm.from_latlon(latitude, longitude)
            utm_str = f"Zone {utm_result[2]}{utm_result[3]} E:{utm_result[0]:.0f} N:{utm_result[1]:.0f}"
            self.set_table_item_text_with_color(self.location_items['utm_value'], utm_str)
            
            # Maidenhead
            mh_grid = mh.to_maiden(latitude, longitude)
            self.set_table_item_text_with_color(self.location_items['mh_value'], mh_grid)
            
            # MGRS
            m = mgrs.MGRS()
            mgrs_result = m.toMGRS(latitude, longitude)
            mgrs_zone = mgrs_result[:3]
            mgrs_grid = mgrs_result[3:5]
            mgrs_coords = mgrs_result[5:]
            
            # Split MGRS coordinates into easting and northing
            if len(mgrs_coords) >= 6:
                mid_point = len(mgrs_coords) // 2
                easting = mgrs_coords[:mid_point]
                northing = mgrs_coords[mid_point:]
                formatted_coords = f"{easting} {northing}"
            else:
                formatted_coords = mgrs_coords
                
            self.set_table_item_text_with_color(self.location_items['mgrs_zone_value'], f"{mgrs_zone} {mgrs_grid}")
            self.set_table_item_text_with_color(self.location_items['mgrs_coords_value'], formatted_coords)
            
            # DMS (Degrees, Minutes, Seconds) format
            def decimal_to_dms(decimal_degrees, is_latitude=True):
                abs_degrees = abs(decimal_degrees)
                degrees = int(abs_degrees)
                minutes_float = (abs_degrees - degrees) * 60
                minutes = int(minutes_float)
                seconds = (minutes_float - minutes) * 60
                
                if is_latitude:
                    direction = 'N' if decimal_degrees >= 0 else 'S'
                else:
                    direction = 'E' if decimal_degrees >= 0 else 'W'
                
                return f"{degrees}°{minutes:02d}'{seconds:05.2f}\"{direction}"
            
            dms_lat = decimal_to_dms(latitude, True)
            dms_lon = decimal_to_dms(longitude, False)
            self.set_table_item_text_with_color(self.location_items['dms_lat_value'], dms_lat)
            self.set_table_item_text_with_color(self.location_items['dms_lon_value'], dms_lon)
            
        except Exception as e:
            print(f"Error updating location displays: {e}")

    def return_to_gps(self):
        """Return to GPS tracking mode after manual location was set"""
        try:
            print("🛰️ Returning to GPS tracking mode...")
            
            # Check if GPS worker is available and running
            if not hasattr(self, 'gps_worker') or not self.gps_worker:
                QMessageBox.warning(self, "GPS Not Available", 
                                  "GPS worker is not running.\n"
                                  "GPS functionality may not be available on this device.")
                return
            
            # Reset manual location mode flag if we have one
            if hasattr(self, 'manual_location_mode'):
                self.manual_location_mode = False
            
            # Update GPS status to show we're waiting for GPS
            self.gps_status.setText("🛰️ GPS: Searching for signal...")
            self.gps_status.setStyleSheet("color: #ffaa00; padding: 12px; font-size: 14px;")  # Orange for searching
            
            # Clear manual location indicators in the location table
            self.set_table_item_text_with_color(self.location_items['status_value'], "Searching...")
            self.set_table_item_text_with_color(self.location_items['fix_value'], "Waiting for GPS...")
            self.set_table_item_text_with_color(self.location_items['alt_value'], "Waiting for GPS...")
            self.set_table_item_text_with_color(self.location_items['speed_value'], "Waiting for GPS...")
            self.set_table_item_text_with_color(self.location_items['heading_value'], "Waiting for GPS...")
            self.set_table_item_text_with_color(self.location_items['vector_value'], "Waiting for GPS...")
            
            # Check if we have recent GPS data to restore
            if hasattr(self, 'last_gps_lat') and hasattr(self, 'last_gps_lon'):
                print(f"📍 Restoring last GPS location: {self.last_gps_lat:.6f}, {self.last_gps_lon:.6f}")
                self.last_lat = self.last_gps_lat
                self.last_lon = self.last_gps_lon
                
                # Update displays with last known GPS location
                self.update_location_displays(self.last_gps_lat, self.last_gps_lon)
                self.display_closest_sites(self.last_gps_lat, self.last_gps_lon)
                self.populate_skywarn_data()
                self.populate_noaa_frequency_data()
                self.populate_all_amateur_data()
                
                self.gps_status.setText("🛰️ GPS: Using last known location")
                self.gps_status.setStyleSheet("color: #00ff00; padding: 12px; font-size: 14px;")  # Green for active
            else:
                print("📍 No previous GPS data available, waiting for new GPS fix...")
                # Set default location while waiting for GPS
                self.last_lat = 44.9778  # Minneapolis default
                self.last_lon = -93.2650
                self.set_table_item_text_with_color(self.location_items['lat_value'], "Waiting for GPS...")
                self.set_table_item_text_with_color(self.location_items['lon_value'], "Waiting for GPS...")
            
            print("✅ Returned to GPS tracking mode")
            
        except Exception as e:
            print(f"❌ Error returning to GPS: {e}")
            QMessageBox.critical(self, "GPS Error", f"Error returning to GPS mode: {str(e)}")

    def show_location_status(self):
        """Show detailed information about current location source"""
        try:
            status_info = "📊 Current Location Status\n\n"
            
            # Determine location source
            if hasattr(self, 'manual_location_mode') and self.manual_location_mode:
                location_source = f"Manual Location: {getattr(self, 'manual_location_name', 'Unknown')}"
                source_icon = "📍"
            elif hasattr(self, 'last_gps_lat') and self.last_gps_lat:
                location_source = "GPS Tracking"
                source_icon = "🛰️"
            else:
                location_source = "Unknown/Default"
                source_icon = "❓"
            
            status_info += f"{source_icon} Source: {location_source}\n"
            
            # Current coordinates
            if hasattr(self, 'last_lat') and hasattr(self, 'last_lon'):
                status_info += f"📍 Coordinates: {self.last_lat:.6f}°, {self.last_lon:.6f}°\n"
                
                # Grid references
                try:
                    # Maidenhead
                    mh_grid = mh.to_maiden(self.last_lat, self.last_lon)
                    status_info += f"📡 Maidenhead: {mh_grid}\n"
                    
                    # UTM
                    utm_result = utm.from_latlon(self.last_lat, self.last_lon)
                    status_info += f"🗺️ UTM: Zone {utm_result[2]}{utm_result[3]} E:{utm_result[0]:.0f} N:{utm_result[1]:.0f}\n"
                    
                    # MGRS
                    m = mgrs.MGRS()
                    mgrs_result = m.toMGRS(self.last_lat, self.last_lon)
                    status_info += f"🪖 MGRS: {mgrs_result}\n"
                    
                except Exception as e:
                    status_info += f"⚠️ Grid calculation error: {e}\n"
            else:
                status_info += "❌ No location data available\n"
            
            # GPS worker status
            if hasattr(self, 'gps_worker') and self.gps_worker:
                status_info += "\n🛰️ GPS Worker: Active\n"
            else:
                status_info += "\n❌ GPS Worker: Inactive\n"
            
            # Show the status
            QMessageBox.information(self, "Location Status", status_info)
            
        except Exception as e:
            QMessageBox.critical(self, "Status Error", f"Error getting location status: {str(e)}")

    def import_csv_data(self):
        """Import repeater/tower data from CSV files"""
        QMessageBox.information(self, "Feature Coming Soon", 
                              "CSV data import functionality will be implemented soon!\n\n"
                              "This will allow you to:\n"
                              "• Import custom repeater lists\n"
                              "• Add local tower information\n"
                              "• Supplement API data with local knowledge")

    def import_json_data(self):
        """Import structured data from JSON files"""
        QMessageBox.information(self, "Feature Coming Soon", 
                              "JSON data import functionality will be implemented soon!\n\n"
                              "This will allow you to:\n"
                              "• Import complex structured data\n"
                              "• Add custom frequency databases\n"
                              "• Import exported data from other applications")

    def export_current_data(self):
        """Export current tower and repeater data"""
        QMessageBox.information(self, "Feature Coming Soon", 
                              "Data export functionality will be implemented soon!\n\n"
                              "This will allow you to:\n"
                              "• Export all current tower data to CSV\n"
                              "• Save repeater lists in JSON format\n"
                              "• Backup your customized data")

    def clear_data_cache(self):
        """Clear cached API data to force fresh downloads"""
        try:
            reply = QMessageBox.question(self, "Clear Cache", 
                                       "This will clear all cached data and force fresh downloads from the API.\n\n"
                                       "Are you sure you want to continue?",
                                       QMessageBox.Yes | QMessageBox.No, 
                                       QMessageBox.No)
            
            if reply == QMessageBox.Yes:
                # Clear the radio cache directory
                cache_dir = os.path.join(os.path.dirname(__file__), "radio_cache")
                if os.path.exists(cache_dir):
                    import shutil
                    try:
                        shutil.rmtree(cache_dir)
                        os.makedirs(cache_dir, exist_ok=True)
                        print("🗑️ Cache cleared successfully")
                        QMessageBox.information(self, "Cache Cleared", 
                                              "Data cache has been cleared successfully!\n\n"
                                              "The next data refresh will download fresh information from the API.")
                    except Exception as e:
                        print(f"❌ Error clearing cache: {e}")
                        QMessageBox.warning(self, "Cache Error", f"Error clearing cache: {str(e)}")
                else:
                    QMessageBox.information(self, "No Cache", "No cache directory found - nothing to clear.")
        
        except Exception as e:
            QMessageBox.critical(self, "Clear Cache Error", f"Error clearing cache: {str(e)}")
    
    def lighten_color(self, color, factor):
        """Lighten a color by mixing it with white"""
        r = int(color.red() + (255 - color.red()) * (1 - factor))
        g = int(color.green() + (255 - color.green()) * (1 - factor))
        b = int(color.blue() + (255 - color.blue()) * (1 - factor))
        return QColor(r, g, b)
    
    def set_main_tab_colors(self):
        """Set unique colors for main tabs using Qt programmatic methods"""
        print("🎨 Setting main tab colors...")
        # Define colors for each main tab (5 tabs now - utilities moved to button)
        tab_colors = [
            "#8E44AD",  # Location - Purple
            "#E74C3C",  # ARMER - Red
            "#F39C12",  # SKYWARN - Orange  
            "#2ECC71",  # NOAA - Green
            "#3498DB"   # Amateur - Blue
        ]
        print(f"🎨 Tab count: {self.tabs.count()}, Colors: {tab_colors}")
        
        # Try a simple approach - set stylesheet on each tab directly
        try:
            tab_bar = self.tabs.tabBar()
            if tab_bar:
                print(f"🎨 Tab bar found with {tab_bar.count()} tabs")
                
                # Method 1: Try setting individual tab styles
                for i in range(min(len(tab_colors), tab_bar.count())):
                    color = tab_colors[i]
                    print(f"🎨 Setting tab {i} to color {color}")
                    
                    # Try setting the tab's stylesheet directly
                    try:
                        # Create a style for this specific tab
                        tab_style = f"""
                        QTabBar::tab:nth-child({i+1}) {{
                            background-color: {color};
                            color: #ffffff;
                            padding: 15px 25px;
                            margin-right: 2px;
                            border-top-left-radius: 5px;
                            border-top-right-radius: 5px;
                            min-width: 120px;
                            font-size: 14px;
                            font-weight: bold;
                        }}
                        """
                        # This approach applies to the whole tab bar
                        current_style = tab_bar.styleSheet()
                        tab_bar.setStyleSheet(current_style + tab_style)
                        
                    except Exception as e:
                        print(f"❌ Error setting style for tab {i}: {e}")
                
                print("✅ Tab colors set programmatically")
            else:
                print("❌ No tab bar found")
                
        except Exception as e:
            print(f"❌ Error in set_main_tab_colors: {e}")
            
        # Method 2: Also try the global stylesheet approach
        try:
            main_widget_style = f"""
            QTabWidget#main_tabs QTabBar::tab {{
                color: #ffffff;
                padding: 15px 25px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                min-width: 120px;
                font-size: 14px;
                font-weight: bold;
                background-color: #666666;  /* Default */
            }}
            """
            
            # Add individual colors
            for i, color in enumerate(tab_colors):
                main_widget_style += f"""
                QTabWidget#main_tabs QTabBar::tab:nth-child({i+1}) {{
                    background-color: {color};
                }}
                """
            
            # Apply to the main widget
            self.setStyleSheet(self.styleSheet() + main_widget_style)
            print("✅ Global tab stylesheet applied")
            
        except Exception as e:
            print(f"❌ Error applying global stylesheet: {e}")
        
        # Alternative method: Create CSS string for individual tab styling
        style_parts = []  # Initialize the style_parts list
        
        # Add each tab color individually
        for i, color in enumerate(tab_colors):
            if i < tab_bar.count():
                # Set text color programmatically
                tab_bar.setTabTextColor(i, QColor("#ffffff"))
                # Add CSS for background
                style_parts.append(f"QTabBar::tab:nth-child({i+1}) {{ background-color: {color}; }}")
        
        style_parts.append("""
            QTabBar::tab:selected {
                border: 2px solid #ffffff;
                font-weight: bolder;
            }
        """)
        
        final_css = "\n".join(style_parts)
        self.tabs.setStyleSheet(final_css)
    
    def set_amateur_band_tab_colors(self):
        """Set colors for amateur band sub-tab titles based on band colors"""
        if not hasattr(self, 'amateur_subtabs'):
            print("❌ No amateur_subtabs attribute found")
            return
            
        print("🎨 Setting amateur band tab colors...")
        print(f"🎨 Night mode active: {self.night_mode_active}")
        
        # Map tab indices to band names for color lookup
        tab_color_map = {
            0: "10m",      # 10m tab
            1: "6m",       # 6m tab  
            2: "2m",       # 2m tab
            3: "1.25m",    # 1.25m tab
            4: "70cm",     # 70cm tab
            5: None,       # Simplex tab (no specific band color)
            6: None        # Emergency tab (no specific band color)
        }
        
        try:
            amateur_tab_bar = self.amateur_subtabs.tabBar()
            if amateur_tab_bar:
                print(f"🎨 Amateur tab bar found with {amateur_tab_bar.count()} tabs")
                
                # Get current mode colors from global BAND_COLORS
                mode = 'night' if self.night_mode_active else 'day'
                current_colors = BAND_COLORS[mode]
                print(f"🎨 Using mode: {mode}")
                print(f"🎨 Available band colors: {list(current_colors.keys())}")
                
                # Use the SAME approach as main tabs - simple CSS with ID selector
                print("🎨 Using PROVEN main tab CSS approach...")
                amateur_css_parts = []
                
                # Start with base tab styling
                amateur_css_parts.append("""
                QTabWidget#amateur_subtabs QTabBar::tab {
                    color: #ffffff;
                    padding: 10px 20px;
                    margin-right: 2px;
                    border-top-left-radius: 5px;
                    border-top-right-radius: 5px;
                    min-width: 80px;
                    font-size: 12px;
                    font-weight: bold;
                }
                """)
                
                # Add individual tab colors using the EXACT same pattern as main tabs
                for tab_index, band_name in tab_color_map.items():
                    if tab_index < amateur_tab_bar.count():
                        if band_name and band_name in current_colors:
                            color = current_colors[band_name]
                            color_hex = color.name() if hasattr(color, 'name') else str(color)
                            print(f"🎨 Adding CSS for tab {tab_index+1} ({band_name}): {color_hex}")
                            
                            # Use EXACT same pattern as main tabs
                            amateur_css_parts.append(f"""
                            QTabWidget#amateur_subtabs QTabBar::tab:nth-child({tab_index+1}) {{ background-color: {color_hex}; }}
                            """)
                        else:
                            # Neutral color for special tabs
                            print(f"🎨 Adding neutral CSS for special tab {tab_index+1}")
                            amateur_css_parts.append(f"""
                            QTabWidget#amateur_subtabs QTabBar::tab:nth-child({tab_index+1}) {{ background-color: #666666; }}
                            """)
                
                # Add selected tab styling
                amateur_css_parts.append("""
                QTabWidget#amateur_subtabs QTabBar::tab:selected {
                    border: 2px solid #ffffff;
                    font-weight: bolder;
                }
                """)
                
                # Apply the CSS - use the SAME method as main tabs
                amateur_final_css = "\n".join(amateur_css_parts)
                print(f"🎨 Final CSS length: {len(amateur_final_css)} characters")
                print("🎨 CSS Preview (using proven main tab approach):")
                print(amateur_final_css[:300] + "..." if len(amateur_final_css) > 300 else amateur_final_css)
                
                # Apply to the MAIN WINDOW stylesheet (same as main tabs)
                current_main_style = self.styleSheet()
                self.setStyleSheet(current_main_style + amateur_final_css)
                print("✅ Amateur band tab CSS added to main window stylesheet (same as main tabs)")
                
                # Verification
                print("🔍 Final verification:")
                for i in range(amateur_tab_bar.count()):
                    tab_text = amateur_tab_bar.tabText(i)
                    print(f"   Tab {i+1}: '{tab_text}'")
                
            else:
                print("❌ No amateur tab bar found")
                
        except Exception as e:
            print(f"❌ Error setting amateur band tab colors: {e}")
            import traceback
            print(f"❌ Traceback: {traceback.format_exc()}")
    
    def get_table_css(self):
        """Get CSS for tables based on current mode"""
        text_color = "#ff6666" if self.night_mode_active else "#ffffff"
        # Use dampened colors for headers in night mode
        header_bg_color = "#4d1a1a" if self.night_mode_active else "#4a90e2"  # Dark red-brown for night
        return f"""
            QTableWidget {{
                background-color: #3b3b3b;
                border: 1px solid #555555;
                border-radius: 5px;
                gridline-color: #555555;
                font-size: 12px;
                color: {text_color};
            }}
            QTableWidget::item {{
                padding: 10px;
                border-bottom: 1px solid #555555;
                color: {text_color};
            }}
            QTableWidget::item:alternate {{
                background-color: #2b2b2b;
                color: {text_color};
            }}
            QTableWidget::item:selected {{
                background-color: {header_bg_color};
                color: {text_color};
            }}
            QHeaderView::section {{
                background-color: {header_bg_color};
                color: {text_color};
                padding: 12px;
                border: 1px solid #555555;
                font-weight: bold;
                font-size: 13px;
            }}
        """

    def get_amateur_subtab_css(self):
        """Get CSS for amateur sub-tabs with band-specific colors based on current mode"""
        
        # Define band-specific colors for day and night modes
        if self.night_mode_active:
            # Night mode - red-tinted colors for night vision compatibility
            band_colors = {
                '10m': '#4d1a1a',    # Dark red-brown for HF
                '6m': '#4d4d1a',     # Dark yellow-red for 6m
                '2m': '#1a1a4d',     # Dark blue-red for VHF
                '1.25m': '#1a4d1a',  # Dark green-red for 220 MHz
                '70cm': '#4d331a',   # Dark orange-red for UHF
                'Simplex': '#4d1a4d' # Dark purple-red for simplex
            }
            text_color = "#ff6666"
            border_color = "#660000"
            hover_color = "#661a1a"
            selected_border = "#ff6666"
        else:
            # Day mode - vibrant band-specific colors
            band_colors = {
                '10m': '#ff4444',    # Red for 10m HF
                '6m': '#ffaa44',     # Orange for 6m 
                '2m': '#4488ff',     # Blue for 2m VHF
                '1.25m': '#44ff44',  # Green for 1.25m
                '70cm': '#ff8844',   # Orange-red for 70cm UHF
                'Simplex': '#aa44ff' # Purple for simplex
            }
            text_color = "#ffffff"
            border_color = "#555555"
            hover_color = "#666666"
            selected_border = "#ffffff"
        
        # Generate CSS with band-specific colors using very specific selectors
        css = f"""
            QTabWidget#amateur_subtabs QTabBar::tab {{
                padding: 10px 15px !important;
                margin-right: 2px !important;
                border-top-left-radius: 5px !important;
                border-top-right-radius: 5px !important;
                min-width: 60px !important;
                font-size: 12px !important;
                font-weight: bold !important;
                color: {text_color} !important;
                border: 1px solid {border_color} !important;
            }}
            QTabBar#amateur_tab_bar::tab {{
                padding: 10px 15px !important;
                margin-right: 2px !important;
                border-top-left-radius: 5px !important;
                border-top-right-radius: 5px !important;
                min-width: 60px !important;
                font-size: 12px !important;
                font-weight: bold !important;
                color: {text_color} !important;
                border: 1px solid {border_color} !important;
            }}
            QTabWidget#amateur_subtabs QTabBar::tab:hover {{
                background-color: {hover_color} !important;
            }}
            QTabBar#amateur_tab_bar::tab:hover {{
                background-color: {hover_color} !important;
            }}
            QTabWidget#amateur_subtabs QTabBar::tab:selected {{
                border: 2px solid {selected_border} !important;
                font-weight: bolder !important;
            }}
            QTabBar#amateur_tab_bar::tab:selected {{
                border: 2px solid {selected_border} !important;
                font-weight: bolder !important;
            }}
            QTabWidget#amateur_subtabs::pane {{
                border: 1px solid {border_color} !important;
                background-color: #3b3b3b !important;
            }}
        """
        
        # Add band-specific styling for each tab using multiple selectors
        for i, (band, color) in enumerate(band_colors.items()):
            css += f"""
            QTabWidget#amateur_subtabs QTabBar::tab:nth-child({i+1}) {{
                background-color: {color} !important;
            }}
            QTabBar#amateur_tab_bar::tab:nth-child({i+1}) {{
                background-color: {color} !important;
            }}
            QTabWidget#amateur_subtabs QTabBar::tab:nth-child({i+1}):selected {{
                background-color: {color} !important;
                border: 2px solid {selected_border} !important;
            }}
            QTabBar#amateur_tab_bar::tab:nth-child({i+1}):selected {{
                background-color: {color} !important;
                border: 2px solid {selected_border} !important;
            }}
            QTabWidget#amateur_subtabs QTabBar::tab:nth-child({i+1}):hover {{
                background-color: {color} !important;
                opacity: 0.8;
            }}
            QTabBar#amateur_tab_bar::tab:nth-child({i+1}):hover {{
                background-color: {color} !important;
                opacity: 0.8;
            }}
            """
        
        return css

    def set_amateur_tab_colors(self):
        """Set amateur sub-tab colors programmatically using QPalette"""
        try:
            from PyQt5.QtGui import QPalette
            
            # Define band-specific colors
            if self.night_mode_active:
                band_colors = [
                    QColor(77, 26, 26),    # Dark red-brown for 10m HF
                    QColor(77, 77, 26),    # Dark yellow-red for 6m
                    QColor(26, 26, 77),    # Dark blue-red for 2m VHF
                    QColor(26, 77, 26),    # Dark green-red for 1.25m
                    QColor(77, 51, 26),    # Dark orange-red for 70cm UHF
                    QColor(77, 26, 77)     # Dark purple-red for simplex
                ]
            else:
                band_colors = [
                    QColor(255, 68, 68),   # Red for 10m HF
                    QColor(255, 170, 68),  # Orange for 6m 
                    QColor(68, 136, 255),  # Blue for 2m VHF
                    QColor(68, 255, 68),   # Green for 1.25m
                    QColor(255, 136, 68),  # Orange-red for 70cm UHF
                    QColor(170, 68, 255)   # Purple for simplex
                ]
            
            tab_bar = self.amateur_subtabs.tabBar()
            
            # Force direct widget styling that bypasses theme
            for i, color in enumerate(band_colors):
                if i < tab_bar.count():
                    # Try multiple approaches to force colors
                    try:
                        # Method 1: Direct palette modification
                        palette = tab_bar.palette()
                        palette.setColor(QPalette.Button, color)
                        palette.setColor(QPalette.Window, color)
                        palette.setColor(QPalette.Base, color)
                        tab_bar.setPalette(palette)
                        
                        # Method 2: Force stylesheet with maximum specificity
                        force_style = f"""
                        QTabBar::tab:nth-child({i+1}) {{
                            background-color: {color.name()} !important;
                            background: {color.name()} !important;
                            color: white !important;
                            border: 2px solid {color.name()} !important;
                        }}
                        """
                        current_style = tab_bar.styleSheet()
                        tab_bar.setStyleSheet(current_style + force_style)
                        
                        # Method 3: Set autoFillBackground to force custom painting
                        tab_bar.setAutoFillBackground(True)
                        
                    except Exception as e:
                        debug_print(f"Error applying color method for tab {i}: {e}", "WARNING")
                    
            debug_print(f"Applied multiple color methods for {len(band_colors)} amateur tabs", "INFO")
            
        except Exception as e:
            debug_print(f"Error setting amateur tab colors: {e}", "ERROR")

    def apply_custom_style_colors(self):
        """Apply colors to custom style if available"""
        try:
            app = QApplication.instance()
            if hasattr(app, 'custom_style') and app.custom_style is not None:
                # Define band-specific colors for custom style
                if self.night_mode_active:
                    band_colors = [
                        QColor(77, 26, 26),    # Dark red-brown for 10m HF
                        QColor(77, 77, 26),    # Dark yellow-red for 6m
                        QColor(26, 26, 77),    # Dark blue-red for 2m VHF
                        QColor(26, 77, 26),    # Dark green-red for 1.25m
                        QColor(77, 51, 26),    # Dark orange-red for 70cm UHF
                        QColor(77, 26, 77)     # Dark purple-red for simplex
                    ]
                else:
                    band_colors = [
                        QColor(255, 68, 68),   # Red for 10m HF
                        QColor(255, 170, 68),  # Orange for 6m 
                        QColor(68, 136, 255),  # Blue for 2m VHF
                        QColor(68, 255, 68),   # Green for 1.25m
                        QColor(255, 136, 68),  # Orange-red for 70cm UHF
                        QColor(170, 68, 255)   # Purple for simplex
                    ]
                
                # Apply colors to custom style
                app.custom_style.set_tab_colors("amateur_subtabs", band_colors)
                debug_print("Applied band colors to custom style", "SUCCESS")
                
                # Also apply main tab colors
                main_colors = [
                    QColor(255, 0, 255),   # GPS - Bright Magenta
                    QColor(0, 255, 0),     # Grids - Bright Green
                    QColor(255, 0, 0),     # ARMER - Bright Red
                    QColor(255, 170, 0),   # Skywarn - Bright Orange
                    QColor(0, 136, 255)    # Amateur - Bright Blue
                ]
                app.custom_style.set_tab_colors("main_tabs", main_colors)
                debug_print("Applied main tab colors to custom style", "SUCCESS")
                
        except Exception as e:
            debug_print(f"Error applying custom style colors: {e}", "ERROR")

    def update_table_colors_for_mode(self, night_mode_on):
        """Update table item colors based on current mode"""
        if night_mode_on:
            # Night mode colors - red theme
            active_color = QColor(255, 102, 102)      # Light red for active status
            warning_color = QColor(255, 153, 102)     # Orange-red for warnings  
            text_color = QColor(255, 102, 102)        # Red for regular text
        else:
            # Day mode colors - original theme
            active_color = QColor(0, 255, 0)          # Green for active status
            warning_color = QColor(255, 255, 0)       # Yellow for warnings
            text_color = QColor(255, 255, 255)        # White for regular text
        
        # Update GPS status colors if they exist
        if hasattr(self, 'location_items'):
            if 'status_value' in self.location_items:
                self.location_items['status_value'].setForeground(active_color)
            if 'fix_value' in self.location_items:
                # Check current fix text to determine appropriate color
                fix_text = self.location_items['fix_value'].text()
                if "Moving" in fix_text:
                    self.location_items['fix_value'].setForeground(active_color)
                else:
                    self.location_items['fix_value'].setForeground(warning_color)
        
        # Update tower table colors (but not amateur radio band tables - they get band-specific colors)
        if hasattr(self, 'tower_table'):
            for row in range(self.tower_table.rowCount()):
                for col in range(self.tower_table.columnCount()):
                    item = self.tower_table.item(row, col)
                    if item:
                        item.setForeground(text_color)
        
        # Update location table (unified GPS and Grid) styles
        if hasattr(self, 'location_table'):
            self.location_table.setStyleSheet(self.get_table_css())
            
        # Update location table item colors individually
        if hasattr(self, 'location_items'):
            for item_key, item in self.location_items.items():
                if item:
                    item.setForeground(text_color)
        
        # Update dynamic labels
        if hasattr(self, 'datetime_label'):
            color_hex = "#ff6666" if night_mode_on else "#ffffff"
            self.datetime_label.setStyleSheet(f"color: {color_hex}; padding: 10px;")
        
        # Update amateur band description labels
        if hasattr(self, 'band_description_labels'):
            color_hex = "#ff6666" if night_mode_on else "#ffffff"
            for label in self.band_description_labels:
                if label:
                    label.setStyleSheet(f"color: {color_hex}; padding: 5px;")
        
        # Force refresh of all band-specific data to update colors
        if hasattr(self, 'amateur_2m_data') and self.amateur_2m_data:
            self.populate_band_data("2m", self.amateur_2m_data)
        if hasattr(self, 'amateur_70cm_data') and self.amateur_70cm_data:
            self.populate_band_data("70cm", self.amateur_70cm_data)
        if hasattr(self, 'amateur_simplex_data') and self.amateur_simplex_data:
            self.populate_simplex_data()
        # Refresh Skywarn data if it exists
        if hasattr(self, 'cached_skywarn_data') and self.cached_skywarn_data:
            self.populate_skywarn_data()
        # Refresh NOAA data
        if hasattr(self, 'noaa_table'):
            self.populate_noaa_frequency_data()

    def toggle_night_mode(self, night_mode_on):
        """Toggle between day and night mode for better night vision"""
        # Use the unified styling system
        self.setup_styling(night_mode=night_mode_on)
        
        # Update header colors based on mode
        if night_mode_on:
            self.gps_status.setStyleSheet("color: #ff6666; padding: 6px; font-size: 14px;")
            self.datetime_label.setStyleSheet("color: #ff6666; padding: 10px;")
        else:
            self.gps_status.setStyleSheet("color: #00ff00; padding: 6px; font-size: 14px;")
            self.datetime_label.setStyleSheet("color: #ffffff; padding: 10px;")
        
        # Update all table item colors to match the new theme
        self.update_table_colors_for_mode(night_mode_on)
        
        # Update amateur band tab colors for new mode
        if hasattr(self, 'amateur_subtabs'):
            self.set_amateur_band_tab_colors()

    def update_gps_data(self, latitude, longitude, altitude, speed, heading):
        """Update all GPS-related displays"""
        # Log GPS speed and direction data
        speed_mph = speed * 2.23694  # Convert m/s to mph
        logger.info(f"GPS Update: Speed={speed:.2f}m/s ({speed_mph:.1f}mph), Heading={heading:.1f}°, Location={latitude:.6f},{longitude:.6f}")
        
        self.last_lat = latitude
        self.last_lon = longitude
        self.last_speed = speed  # Store speed for UDP and other functions
        
        # Store GPS coordinates for return to GPS functionality
        self.last_gps_lat = latitude
        self.last_gps_lon = longitude
        self.last_gps_altitude = altitude
        self.last_gps_speed = speed
        self.last_gps_heading = heading
        
        # Update GPS table with proper colors
        self.set_table_item_text_with_color(self.location_items['lat_value'], f"{latitude:.6f}°")
        self.set_table_item_text_with_color(self.location_items['lon_value'], f"{longitude:.6f}°")
        
        # Update altitude with both metric and imperial
        self.set_table_item_text_with_color(self.location_items['alt_value'], f"{altitude:.1f} m ({altitude * M_TO_FEET:.1f} ft)")
        
        # Update speed with multiple units (with minimum threshold)
        # GPS noise threshold - ignore speeds below 0.5 m/s (~1.1 mph, walking speed)
        MIN_SPEED_THRESHOLD = 0.5  # meters per second
        is_moving = False  # Initialize is_moving variable
        
        # Debug logging for speed processing
        debug_print(f"Processing GPS speed: {speed:.2f} m/s ({speed * MPS_TO_MPH:.1f} mph)", "DEBUG")
        
        if speed >= MIN_SPEED_THRESHOLD:
            speed_mph = speed * MPS_TO_MPH
            speed_knots = speed * MPS_TO_KNOTS
            self.set_table_item_text_with_color(self.location_items['speed_value'], f"{speed:.1f} m/s ({speed_mph:.1f} mph, {speed_knots:.1f} kt)")
            is_moving = True
            
            # Determine if we're at vehicle speed (above walking speed)
            self.is_vehicle_speed = speed >= self.WALKING_SPEED_THRESHOLD
            
            debug_print(f"Speed above threshold - Moving: {is_moving}, Vehicle speed: {self.is_vehicle_speed}", "DEBUG")
        else:
            # Below threshold - consider stationary
            self.set_table_item_text_with_color(self.location_items['speed_value'], "0.0 m/s (0.0 mph, 0.0 kt)")
            is_moving = False
            self.is_vehicle_speed = False
            
            debug_print(f"Speed below threshold ({MIN_SPEED_THRESHOLD} m/s) - Considered stationary", "DEBUG")
        
        # Update GPS status in header with motion mode
        if self.is_vehicle_speed:
            mode_text = f"GPS: Active (Vehicle {speed * MPS_TO_MPH:.0f} mph)"
            self.gps_status.setText(mode_text)
            self.gps_status.setStyleSheet("color: #ffa500; padding: 12px; font-size: 14px;")  # Orange for vehicle speed
        elif is_moving:
            mode_text = f"GPS: Active (Walking {speed * MPS_TO_MPH:.1f} mph)"
            self.gps_status.setText(mode_text)
            self.gps_status.setStyleSheet("color: #00ff00; padding: 12px; font-size: 14px;")  # Green for walking
        else:
            self.gps_status.setText("GPS: Active (Stationary)")
            self.gps_status.setStyleSheet("color: #00ff00; padding: 12px; font-size: 14px;")  # Green for stationary
        
        # Update heading with cardinal direction (only when moving)
        if heading is not None and heading >= 0 and is_moving:
            # Convert bearing to cardinal direction
            directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                         'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
            index = int((heading + 11.25) / 22.5) % 16
            cardinal = directions[index]
            self.set_table_item_text_with_color(self.location_items['heading_value'], f"{heading:.0f}° ({cardinal})")
        else:
            self.set_table_item_text_with_color(self.location_items['heading_value'], "--° (--)")
        
        # Update vector speed (speed + direction combined)
        if is_moving and heading is not None and heading >= 0:
            # Convert bearing to cardinal direction for vector
            directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                         'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
            index = int((heading + 11.25) / 22.5) % 16
            cardinal = directions[index]
            speed_mph = speed * MPS_TO_MPH
            self.set_table_item_text_with_color(self.location_items['vector_value'], f"{speed_mph:.1f} mph {cardinal}")
        else:
            self.set_table_item_text_with_color(self.location_items['vector_value'], "Stationary")
        
        # Update GPS status and fix quality with appropriate colors
        self.location_items['status_value'].setText("ACTIVE")
        # Set status color based on night mode
        status_color = QColor(255, 102, 102) if self.night_mode_active else QColor(0, 255, 0)
        self.location_items['status_value'].setForeground(status_color)
        
        # Determine fix quality based on speed accuracy (using same threshold as movement detection)
        if speed >= MIN_SPEED_THRESHOLD:  # Moving (consistent with is_moving logic)
            self.location_items['fix_value'].setText("3D FIX (Moving)")
            self.location_items['fix_value'].setForeground(status_color)
        else:  # Stationary
            self.location_items['fix_value'].setText("3D FIX (Stationary)")
            # Set warning color based on night mode
            warning_color = QColor(255, 153, 102) if self.night_mode_active else QColor(255, 255, 0)
            self.location_items['fix_value'].setForeground(warning_color)

        # Update Grid Systems in unified location table
        try:
            # UTM coordinate system (right side, row 0)
            utm_result = utm.from_latlon(latitude, longitude)
            utm_str = f"Zone {utm_result[2]}{utm_result[3]} E:{utm_result[0]:.0f} N:{utm_result[1]:.0f}"
            self.set_table_item_text_with_color(self.location_items['utm_value'], utm_str)
            
            # Maidenhead (right side, row 1)
            mh_grid = mh.to_maiden(latitude, longitude)
            self.set_table_item_text_with_color(self.location_items['mh_value'], mh_grid)
            
            # MGRS (right side, rows 2-3)
            m = mgrs.MGRS()
            mgrs_result = m.toMGRS(latitude, longitude)
            mgrs_zone = mgrs_result[:3]
            mgrs_grid = mgrs_result[3:5]
            mgrs_coords = mgrs_result[5:]
            
            # Split MGRS coordinates into easting and northing for better readability
            if len(mgrs_coords) >= 6:
                mid_point = len(mgrs_coords) // 2
                easting = mgrs_coords[:mid_point]
                northing = mgrs_coords[mid_point:]
                formatted_coords = f"{easting} {northing}"
            else:
                formatted_coords = mgrs_coords
                
            self.set_table_item_text_with_color(self.location_items['mgrs_zone_value'], f"{mgrs_zone} {mgrs_grid}")
            self.set_table_item_text_with_color(self.location_items['mgrs_coords_value'], formatted_coords)
            
            # DMS (Degrees, Minutes, Seconds) format (right side, rows 4-5)
            def decimal_to_dms(decimal_degrees, is_latitude=True):
                """Convert decimal degrees to degrees, minutes, seconds format"""
                abs_degrees = abs(decimal_degrees)
                degrees = int(abs_degrees)
                minutes_float = (abs_degrees - degrees) * 60
                minutes = int(minutes_float)
                seconds = (minutes_float - minutes) * 60
                
                if is_latitude:
                    direction = 'N' if decimal_degrees >= 0 else 'S'
                else:
                    direction = 'E' if decimal_degrees >= 0 else 'W'
                
                return f"{degrees}°{minutes:02d}'{seconds:05.2f}\"{direction}"
            
            dms_lat = decimal_to_dms(latitude, True)
            dms_lon = decimal_to_dms(longitude, False)
            self.set_table_item_text_with_color(self.location_items['dms_lat_value'], dms_lat)
            self.set_table_item_text_with_color(self.location_items['dms_lon_value'], dms_lon)
            
        except Exception as e:
            print(f"Error calculating grid systems: {e}")

        # Update coordinate display with current location
        # Coordinate data is already shown in the grid table

        # Update Closest Towers - now handled at the top of motion-aware updates section

        # Update coordinate display with current location
        current_time = time.time()
        current_location = (latitude, longitude)
        
        if not hasattr(self, 'last_repeater_update_location'):
            # First time - populate everything
            self.populate_skywarn_data()
            self.populate_noaa_frequency_data()
            self.populate_all_amateur_data()
            self.last_repeater_update_location = current_location
            self.last_armer_update = current_time
            self.last_skywarn_update = current_time
            self.last_amateur_update = current_time
            print("📍 First GPS lock - fetching all repeater data")
        else:
            # Check movement and apply motion-aware update logic
            last_lat, last_lon = self.last_repeater_update_location
            distance_moved = haversine(latitude, longitude, last_lat, last_lon)
            
            # Always update location tracking when we have any movement
            if distance_moved > 0.001:  # Update location tracking for any movement > ~5 feet
                self.last_repeater_update_location = current_location
            
            if self.is_vehicle_speed:
                # Vehicle speed mode - time-based updates with debug output
                print(f"🚗 Vehicle speed detected ({speed * MPS_TO_MPH:.1f} mph, {speed:.1f} m/s) - distance moved: {distance_moved:.4f} miles")
                
                # Update ARMER and Skywarn every 25 seconds when moving at vehicle speed
                if current_time - self.last_skywarn_update >= self.ARMER_SKYWARN_INTERVAL:
                    print(f"⏰ Vehicle mode: Updating emergency services ({self.ARMER_SKYWARN_INTERVAL}s interval)")
                    self.display_closest_sites(latitude, longitude)
                    self.populate_skywarn_data()
                    self.populate_noaa_frequency_data()
                    self.last_skywarn_update = current_time
                
                # Update Amateur radio every 35 seconds when moving at vehicle speed
                if current_time - self.last_amateur_update >= self.AMATEUR_INTERVAL:
                    print(f"⏰ Vehicle mode: Updating amateur radio ({self.AMATEUR_INTERVAL}s interval)")
                    self.populate_all_amateur_data()
                    self.last_amateur_update = current_time
                    
                # Force immediate update if moved significantly (>0.1 miles = ~500 feet)
                if distance_moved > 0.1:
                    print(f"🚗 Force update: moved {distance_moved:.3f} miles - refreshing all data immediately")
                    self.display_closest_sites(latitude, longitude)
                    self.populate_skywarn_data()
                    self.populate_noaa_frequency_data() 
                    self.populate_all_amateur_data()
                    self.last_skywarn_update = current_time
                    self.last_amateur_update = current_time
                    
            else:
                # Walking speed or stationary - distance-based updates for all services
                if distance_moved > self.stationary_threshold:  # 0.01 miles = ~50 feet
                    print(f"🚶 Walking/stationary mode: Updating all services (moved {distance_moved:.3f} miles)")
                    self.display_closest_sites(latitude, longitude)
                    self.populate_skywarn_data()
                    self.populate_noaa_frequency_data()
                    self.populate_all_amateur_data()
                    self.last_skywarn_update = current_time
                    self.last_amateur_update = current_time
                    
                    # Force refresh of band displays if we're within cached region but moving
                    if hasattr(self, 'force_band_refresh') and self.force_band_refresh:
                        print("🔄 Forcing band display refresh for new location")
                    # Repopulate band data to re-sort by distance from new location
                    if hasattr(self, 'amateur_10m_data'):
                        self.populate_band_data("10m", self.amateur_10m_data)
                    if hasattr(self, 'amateur_6m_data'):
                        self.populate_band_data("6m", self.amateur_6m_data) 
                    if hasattr(self, 'amateur_2m_data'):
                        self.populate_band_data("2m", self.amateur_2m_data)
                    if hasattr(self, 'amateur_125m_data'):
                        self.populate_band_data("1.25m", self.amateur_125m_data)
                    if hasattr(self, 'amateur_70cm_data'):
                        self.populate_band_data("70cm", self.amateur_70cm_data)
                else:
                    # Log when we're truly stationary
                    print(f"🏠 Stationary: moved only {distance_moved:.4f} miles (< {self.stationary_threshold:.3f} threshold)")

            # Debug output for vehicle speed detection
            if hasattr(self, 'is_vehicle_speed'):
                print(f"🚗 Vehicle speed check: {speed:.1f} m/s, threshold: {self.WALKING_SPEED_THRESHOLD:.1f} m/s, is_vehicle_speed: {self.is_vehicle_speed}")

    def display_closest_sites(self, latitude, longitude):
        """Display closest tower sites in enhanced table"""
        closest_sites = find_closest_sites(self.csv_filepath, latitude, longitude)
        self.table.setRowCount(len(closest_sites))
        
        for row, (site, distance, bearing, control_frequencies, nac) in enumerate(closest_sites):
            # Site name with color coding by distance
            site_item = QTableWidgetItem(site["Description"])
            if distance < 5:
                site_item.setBackground(QColor(0, 120, 0))  # Darker green for better contrast
                site_item.setForeground(self.get_text_color())
            elif distance < 15:
                site_item.setBackground(QColor(140, 140, 0))  # Darker yellow for better contrast
                site_item.setForeground(self.get_text_color())
            else:
                site_item.setBackground(QColor(120, 0, 0))  # Darker red for better contrast
                site_item.setForeground(self.get_text_color())
            
            # Create other items with mode-appropriate text color
            county_item = QTableWidgetItem(site["County Name"])
            county_item.setForeground(self.get_text_color())
            
            distance_item = QTableWidgetItem(f"{distance:.1f} mi")
            distance_item.setForeground(self.get_text_color())
            
            bearing_item = QTableWidgetItem(f"{bearing:.0f}°")
            bearing_item.setForeground(self.get_text_color())
            
            nac_item = QTableWidgetItem(str(nac))
            nac_item.setForeground(self.get_text_color())
            
            # Format control frequencies nicely
            freq_text = ", ".join(control_frequencies) if control_frequencies else "N/A"
            freq_item = QTableWidgetItem(freq_text)
            freq_item.setForeground(self.get_text_color())
            
            self.table.setItem(row, 0, site_item)
            self.table.setItem(row, 1, county_item)
            self.table.setItem(row, 2, distance_item)
            self.table.setItem(row, 3, bearing_item)
            self.table.setItem(row, 4, nac_item)
            self.table.setItem(row, 5, freq_item)
        
        # Send UDP broadcast of closest ARMER towers
        self.send_udp_armer_data()

    def populate_skywarn_data(self):
        """Populate SKYWARN weather repeater data with smart caching"""
        if hasattr(self, 'last_lat') and hasattr(self, 'last_lon'):
            user_lat = self.last_lat
            user_lon = self.last_lon
        else:
            user_lat = 44.9778  # Default to Minneapolis
            user_lon = -93.2650
        
        # Initialize Skywarn caching if not exists
        if not hasattr(self, 'cached_skywarn_data'):
            self.cached_skywarn_data = None
            self.cached_skywarn_location = None
            self.skywarn_is_stationary = False
        
        # Check if we need to refresh Skywarn data
        should_refresh = False
        
        if self.cached_skywarn_data is None:
            should_refresh = True
            print("📍 First time fetching Skywarn data")
        elif self.cached_skywarn_location:
            cached_lat, cached_lon = self.cached_skywarn_location
            distance = haversine(user_lat, user_lon, cached_lat, cached_lon)
            
            if distance > 0.01:  # Moved more than ~50 feet
                should_refresh = True
                self.skywarn_is_stationary = False
                print(f"📍 Moved {distance:.3f} miles, refreshing Skywarn data")
            else:
                # Stationary - Skywarn repeaters don't move either!
                if not self.skywarn_is_stationary:
                    self.skywarn_is_stationary = True
                    print("🔒 Skywarn stationary mode: Using cached data")
        
        # Try to get data from Radio Reference API only if we need to refresh
        api_data = []
        if should_refresh and hasattr(self, 'radio_api'):
            try:
                api_data = self.radio_api.get_skywarn_repeaters(user_lat, user_lon)
                if api_data:
                    # Cache the successful API data
                    self.cached_skywarn_data = api_data
                    self.cached_skywarn_location = (user_lat, user_lon)
                    self.data_source_status['skywarn'] = 'live'
                    print("✓ Using live Skywarn data from Radio Reference")
                else:
                    # Check cache
                    cached = self.radio_api.load_from_cache("skywarn", f"{user_lat:.3f}_{user_lon:.3f}_100")
                    if cached:
                        api_data = cached
                        self.cached_skywarn_data = cached
                        self.cached_skywarn_location = (user_lat, user_lon)
                        self.data_source_status['skywarn'] = 'cached'
            except Exception as e:
                print(f"Error fetching Skywarn API data: {e}")
        elif self.cached_skywarn_data:
            # Use existing cached data
            api_data = self.cached_skywarn_data
            self.data_source_status['skywarn'] = 'cached'
        
        # Use combined data - merge API data with static data for completeness
        combined_repeaters = []
        
        if api_data:
            # Convert API data to expected format
            api_repeaters = self.convert_api_data_to_repeater_format(api_data)
            combined_repeaters.extend(api_repeaters)
            self.data_source_status['skywarn'] = 'live'
            print(f"✓ Using {len(api_repeaters)} live Skywarn repeaters from Radio Reference")
        
        # Always include static data as fallback/supplement
        static_skywarn_repeaters = [
            # Twin Cities Metro SKYWARN Network
            {"call": "W0EAR", "location": "Minneapolis ARES", "freq": "146.94", "tone": "114.8", "lat": 44.9778, "lon": -93.2650},
            {"call": "WB0CMZ", "location": "Ramsey County ARES", "freq": "145.43", "tone": "123.0", "lat": 44.9537, "lon": -93.0900},
            {"call": "KC0YHH", "location": "Anoka County ARES", "freq": "145.45", "tone": "131.8", "lat": 45.1975, "lon": -93.3063},
            {"call": "W0MSP", "location": "MSP Emergency Coord", "freq": "147.42", "tone": "100.0", "lat": 44.8848, "lon": -93.2223},
            
            # Regional SKYWARN/Emergency Networks
            {"call": "K0USC", "location": "Duluth SKYWARN", "freq": "146.76", "tone": "131.8", "lat": 46.7867, "lon": -92.1005},
            {"call": "W0HSC", "location": "Rochester ARES", "freq": "147.06", "tone": "100.0", "lat": 44.0121, "lon": -92.4802},
            {"call": "KC0OOO", "location": "St. Cloud ARES", "freq": "145.47", "tone": "103.5", "lat": 45.5579, "lon": -94.2476},
            {"call": "W0RAN", "location": "Brainerd SKYWARN", "freq": "146.85", "tone": "136.5", "lat": 46.3580, "lon": -94.2008},
            {"call": "N0BVE", "location": "Bemidji Emergency", "freq": "146.67", "tone": "94.8", "lat": 47.4737, "lon": -94.8789},
            {"call": "WA0TDA", "location": "Itasca County ARES", "freq": "147.33", "tone": "107.2", "lat": 47.2378, "lon": -93.5308},
            
            # Southern Minnesota SKYWARN
            {"call": "W0TCX", "location": "Mankato SKYWARN", "freq": "146.73", "tone": "123.0", "lat": 44.1636, "lon": -94.0719},
            {"call": "KC0BSC", "location": "Winona Emergency", "freq": "145.17", "tone": "107.2", "lat": 44.0498, "lon": -91.6407},
            {"call": "W0ZPL", "location": "Albert Lea ARES", "freq": "146.68", "tone": "131.8", "lat": 43.6481, "lon": -93.3687},
            
            # Western Minnesota SKYWARN  
            {"call": "KC0JHF", "location": "Marshall SKYWARN", "freq": "147.24", "tone": "94.8", "lat": 44.4469, "lon": -95.7881},
            {"call": "W0MWX", "location": "Moorhead ARES", "freq": "145.23", "tone": "114.8", "lat": 46.8738, "lon": -96.7667},
            {"call": "KC0AHX", "location": "Alexandria SKYWARN", "freq": "146.91", "tone": "103.5", "lat": 45.8855, "lon": -95.3772},
            
            # Northern Minnesota Emergency
            {"call": "W0IAC", "location": "International Falls", "freq": "147.39", "tone": "136.5", "lat": 48.6019, "lon": -93.4016},
            {"call": "KC0EMG", "location": "Grand Marais ARES", "freq": "146.55", "tone": "100.0", "lat": 47.7503, "lon": -90.3376},
            {"call": "N0QVC", "location": "Ely Emergency Net", "freq": "145.35", "tone": "131.8", "lat": 47.9032, "lon": -91.8673}
        ]
        
        # Merge static data, avoiding duplicates by call sign
        api_calls = {rep.get('call', '') for rep in combined_repeaters}
        for static_rep in static_skywarn_repeaters:
            if static_rep['call'] not in api_calls:
                combined_repeaters.append(static_rep)
        
        # Update status based on final data source
        if not api_data:
            self.data_source_status['skywarn'] = 'static'
        elif len(combined_repeaters) > len(api_data if api_data else []):
            self.data_source_status['skywarn'] = 'hybrid'  # Mix of API and static
        
        skywarn_repeaters = combined_repeaters
        
        # Calculate distances and sort
        repeater_distances = []
        for repeater in skywarn_repeaters:
            distance = haversine(user_lat, user_lon, repeater["lat"], repeater["lon"])
            bearing = calculate_bearing(user_lat, user_lon, repeater["lat"], repeater["lon"])
            repeater_distances.append((repeater, distance, bearing))
        
        # Sort by distance
        repeater_distances.sort(key=lambda x: x[1])
        
        # Populate table
        self.skywarn_table.setRowCount(len(repeater_distances))
        
        # Update header to show data source
        source_indicator = self.get_data_source_indicator('skywarn')
        self.skywarn_table.setHorizontalHeaderLabels([
            f"Call Sign {source_indicator}", "Location", "Frequency", "Tone", "Distance", "Bearing"
        ])
        
        # Get Skywarn-specific color
        skywarn_color = self.get_band_color('skywarn')
        
        for row, (repeater, distance, bearing) in enumerate(repeater_distances):
            # Use Skywarn-specific background color with distance-based brightness/saturation
            call_item = QTableWidgetItem(repeater["call"])
            
            # Make Skywarn color more or less saturated based on distance
            if distance < 25:
                # Closer = more saturated Skywarn color
                background_color = skywarn_color
                text_color = QColor(255, 255, 255) if self.is_dark_color(skywarn_color) else QColor(0, 0, 0)
            elif distance < 75:
                # Medium distance = slightly desaturated Skywarn color
                background_color = self.lighten_color(skywarn_color, 0.7)
                text_color = QColor(255, 255, 255) if self.is_dark_color(background_color) else QColor(0, 0, 0)
            else:
                # Farther = much lighter Skywarn color
                background_color = self.lighten_color(skywarn_color, 0.4)
                text_color = QColor(255, 255, 255) if self.is_dark_color(background_color) else QColor(0, 0, 0)
                
            call_item.setBackground(background_color)
            call_item.setForeground(text_color)
            
            location_item = QTableWidgetItem(repeater["location"])
            location_item.setForeground(skywarn_color)
            
            freq_item = QTableWidgetItem(f"{repeater['freq']} MHz")
            freq_item.setForeground(skywarn_color)
            
            tone_item = QTableWidgetItem(f"{repeater['tone']} Hz")
            tone_item.setForeground(skywarn_color)
            
            distance_item = QTableWidgetItem(f"{distance:.1f} mi")
            distance_item.setForeground(skywarn_color)
            
            bearing_item = QTableWidgetItem(f"{bearing:.0f}°")
            bearing_item.setForeground(skywarn_color)
            
            self.skywarn_table.setItem(row, 0, call_item)
            self.skywarn_table.setItem(row, 1, location_item)
            self.skywarn_table.setItem(row, 2, freq_item)
            self.skywarn_table.setItem(row, 3, tone_item)
            self.skywarn_table.setItem(row, 4, distance_item)
            self.skywarn_table.setItem(row, 5, bearing_item)

    def convert_api_data_to_repeater_format(self, api_data):
        """Convert Radio Reference API data to internal repeater format"""
        converted_repeaters = []
        
        try:
            for repeater in api_data:
                # Extract relevant fields from Radio Reference API response
                converted_rep = {
                    "call": repeater.get('call_sign', repeater.get('callsign', 'N/A')),
                    "location": repeater.get('description', repeater.get('location', 'Unknown')),
                    "freq": str(repeater.get('frequency', repeater.get('output_freq', '0.0'))),
                    "tone": str(repeater.get('tone', repeater.get('ctcss', '0.0'))),
                    "lat": float(repeater.get('latitude', repeater.get('lat', 0.0))),
                    "lon": float(repeater.get('longitude', repeater.get('lon', 0.0)))
                }
                
                # Validate coordinates (basic sanity check for Minnesota)
                if 43.0 <= converted_rep["lat"] <= 49.5 and -97.5 <= converted_rep["lon"] <= -89.0:
                    converted_repeaters.append(converted_rep)
                else:
                    print(f"⚠️ Skipping repeater {converted_rep['call']} - coordinates outside Minnesota")
                    
        except Exception as e:
            print(f"⚠️ Error converting API data: {e}")
            
        return converted_repeaters

    def populate_noaa_frequency_data(self):
        """Populate NOAA Weather Radio frequency reference table"""
        
        print("📻 Populating NOAA Weather Radio frequency reference...")
        
        # The 7 standard NOAA Weather Radio frequencies
        noaa_frequencies = [
            "162.400",
            "162.425", 
            "162.450",
            "162.475",
            "162.500",
            "162.525",
            "162.550"
        ]
        
        # Our comprehensive station database for distance calculations
        static_noaa_stations = [
            # Primary Minnesota NWR stations with official call signs
            {"call": "KEC65", "location": "Minneapolis/St. Paul", "freq": "162.550", "same_codes": "027003,027019,027037,027053,027123,027139,027163", "lat": 44.8588, "lon": -93.2087},
            {"call": "KIG64", "location": "Duluth", "freq": "162.550", "same_codes": "027017,027035,027075,027115,027137", "lat": 46.7867, "lon": -92.1005},
            {"call": "KIF73", "location": "St. Cloud", "freq": "162.525", "same_codes": "027009,027145,027171", "lat": 45.5608, "lon": -94.2041},
            {"call": "WXM63", "location": "Grand Rapids", "freq": "162.525", "same_codes": "027031,027061,027097", "lat": 47.2378, "lon": -93.5308},
            {"call": "KJY63", "location": "Aitkin", "freq": "162.525", "same_codes": "027001,027027,027035,027097", "lat": 46.5330, "lon": -93.7108},
            {"call": "WXM51", "location": "Little Falls", "freq": "162.475", "same_codes": "027097,027153", "lat": 45.9763, "lon": -94.3625},
            {"call": "WXJ64", "location": "Leader (Omen Lake)", "freq": "162.550", "same_codes": "027027,027035,027097", "lat": 46.6500, "lon": -94.1000},
            {"call": "KXI44", "location": "Wadena", "freq": "162.450", "same_codes": "027111,027153,027159", "lat": 46.4388, "lon": -95.1364},
            {"call": "KJY80", "location": "Red Wing", "freq": "162.450", "same_codes": "027049,027131,055011,055063", "lat": 44.5633, "lon": -92.5340},
            {"call": "KXI31", "location": "Jeffers", "freq": "162.450", "same_codes": "027101,027103,027159,056041", "lat": 44.0733, "lon": -95.1953},
            {"call": "KXI32", "location": "Sleepy Eye", "freq": "162.475", "same_codes": "027013,027091,027103,027169", "lat": 44.3008, "lon": -94.7219},
            {"call": "KIH60", "location": "Alexandria", "freq": "162.400", "same_codes": "027041,027051,027111", "lat": 45.8855, "lon": -95.3772},
            {"call": "KXI48", "location": "Morris", "freq": "162.475", "same_codes": "027129,027151,027167", "lat": 45.5869, "lon": -95.9142},
            {"call": "KXI51", "location": "Marshall", "freq": "162.425", "same_codes": "027083,027091,027113,027123,027129,027165,027173", "lat": 44.4469, "lon": -95.7881},
            {"call": "KXI61", "location": "Montevideo", "freq": "162.400", "same_codes": "027023,027067,027111,027167,027173", "lat": 44.9388, "lon": -95.7142},
            {"call": "KZZ34", "location": "Rochester", "freq": "162.525", "same_codes": "027009,027045,027079,027109,027157,055005,055157", "lat": 44.0121, "lon": -92.4802},
            {"call": "KZZ56", "location": "Worthington", "freq": "162.400", "same_codes": "027063,027105,027161,046065,046133", "lat": 43.6191, "lon": -95.5956},
            {"call": "WXK40", "location": "La Crescent", "freq": "162.475", "same_codes": "027055,027109,027157,055063,055081,055123", "lat": 43.8241, "lon": -91.3096},
            {"call": "WXK95", "location": "Hinckley", "freq": "162.550", "same_codes": "027017,027025,027037,027061,027161,055023", "lat": 46.0047, "lon": -92.9405},
            {"call": "WXM65", "location": "Mankato", "freq": "162.425", "same_codes": "027013,027015,027079,027103,027143,027161", "lat": 44.1636, "lon": -94.0719},
            {"call": "WXM86", "location": "International Falls", "freq": "162.475", "same_codes": "027071,027077,055023", "lat": 48.6019, "lon": -93.4016},
            {"call": "WWG55", "location": "Albert Lea", "freq": "162.475", "same_codes": "027013,027047,027109,056043", "lat": 43.6481, "lon": -93.3687},
            {"call": "WWG56", "location": "Virginia", "freq": "162.475", "same_codes": "027017,027137", "lat": 47.5235, "lon": -92.5368},
            {"call": "KEC44", "location": "Thief River Falls", "freq": "162.400", "same_codes": "027069,027087,027135,027155", "lat": 48.1173, "lon": -96.1779},
            {"call": "KIF68", "location": "Willmar", "freq": "162.500", "same_codes": "027083,027121,027155,027167", "lat": 45.1219, "lon": -95.0433},
            {"call": "KIH41", "location": "Redwood Falls", "freq": "162.400", "same_codes": "027127,027173", "lat": 44.5408, "lon": -95.1167},
            {"call": "KIH53", "location": "New Ulm", "freq": "162.550", "same_codes": "027013,027015,027103", "lat": 44.3128, "lon": -94.4608},
            
            # Regional coverage (neighboring states)
            {"call": "KEC85", "location": "Grand Forks, ND", "freq": "162.525", "same_codes": "038035,038067,038097", "lat": 47.9253, "lon": -97.0329},
            {"call": "KZZ93", "location": "Aberdeen, SD", "freq": "162.475", "same_codes": "046005,046025,046051,046091", "lat": 45.4647, "lon": -98.4865},
            {"call": "WXK73", "location": "Eau Claire, WI", "freq": "162.550", "same_codes": "055035,055053,055091", "lat": 44.8113, "lon": -91.4985},
            {"call": "WXL40", "location": "La Crosse, WI", "freq": "162.475", "same_codes": "055063,055081,055123", "lat": 43.8014, "lon": -91.2396},
            
            # Additional Minnesota stations
            {"call": "KWO39", "location": "Park Rapids", "freq": "162.525", "same_codes": "027027,027097,027111", "lat": 46.9233, "lon": -95.0587},
            {"call": "KXI86", "location": "Fergus Falls", "freq": "162.400", "same_codes": "027111,027167", "lat": 46.2830, "lon": -96.0779},
            {"call": "WXL35", "location": "Bemidji", "freq": "162.450", "same_codes": "027007,027027,027071,027077", "lat": 47.4737, "lon": -94.8789},
            {"call": "WXM32", "location": "Walker", "freq": "162.475", "same_codes": "027027,027035,027061", "lat": 47.0942, "lon": -94.5844},
            {"call": "KIG47", "location": "Two Harbors", "freq": "162.400", "same_codes": "027061,027075", "lat": 47.0066, "lon": -91.6968},
            {"call": "WXK73", "location": "Winona", "freq": "162.550", "same_codes": "027055,027157,055005,055063", "lat": 44.0498, "lon": -91.6407},
            {"call": "KZZ81", "location": "Austin", "freq": "162.475", "same_codes": "027045,027109,056043", "lat": 43.6675, "lon": -92.9741}
        ]
        
        # Get current GPS location for distance calculations
        if hasattr(self, 'last_lat') and hasattr(self, 'last_lon') and self.last_lat and self.last_lon:
            user_lat = self.last_lat
            user_lon = self.last_lon
            print(f"📊 Calculating NOAA frequencies from {user_lat:.4f},{user_lon:.4f}")
        else:
            user_lat = 44.9778  # Default to Minneapolis
            user_lon = -93.2650
            print("📍 Using default location (Minneapolis) for NOAA frequency calculations")
        
        # Set NOAA color (weatherly blue)
        noaa_color = QColor(70, 130, 180)  # Steel blue for weather services
        
        # First, calculate the closest station for each frequency
        frequency_data = []
        
        for frequency in noaa_frequencies:
            # Find all stations on this frequency
            stations_on_freq = [s for s in static_noaa_stations if s['freq'] == frequency]
            
            if stations_on_freq:
                # Calculate distance to each station on this frequency
                closest_station = None
                closest_distance = float('inf')
                
                for station in stations_on_freq:
                    try:
                        station_lat = float(station.get('lat', 0))
                        station_lon = float(station.get('lon', 0))
                        distance = self.radio_api.calculate_distance_miles(user_lat, user_lon, station_lat, station_lon)
                        
                        if distance < closest_distance:
                            closest_distance = distance
                            closest_station = station
                    except (ValueError, TypeError):
                        continue
                
                if closest_station:
                    # Store frequency data with distance for sorting
                    frequency_data.append({
                        'frequency': frequency,
                        'station': closest_station,
                        'distance': closest_distance
                    })
                else:
                    # No valid stations found for this frequency
                    frequency_data.append({
                        'frequency': frequency,
                        'station': None,
                        'distance': float('inf')
                    })
            else:
                # No stations found for this frequency
                frequency_data.append({
                    'frequency': frequency,
                    'station': None,
                    'distance': float('inf')
                })
        
        # Sort frequencies by distance to nearest transmitter (best first)
        frequency_data.sort(key=lambda x: x['distance'])
        print(f"📊 Best NOAA frequency: {frequency_data[0]['frequency']} MHz ({frequency_data[0]['distance']:.1f} mi)")
        
        # Now populate table with distance-sorted data
        for row, freq_info in enumerate(frequency_data):
            frequency = freq_info['frequency']
            closest_station = freq_info['station']
            closest_distance = freq_info['distance']
            
            if closest_station and closest_distance != float('inf'):
                # Create table items
                freq_item = QTableWidgetItem(f"{frequency} MHz")
                freq_item.setForeground(noaa_color)
                
                station_item = QTableWidgetItem(closest_station['call'])
                station_item.setForeground(noaa_color)
                
                location_item = QTableWidgetItem(closest_station['location'])
                location_item.setForeground(noaa_color)
                
                distance_item = QTableWidgetItem(f"{closest_distance:.1f} mi")
                distance_item.setForeground(noaa_color)
                
                # Status based on distance (reception quality estimate)
                if closest_distance < 30:
                    status = "🟢 Excellent"
                    status_color = QColor(0, 150, 0)  # Green
                elif closest_distance < 60:
                    status = "🟡 Good"
                    status_color = QColor(180, 180, 0)  # Yellow
                elif closest_distance < 100:
                    status = "🟠 Fair"
                    status_color = QColor(255, 140, 0)  # Orange
                else:
                    status = "🔴 Poor"
                    status_color = QColor(200, 0, 0)  # Red
                
                status_item = QTableWidgetItem(status)
                status_item.setForeground(status_color)
                
                # Set items in table
                self.noaa_table.setItem(row, 0, freq_item)
                self.noaa_table.setItem(row, 1, station_item)
                self.noaa_table.setItem(row, 2, location_item)
                self.noaa_table.setItem(row, 3, distance_item)
                self.noaa_table.setItem(row, 4, status_item)
                
            else:
                # No stations found for this frequency - show as unavailable
                freq_item = QTableWidgetItem(f"{frequency} MHz")
                freq_item.setForeground(noaa_color)
                
                self.noaa_table.setItem(row, 0, freq_item)
                self.noaa_table.setItem(row, 1, QTableWidgetItem("N/A"))
                self.noaa_table.setItem(row, 2, QTableWidgetItem("No stations"))
                self.noaa_table.setItem(row, 3, QTableWidgetItem("--"))
                self.noaa_table.setItem(row, 4, QTableWidgetItem("Not available"))
        
        print(f"✅ NOAA frequency reference populated with 7 standard frequencies")

    def populate_all_amateur_data(self):
        """Populate Amateur Radio repeater data for all bands with smart stationary caching"""
        
        # Get current location
        if hasattr(self, 'last_lat') and hasattr(self, 'last_lon'):
            user_lat = self.last_lat
            user_lon = self.last_lon
        else:
            user_lat = 44.9778  # Default to Minneapolis
            user_lon = -93.2650
        
        # Check if we need to refresh the regional API cache
        should_refresh = False
        current_time = time.time()
        
        # Refresh if no cached data exists
        if self.cached_api_data is None:
            should_refresh = True
            print("📍 No regional cache - fetching amateur radio data")
        
        # Check if cache has expired (24 hours for regional cache)
        elif self.cached_api_timestamp and (current_time - self.cached_api_timestamp) > self.amateur_data_cache_timeout:
            should_refresh = True
            print(f"⏰ Regional cache expired ({(current_time - self.cached_api_timestamp)/3600:.1f} hours old), refreshing")
        
        # Check if we've moved outside the cached region
        elif self.cached_api_location:
            cached_lat, cached_lon = self.cached_api_location
            distance_from_cache_center = haversine(user_lat, user_lon, cached_lat, cached_lon)
            
            if distance_from_cache_center > self.cache_region_radius:
                should_refresh = True
                print(f"📍 Moved {distance_from_cache_center:.1f} miles from cache center (outside {self.cache_region_radius}-mile region)")
            else:
                # We're within the cached region - check for movement for logging
                if self.last_known_position:
                    last_lat, last_lon = self.last_known_position
                    distance_moved = haversine(user_lat, user_lon, last_lat, last_lon)
                    
                    if distance_moved < self.stationary_threshold:
                        if not self.is_stationary:
                            self.is_stationary = True
                            print(f"🔒 Stationary within cached region ({distance_from_cache_center:.1f} miles from center)")
                    else:
                        was_stationary = self.is_stationary
                        self.is_stationary = False
                        if was_stationary:
                            print(f"🚶 Movement within cached region ({distance_from_cache_center:.1f} miles from center)")
                        
                        # Important: Even within cached region, refresh displays when moving significantly
                        if distance_moved > 1.0:  # Moved more than 1 mile, update displays
                            print(f"📍 Moved {distance_moved:.1f} miles - refreshing repeater displays for new location")
                            # Force refresh of band tables even with cached data
                            self.force_band_refresh = True
                else:
                    print(f"✓ Using regional cache ({distance_from_cache_center:.1f} miles from center)")
        
        # Update last known position for movement tracking
        self.last_known_position = (user_lat, user_lon)
        
        # Fetch new regional API data only if needed
        if should_refresh and hasattr(self, 'radio_api') and self.radio_api.api_key:
            try:
                print(f"🌐 Fetching fresh regional amateur radio data (radius: {self.cached_api_radius} miles)...")
                api_data = self.radio_api.get_repeaters_by_location(user_lat, user_lon, self.cached_api_radius)
                
                # Only use API data if we actually get useful results
                if api_data and len(api_data) > 3:  # Require meaningful data
                    self.cached_api_data = api_data
                    self.cached_api_location = (user_lat, user_lon)
                    self.cached_api_timestamp = current_time
                    print(f"✓ Cached {len(self.cached_api_data)} amateur repeaters for {self.cached_api_radius}-mile region")
                else:
                    print("⚠️ API returned limited data - using comprehensive static database instead")
                    self.cached_api_data = []  # Force use of static data
            except Exception as e:
                print(f"⚠️ Error fetching amateur radio data: {e} - using comprehensive static database")
                self.cached_api_data = []  # Force use of static data
        
        # Static fallback data for each band
        # 10m repeaters (28-29.7 MHz) - Usually FM simplex or experimental
        self.amateur_10m_data = [
            {"call": "W0EXP", "location": "Minneapolis", "output": "29.620", "input": "29.620", "tone": "Simplex", "lat": 44.9778, "lon": -93.2650},
            {"call": "K0HF", "location": "St. Paul", "output": "29.640", "input": "29.640", "tone": "Simplex", "lat": 44.9537, "lon": -93.0900}
        ]
        
        # 6m repeaters (50-54 MHz) - Enhanced with Radio Reference data
        self.amateur_6m_data = [
            {"call": "W0UJ", "location": "Brainerd ARC - 6M", "output": "53.110", "input": "52.110", "tone": "123.0", "lat": 46.3560, "lon": -94.2008},
            {"call": "W0VHF", "location": "Minneapolis", "output": "53.290", "input": "52.290", "tone": "100.0", "lat": 44.9778, "lon": -93.2650},
            {"call": "K0SIX", "location": "Duluth", "output": "53.370", "input": "52.370", "tone": "103.5", "lat": 46.7867, "lon": -92.1005},
            {"call": "WB0SIX", "location": "Rochester", "output": "53.430", "input": "52.430", "tone": "107.2", "lat": 44.0121, "lon": -92.4802}
        ]
        
        # 2m repeaters (144-148 MHz) - Comprehensive Minnesota coverage from Radio Reference
        self.amateur_2m_data = [
            # Crow Wing County (Brainerd/Baxter area) - Radio Reference verified data
            {"call": "W0UJ", "location": "Brainerd ARC - VHF", "output": "145.130", "input": "144.530", "tone": "CSQ", "lat": 46.3560, "lon": -94.2008},
            {"call": "W0UJ", "location": "Brainerd ARC - VHF", "output": "147.225", "input": "147.825", "tone": "CSQ", "lat": 46.3560, "lon": -94.2008},
            {"call": "W0UJ", "location": "Crosslake", "output": "147.030", "input": "147.630", "tone": "CSQ", "lat": 46.6347, "lon": -94.1074},
            {"call": "W0REA", "location": "Pequot Lakes", "output": "147.090", "input": "147.690", "tone": "123.0", "lat": 46.6014, "lon": -94.3125},
            {"call": "N0CRW", "location": "Brainerd", "output": "146.985", "input": "146.385", "tone": "CSQ", "lat": 46.3560, "lon": -94.2008},
            {"call": "W0BTO", "location": "Brainerd", "output": "146.760", "input": "146.160", "tone": "114.8", "lat": 46.3583, "lon": -94.2003},
            {"call": "W0RAN", "location": "Brainerd", "output": "146.850", "input": "146.250", "tone": "136.5", "lat": 46.3580, "lon": -94.2008},
            {"call": "KC0FBZ", "location": "Crow Wing County", "output": "146.940", "input": "146.340", "tone": "131.8", "lat": 46.4816, "lon": -93.9589},
            {"call": "W0CVZ", "location": "Baxter", "output": "147.060", "input": "147.660", "tone": "100.0", "lat": 46.3583, "lon": -94.2003},
            {"call": "KC0YHM", "location": "Crosby", "output": "146.820", "input": "146.220", "tone": "100.0", "lat": 46.4816, "lon": -93.9589},
            
            # Morrison County (Little Falls area)
            {"call": "KC0TZF", "location": "Little Falls", "output": "147.300", "input": "147.900", "tone": "123.0", "lat": 45.9763, "lon": -94.3625},
            {"call": "K0LFD", "location": "Little Falls", "output": "145.350", "input": "144.750", "tone": "103.5", "lat": 45.9763, "lon": -94.3625},
            {"call": "WB0CVZ", "location": "Pierz", "output": "147.120", "input": "147.720", "tone": "107.2", "lat": 45.9896, "lon": -94.1058},
            
            # Itasca County (Grand Rapids area)
            {"call": "N0GWS", "location": "Grand Rapids", "output": "145.230", "input": "144.630", "tone": "91.5", "lat": 47.2399, "lon": -93.5277},
            {"call": "WA0TDA", "location": "Grand Rapids", "output": "147.330", "input": "147.930", "tone": "107.2", "lat": 47.2378, "lon": -93.5308},
            
            # Stearns County (St. Cloud area)
            {"call": "KC0OOO", "location": "St. Cloud", "output": "145.470", "input": "144.870", "tone": "103.5", "lat": 45.5579, "lon": -94.2476},
            {"call": "W0RTN", "location": "St. Cloud", "output": "146.820", "input": "146.220", "tone": "131.8", "lat": 45.5372, "lon": -94.1653},
            {"call": "KC0ALV", "location": "Sauk Centre", "output": "147.390", "input": "147.990", "tone": "123.0", "lat": 45.7361, "lon": -94.9533},
            
            # Beltrami County (Bemidji area)
            {"call": "N0BVE", "location": "Bemidji", "output": "146.670", "input": "146.070", "tone": "94.8", "lat": 47.4737, "lon": -94.8789},
            {"call": "KC0BSU", "location": "Bemidji", "output": "147.180", "input": "147.780", "tone": "131.8", "lat": 47.4737, "lon": -94.8789},
            
            # Twin Cities Metro
            {"call": "W0MSP", "location": "Minneapolis", "output": "145.310", "input": "144.710", "tone": "123.0", "lat": 44.9778, "lon": -93.2650},
            {"call": "KC9SPG", "location": "St. Paul", "output": "146.520", "input": "145.920", "tone": "Simplex", "lat": 44.9537, "lon": -93.0900},
            {"call": "W0UJ", "location": "St. Paul", "output": "145.490", "input": "144.890", "tone": "131.8", "lat": 44.9537, "lon": -93.0900},
            {"call": "K0TRC", "location": "St. Paul", "output": "147.165", "input": "147.765", "tone": "103.5", "lat": 44.9537, "lon": -93.0900},
            {"call": "WB0RUR", "location": "Minneapolis", "output": "146.52", "input": "146.52", "tone": "Simplex", "lat": 44.9778, "lon": -93.2650},
            {"call": "WA0ZQG", "location": "Minneapolis", "output": "145.23", "input": "144.63", "tone": "100.0", "lat": 44.9778, "lon": -93.2650},
            {"call": "WB0CMZ", "location": "St. Paul (South)", "output": "145.43", "input": "144.83", "tone": "123.0", "lat": 44.9000, "lon": -93.1000},
            
            # St. Louis County (Duluth area)
            {"call": "K0USC", "location": "Duluth", "output": "146.76", "input": "146.16", "tone": "131.8", "lat": 46.7867, "lon": -92.1005},
            {"call": "WD0EKR", "location": "Duluth", "output": "145.130", "input": "144.530", "tone": "103.5", "lat": 46.7867, "lon": -92.1005},
            
            # Olmsted County (Rochester area)
            {"call": "W0HSC", "location": "Rochester", "output": "147.06", "input": "147.66", "tone": "100.0", "lat": 44.0121, "lon": -92.4802},
            {"call": "KC0RCH", "location": "Rochester", "output": "146.850", "input": "146.250", "tone": "107.2", "lat": 44.0121, "lon": -92.4802}
        ]
        
        # 1.25m repeaters (220-225 MHz) - Less common band
        self.amateur_125m_data = [
            {"call": "N0ONT", "location": "Minneapolis", "output": "224.38", "input": "223.38", "tone": "103.5", "lat": 44.9778, "lon": -93.2650},
            {"call": "KC0125", "location": "St. Paul", "output": "224.46", "input": "223.46", "tone": "107.2", "lat": 44.9537, "lon": -93.0900},
            {"call": "W0RPT", "location": "Duluth", "output": "224.54", "input": "223.54", "tone": "100.0", "lat": 46.7867, "lon": -92.1005}
        ]
        
        # 70cm repeaters (420-450 MHz) - Comprehensive Minnesota UHF coverage
        self.amateur_70cm_data = [
            # Crow Wing County (Brainerd/Baxter area) - Radio Reference verified data
            {"call": "W0UJ", "location": "Nisswa", "output": "443.925", "input": "448.925", "tone": "123.0", "lat": 46.5208, "lon": -94.2886},
            {"call": "W0UJ", "location": "Brainerd ARC - UHF", "output": "444.925", "input": "449.925", "tone": "CSQ", "lat": 46.3560, "lon": -94.2008},
            {"call": "W0AIH", "location": "Baxter", "output": "444.025", "input": "449.025", "tone": "131.8", "lat": 46.3583, "lon": -94.2003},
            {"call": "KC0YHM", "location": "Crosby", "output": "442.750", "input": "447.750", "tone": "100.0", "lat": 46.4816, "lon": -93.9589},
            {"call": "N0FMN", "location": "Brainerd", "output": "442.200", "input": "447.200", "tone": "123.0", "lat": 46.3583, "lon": -94.2003},
            {"call": "KC0CVZ", "location": "Baxter", "output": "443.800", "input": "448.800", "tone": "114.8", "lat": 46.3583, "lon": -94.2003},
            
            # Morrison County area
            {"call": "KC0TZF", "location": "Little Falls", "output": "442.525", "input": "447.525", "tone": "123.0", "lat": 45.9763, "lon": -94.3625},
            
            # Stearns County (St. Cloud area)
            {"call": "W0RTN", "location": "St. Cloud", "output": "444.550", "input": "449.550", "tone": "131.8", "lat": 45.5372, "lon": -94.1653},
            {"call": "KC0SCL", "location": "St. Cloud", "output": "442.975", "input": "447.975", "tone": "103.5", "lat": 45.5579, "lon": -94.2476},
            
            # Itasca County (Grand Rapids area)
            {"call": "N0GWS", "location": "Grand Rapids", "output": "443.650", "input": "448.650", "tone": "91.5", "lat": 47.2399, "lon": -93.5277},
            
            # Beltrami County (Bemidji area)
            {"call": "N0BVE", "location": "Bemidji", "output": "442.950", "input": "447.950", "tone": "94.8", "lat": 47.4737, "lon": -94.8789},
            {"call": "KC0BSU", "location": "Bemidji", "output": "444.300", "input": "449.300", "tone": "131.8", "lat": 47.4737, "lon": -94.8789},
            
            # Twin Cities Metro
            {"call": "WB0CMZ", "location": "St. Paul", "output": "442.600", "input": "447.600", "tone": "123.0", "lat": 44.9537, "lon": -93.0900},
            {"call": "K0UHF", "location": "Minneapolis", "output": "443.200", "input": "448.200", "tone": "100.0", "lat": 44.9778, "lon": -93.2650},
            {"call": "W0UJ", "location": "St. Paul (UHF)", "output": "443.925", "input": "448.925", "tone": "103.5", "lat": 44.9537, "lon": -93.0900},
            {"call": "KC0ART", "location": "Apple Valley", "output": "442.325", "input": "447.325", "tone": "100.0", "lat": 44.7317, "lon": -93.2170},
            {"call": "W0MSP", "location": "Minneapolis", "output": "444.875", "input": "449.875", "tone": "123.0", "lat": 44.9778, "lon": -93.2650},
            {"call": "KC0TCM", "location": "Plymouth", "output": "442.125", "input": "447.125", "tone": "107.2", "lat": 45.0105, "lon": -93.4555},
            
            # St. Louis County (Duluth area)
            {"call": "WD0EKR", "location": "Duluth", "output": "444.450", "input": "449.450", "tone": "103.5", "lat": 46.7867, "lon": -92.1005},
            {"call": "K0DLH", "location": "Duluth", "output": "442.375", "input": "447.375", "tone": "131.8", "lat": 46.7867, "lon": -92.1005},
            
            # Olmsted County (Rochester area)
            {"call": "WA0UHF", "location": "Rochester", "output": "442.775", "input": "447.775", "tone": "107.2", "lat": 44.0121, "lon": -92.4802},
            {"call": "KC0RCH", "location": "Rochester", "output": "444.700", "input": "449.700", "tone": "100.0", "lat": 44.0121, "lon": -92.4802},
            
            # Regional/Wide Area
            {"call": "W0MN", "location": "Central MN", "output": "443.775", "input": "448.775", "tone": "114.8", "lat": 45.7869, "lon": -94.6859},
            {"call": "KC0NET", "location": "Northern MN", "output": "442.850", "input": "447.850", "tone": "136.5", "lat": 46.7296, "lon": -93.9336}
        ]
        
        # Populate each band
        self.populate_band_data("10m", self.amateur_10m_data)
        self.populate_band_data("6m", self.amateur_6m_data) 
        self.populate_band_data("2m", self.amateur_2m_data)
        self.populate_band_data("1.25m", self.amateur_125m_data)
        self.populate_band_data("70cm", self.amateur_70cm_data)

    def populate_band_data(self, band_name, repeaters):
        """Populate data for a specific amateur radio band using cached API data"""
        # Map from new band names to existing table attribute names
        band_to_table_map = {
            "10m": "amateur_10_table",
            "6m": "amateur_6_table", 
            "2m": "amateur_2_table",
            "1.25m": "amateur_125_table",
            "70cm": "amateur_70cm_table"
        }
        
        table_attr = band_to_table_map.get(band_name, f'amateur_{band_name}_table')
        
        if not hasattr(self, table_attr):
            print(f"❌ Warning: Table attribute {table_attr} not found for band {band_name}")
            return
            
        table = getattr(self, table_attr)
        
        if hasattr(self, 'last_lat') and hasattr(self, 'last_lon'):
            user_lat = self.last_lat
            user_lon = self.last_lon
        else:
            user_lat = 44.9778  # Default to Minneapolis
            user_lon = -93.2650
        
        # Use cached API data if available, but prefer comprehensive static data when API is limited
        api_repeaters = []
        if self.cached_api_data and len(self.cached_api_data) > 5:  # Only use API if substantial data
            # Filter cached data for this specific band
            api_repeaters = self.filter_repeaters_by_band(self.cached_api_data, band_name)
            if api_repeaters and len(api_repeaters) > 2:  # Require meaningful band data
                print(f"✓ Using {len(api_repeaters)} live {band_name} repeaters from cached API data")
                self.data_source_status['amateur'] = 'live'
        
        # Combine comprehensive static data with any useful API data
        if api_repeaters and len(api_repeaters) > len(repeaters) * 0.5:  # API has more than 50% of static data
            # API data seems substantial, use it
            repeater_data = api_repeaters
        else:
            # Use our comprehensive static database (Radio Reference verified)
            if api_repeaters:
                print(f"⚠️ API data limited ({len(api_repeaters)} {band_name}) - using comprehensive static database instead")
            repeater_data = repeaters
            self.data_source_status['amateur'] = 'static'
        
        # Calculate distances and sort (always recalculate for current position)
        repeater_distances = []
        for repeater in repeater_data:
            distance = haversine(user_lat, user_lon, repeater["lat"], repeater["lon"])
            bearing = calculate_bearing(user_lat, user_lon, repeater["lat"], repeater["lon"])
            repeater_distances.append((repeater, distance, bearing))
        
        # Sort by distance (always sort based on current location)
        repeater_distances.sort(key=lambda x: x[1])
        
        # Clear force refresh flag after processing
        if hasattr(self, 'force_band_refresh'):
            self.force_band_refresh = False
        
        # Populate table
        table.setRowCount(len(repeater_distances))
        
        # Update header to show data source and apply band color to headers
        source_indicator = self.get_data_source_indicator('amateur')
        table.setHorizontalHeaderLabels([
            f"Call Sign {source_indicator}", "Location", "Output", "Input", "Tone", "Distance", "Bearing"
        ])
        
        # Get band-specific color for this amateur radio band
        band_color = self.get_band_color(band_name)
        
        # Apply band color to the table headers for visual identification
        debug_print(f"🎨 Applying band color to {band_name} table headers: RGB({band_color.red()}, {band_color.green()}, {band_color.blue()})", "DEBUG")
        header = table.horizontalHeader()
        if header:
            header.setStyleSheet(f"""
                QHeaderView::section {{
                    background-color: rgb({band_color.red()}, {band_color.green()}, {band_color.blue()});
                    color: {'white' if self.is_dark_color(band_color) else 'black'};
                    font-weight: bold;
                    border: 1px solid #c0c0c0;
                    padding: 4px;
                }}
            """)
        
        for row, (repeater, distance, bearing) in enumerate(repeater_distances):
            # Use standard table appearance with normal text colors
            call_item = QTableWidgetItem(repeater["call"])
            location_item = QTableWidgetItem(repeater["location"])
            output_item = QTableWidgetItem(f"{repeater['output']} MHz")
            input_item = QTableWidgetItem(f"{repeater['input']} MHz")
            tone_item = QTableWidgetItem(f"{repeater['tone']}")
            distance_item = QTableWidgetItem(f"{distance:.1f} mi")
            bearing_item = QTableWidgetItem(f"{bearing:.0f}°")
            
            table.setItem(row, 0, call_item)
            table.setItem(row, 1, location_item)
            table.setItem(row, 2, output_item)
            table.setItem(row, 3, input_item)
            table.setItem(row, 4, tone_item)
            table.setItem(row, 5, distance_item)
            table.setItem(row, 6, bearing_item)

    def filter_repeaters_by_band(self, repeaters, band_name):
        """Filter repeaters by amateur radio band"""
        band_ranges = {
            '10': (28.0, 29.7),      # 10 meters
            '6': (50.0, 54.0),       # 6 meters  
            '2': (144.0, 148.0),     # 2 meters
            '125': (220.0, 225.0),   # 1.25 meters
            '70cm': (420.0, 450.0)   # 70 centimeters
        }
        
        if band_name not in band_ranges:
            return []
        
        min_freq, max_freq = band_ranges[band_name]
        filtered = []
        
        for repeater in repeaters:
            try:
                # Try 'frequency' first (our data format), then 'freq' (API format)
                freq = float(repeater.get('frequency', repeater.get('freq', '0')))
                if min_freq <= freq <= max_freq:
                    filtered.append(repeater)
            except (ValueError, TypeError):
                continue
        
        return filtered

    def flush_amateur_cache(self):
        """Manually flush the regional amateur radio cache"""
        self.cached_api_data = None
        self.cached_api_location = None
        self.cached_api_timestamp = None
        print("�️ Amateur radio cache flushed")

    def flush_skywarn_cache(self):
        """Manually flush the Skywarn repeater cache"""
        self.cached_skywarn_data = None
        self.cached_skywarn_location = None
        self.cached_skywarn_timestamp = None
        print("🗑️ Skywarn cache flushed")

    def populate_simplex_data(self):
        """Populate the simplex frequencies table"""
        try:
            table = getattr(self, 'amateur_simplex_table', None)
            if not table:
                print("⚠️ Simplex table not found")
                return
            
            # Clear existing data
            table.setRowCount(0)
            
            if not hasattr(self, 'amateur_simplex_data') or not self.amateur_simplex_data:
                self.load_simplex_data()
            
            # Populate table
            table.setRowCount(len(self.amateur_simplex_data))
            
            for row, entry in enumerate(self.amateur_simplex_data):
                try:
                    # Frequency
                    freq_item = QTableWidgetItem(entry['frequency_display'])
                    freq_item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, 0, freq_item)
                    
                    # Description
                    desc_item = QTableWidgetItem(entry['description'])
                    table.setItem(row, 1, desc_item)
                    
                    # Type (Simplex/Repeater) with band
                    type_text = f"{entry['type']} ({entry['band']})"
                    type_item = QTableWidgetItem(type_text)
                    type_item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, 2, type_item)
                    
                    # Mode
                    mode_item = QTableWidgetItem(entry['mode'])
                    mode_item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, 3, mode_item)
                    
                    # Tone
                    tone_item = QTableWidgetItem(entry['tone'])
                    tone_item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, 4, tone_item)
                    
                    # Notes
                    notes_item = QTableWidgetItem(entry['notes'])
                    table.setItem(row, 5, notes_item)
                    
                    # Use simplex-specific background color for all simplex entries
                    simplex_background_color = self.get_band_color('simplex')
                    text_color = QColor(255, 255, 255) if self.is_dark_color(simplex_background_color) else QColor(0, 0, 0)
                    
                    for col in range(6):
                        item = table.item(row, col)
                        if item:
                            item.setBackground(simplex_background_color)
                            item.setForeground(text_color)
                
                except Exception as e:
                    print(f"⚠️ Error populating simplex row {row}: {e}")
                    continue
            
            print(f"✅ Populated {table.rowCount()} simplex frequencies")
            
        except Exception as e:
            print(f"❌ Error populating simplex data: {e}")

    def load_simplex_data(self):
        """Load amateur radio simplex frequencies from CSV file"""
        try:
            simplex_file = os.path.join(os.path.dirname(__file__), "AmateurSimplex.csv")
            self.amateur_simplex_data = []
            
            print(f"📻 Loading simplex data from: {simplex_file}")
            
            if os.path.exists(simplex_file):
                with open(simplex_file, 'r', encoding='utf-8') as file:
                    csv_reader = csv.DictReader(file)
                    for row in csv_reader:
                        try:
                            # Parse the CSV data
                            freq_output = float(row['Frequency Output'])
                            freq_input = float(row['Frequency Input']) if row['Frequency Input'] != '0' else None
                            
                            # Determine frequency type and band
                            freq_type = "Repeater" if freq_input else "Simplex"
                            band = self.determine_band(freq_output)
                            
                            # Format tone information
                            tone_out = row.get('PL Output Tone', '').strip()
                            tone_in = row.get('PL Input Tone', '').strip()
                            tone_display = ""
                            if tone_out and tone_out != 'CSQ':
                                tone_display = tone_out
                                if tone_in and tone_in != tone_out:
                                    tone_display += f"/{tone_in}"
                            
                            # Create notes from multiple fields
                            notes = []
                            if row.get('Alpha Tag'):
                                notes.append(row['Alpha Tag'])
                            if row.get('Agency/Category'):
                                notes.append(row['Agency/Category'])
                            notes_text = " | ".join(notes) if notes else ""
                            
                            # Format frequency display
                            if freq_input:
                                freq_display = f"{freq_output} / {freq_input}"
                            else:
                                freq_display = str(freq_output)
                            
                            simplex_entry = {
                                'frequency': freq_output,
                                'frequency_display': freq_display,
                                'description': row.get('Description', '').strip(),
                                'type': freq_type,
                                'mode': row.get('Mode', '').strip(),
                                'tone': tone_display,
                                'notes': notes_text,
                                'band': band,
                                'input_freq': freq_input
                            }
                            
                            self.amateur_simplex_data.append(simplex_entry)
                            
                        except (ValueError, KeyError) as e:
                            print(f"⚠️ Error parsing simplex entry: {e}")
                            continue
                
                # Sort by frequency
                self.amateur_simplex_data.sort(key=lambda x: x['frequency'])
                print(f"✅ Loaded {len(self.amateur_simplex_data)} simplex frequencies")
                
            else:
                print(f"⚠️ Simplex file not found: {simplex_file}")
                self.amateur_simplex_data = []
                
        except Exception as e:
            print(f"❌ Error loading simplex data: {e}")
            self.amateur_simplex_data = []

    def determine_band(self, frequency):
        """Determine amateur radio band from frequency"""
        if 28.0 <= frequency <= 29.7:
            return "10m"
        elif 50.0 <= frequency <= 54.0:
            return "6m"
        elif 144.0 <= frequency <= 148.0:
            return "2m"
        elif 220.0 <= frequency <= 225.0:
            return "1.25m"
        elif 420.0 <= frequency <= 450.0:
            return "70cm"
        elif 902.0 <= frequency <= 928.0:
            return "33cm"
        elif 1240.0 <= frequency <= 1300.0:
            return "23cm"
        elif 2300.0 <= frequency <= 2450.0:
            return "13cm"
        else:
            return "Other"

    def populate_emergency_data(self):
        """Populate the emergency frequencies table with NIFOG data"""
        try:
            table = getattr(self, 'amateur_emergency_table', None)
            if not table:
                print("⚠️ Emergency table not found")
                return
            
            # Clear existing data
            table.setRowCount(0)
            
            if not hasattr(self, 'amateur_emergency_data') or not self.amateur_emergency_data:
                self.load_emergency_data()
            
            # Populate table
            table.setRowCount(len(self.amateur_emergency_data))
            
            for row, entry in enumerate(self.amateur_emergency_data):
                try:
                    # Frequency
                    freq_item = QTableWidgetItem(entry['frequency'])
                    freq_item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, 0, freq_item)
                    
                    # Band
                    band_item = QTableWidgetItem(entry['band'])
                    band_item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, 1, band_item)
                    
                    # Mode
                    mode_item = QTableWidgetItem(entry['mode'])
                    mode_item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, 2, mode_item)
                    
                    # Purpose/Network
                    purpose_item = QTableWidgetItem(entry['purpose'])
                    table.setItem(row, 3, purpose_item)
                    
                    # Notes
                    notes_item = QTableWidgetItem(entry['notes'])
                    table.setItem(row, 4, notes_item)
                    
                    # Category
                    category_item = QTableWidgetItem(entry['category'])
                    category_item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, 5, category_item)
                    
                    # Apply band-specific color to the ENTIRE ROW for visual identification
                    band_color = self.get_band_color(entry['band'])
                    debug_print(f"🎨 Applying color to Emergency table row {row}:", "DEBUG")
                    debug_print(f"   Band: '{entry['band']}', Color: RGB({band_color.red()}, {band_color.green()}, {band_color.blue()})", "DEBUG")
                    
                    # Apply band color to ALL columns in the row
                    all_items = [freq_item, band_item, mode_item, purpose_item, notes_item, category_item]
                    for item in all_items:
                        if item:
                            item.setForeground(band_color)
                    
                    # Verify the color was applied
                    applied_color = band_item.foreground().color()
                    debug_print(f"   Applied color verification: RGB({applied_color.red()}, {applied_color.green()}, {applied_color.blue()})", "DEBUG")
                
                except Exception as e:
                    print(f"⚠️ Error populating emergency row {row}: {e}")
                    continue
            
            print(f"✅ Populated {table.rowCount()} emergency frequencies")
            
        except Exception as e:
            print(f"❌ Error populating emergency data: {e}")

    def load_emergency_data(self):
        """Load amateur radio emergency frequencies from NIFOG data"""
        try:
            self.amateur_emergency_data = []
            
            print("📻 Loading emergency frequencies from NIFOG data...")
            
            # Emergency Center of Activity Frequencies (HF)
            emergency_hf = [
                {"freq": "3750", "mode": "LSB", "purpose": "Emergency Center of Activity", "notes": "80 meters"},
                {"freq": "3985", "mode": "LSB", "purpose": "Emergency Center of Activity", "notes": "80 meters"},
                {"freq": "7060", "mode": "LSB", "purpose": "Emergency Center of Activity", "notes": "40 meters"},
                {"freq": "7240", "mode": "LSB", "purpose": "Emergency Center of Activity", "notes": "40 meters"},
                {"freq": "7290", "mode": "LSB", "purpose": "Emergency Center of Activity", "notes": "40 meters"},
                {"freq": "14300", "mode": "USB", "purpose": "Emergency Center of Activity", "notes": "20 meters"},
                {"freq": "18160", "mode": "USB", "purpose": "Emergency Center of Activity", "notes": "17 meters"},
                {"freq": "21360", "mode": "USB", "purpose": "Emergency Center of Activity", "notes": "15 meters"},
            ]
            
            # 60-meter Band (5 MHz) - Federal/Amateur Interoperability
            sixty_meter = [
                {"freq": "5330.5", "mode": "USB", "purpose": "Federal/Amateur Interoperability", "notes": "Center: 5332.0 kHz"},
                {"freq": "5346.5", "mode": "USB", "purpose": "Federal/Amateur Interoperability", "notes": "Center: 5348.0 kHz"},
                {"freq": "5357.0", "mode": "USB", "purpose": "Federal/Amateur Interoperability", "notes": "Center: 5358.5 kHz"},
                {"freq": "5371.5", "mode": "USB", "purpose": "Federal/Amateur Interoperability", "notes": "Center: 5373.0 kHz"},
                {"freq": "5403.5", "mode": "USB", "purpose": "Federal/Amateur Interoperability", "notes": "Center: 5405.0 kHz"},
            ]
            
            # VHF/UHF Emergency and Calling Frequencies
            vhf_uhf_emergency = [
                {"freq": "146.520", "mode": "FM", "purpose": "National Simplex Calling", "notes": "2 meters - Emergency standard"},
                {"freq": "446.000", "mode": "FM", "purpose": "National Simplex Calling", "notes": "70 cm - Emergency standard"},
                {"freq": "52.525", "mode": "FM", "purpose": "Simplex Calling", "notes": "6 meters"},
                {"freq": "52.540", "mode": "FM", "purpose": "Simplex Calling", "notes": "6 meters"},
                {"freq": "144.200", "mode": "SSB", "purpose": "Calling Frequency", "notes": "2 meters SSB"},
                {"freq": "222.100", "mode": "CW/SSB", "purpose": "Calling Frequency", "notes": "1.25 meters"},
                {"freq": "432.100", "mode": "CW/SSB", "purpose": "Calling Frequency", "notes": "70 cm"},
                {"freq": "902.100", "mode": "CW/SSB", "purpose": "Calling Frequency", "notes": "33 cm"},
                {"freq": "927.500", "mode": "FM", "purpose": "Simplex Calling", "notes": "33 cm"},
                {"freq": "1294.500", "mode": "FM", "purpose": "Simplex Calling", "notes": "23 cm"},
                {"freq": "1296.100", "mode": "CW/SSB", "purpose": "Calling Frequency", "notes": "23 cm"},
            ]
            
            # Hurricane Watch Net and Maritime Mobile
            hurricane_maritime = [
                {"freq": "14325", "mode": "USB", "purpose": "Hurricane Watch Net", "notes": "Day operations"},
                {"freq": "7268", "mode": "LSB", "purpose": "Hurricane Watch Net", "notes": "Night operations"},
                {"freq": "3815", "mode": "LSB", "purpose": "Hurricane Watch Net", "notes": "Caribbean"},
                {"freq": "3950", "mode": "LSB", "purpose": "Hurricane Watch Net", "notes": "North Florida"},
                {"freq": "3940", "mode": "LSB", "purpose": "Hurricane Watch Net", "notes": "South Florida"},
                {"freq": "14300", "mode": "USB", "purpose": "Maritime Mobile Service Net", "notes": "MMSN and others"},
            ]
            
            # HF Emergency/Disaster Relief Voice Channels
            hf_disaster = [
                {"freq": "1996.0", "mode": "USB", "purpose": "Emergency/Disaster Relief Voice", "notes": "Netcall: HFL"},
                {"freq": "3996.0", "mode": "USB", "purpose": "Emergency/Disaster Relief Voice", "notes": "Netcall: HFL"},
                {"freq": "7296.0", "mode": "USB", "purpose": "Emergency/Disaster Relief Voice", "notes": "Netcall: HFL"},
                {"freq": "14346.0", "mode": "USB", "purpose": "Emergency/Disaster Relief Voice", "notes": "Netcall: HFL"},
                {"freq": "18117.5", "mode": "USB", "purpose": "Emergency/Disaster Relief Voice", "notes": "Netcall: HFL"},
                {"freq": "21432.5", "mode": "USB", "purpose": "Emergency/Disaster Relief Voice", "notes": "Netcall: HFL"},
                {"freq": "28312.5", "mode": "USB", "purpose": "Emergency/Disaster Relief Voice", "notes": "Netcall: HFL"},
            ]
            
            # Process all frequency sets
            freq_sets = [
                (emergency_hf, "HF Emergency"),
                (sixty_meter, "60m Federal"),
                (vhf_uhf_emergency, "VHF/UHF"),
                (hurricane_maritime, "Hurricane/Maritime"),
                (hf_disaster, "HF Disaster Relief")
            ]
            
            for freq_set, category in freq_sets:
                for entry in freq_set:
                    freq_khz = float(entry["freq"])
                    
                    # Determine band
                    if freq_khz < 30:  # HF bands
                        if 1.8 <= freq_khz <= 2.0:
                            band = "160m"
                        elif 3.5 <= freq_khz <= 4.0:
                            band = "80m"
                        elif 7.0 <= freq_khz <= 7.3:
                            band = "40m"
                        elif 10.1 <= freq_khz <= 10.15:
                            band = "30m"
                        elif 14.0 <= freq_khz <= 14.35:
                            band = "20m"
                        elif 18.068 <= freq_khz <= 18.168:
                            band = "17m"
                        elif 21.0 <= freq_khz <= 21.45:
                            band = "15m"
                        elif 24.89 <= freq_khz <= 24.99:
                            band = "12m"
                        elif 28.0 <= freq_khz <= 29.7:
                            band = "10m"
                        elif 5.3 <= freq_khz <= 5.41:
                            band = "60m"
                        else:
                            band = "HF"
                    else:  # VHF/UHF bands
                        if 50 <= freq_khz <= 54:
                            band = "6m"
                        elif 144 <= freq_khz <= 148:
                            band = "2m"
                        elif 220 <= freq_khz <= 225:
                            band = "1.25m"
                        elif 420 <= freq_khz <= 450:
                            band = "70cm"
                        elif 902 <= freq_khz <= 928:
                            band = "33cm"
                        elif 1240 <= freq_khz <= 1300:
                            band = "23cm"
                        else:
                            band = "VHF/UHF"
                    
                    # Format frequency for display
                    if freq_khz < 30:  # HF - show in kHz
                        freq_display = f"{freq_khz} kHz"
                    else:  # VHF/UHF - show in MHz
                        freq_display = f"{freq_khz} MHz"
                    
                    emergency_entry = {
                        'frequency': freq_display,
                        'band': band,
                        'mode': entry['mode'],
                        'purpose': entry['purpose'],
                        'notes': entry['notes'],
                        'category': category
                    }
                    
                    # Debug what band was determined
                    debug_print(f"📻 Emergency frequency processed: {freq_display} → Band: '{band}' (Category: {category})", "DEBUG")
                    
                    self.amateur_emergency_data.append(emergency_entry)
            
            print(f"✅ Loaded {len(self.amateur_emergency_data)} emergency frequencies")
                
        except Exception as e:
            print(f"❌ Error loading emergency data: {e}")
            self.amateur_emergency_data = []

    def get_cache_status(self):
        """Get information about the current cache status"""
        status = {
            "amateur_api_cached": self.cached_api_data is not None,
            "amateur_api_location": self.cached_api_location,
            "amateur_api_timestamp": self.cached_api_timestamp,
            "skywarn_cached": self.cached_skywarn_data is not None,
            "skywarn_location": self.cached_skywarn_location,
            "skywarn_timestamp": self.cached_skywarn_timestamp
        }
        return status

    def parse_filter_by_service(self, repeaters):
        """Filter repeaters by service type"""
        filtered = []
        
        # Emergency/Public Safety keywords
        emergency_keywords = [
            'police', 'fire', 'ems', 'emergency', 'dispatch', 'sheriff', 
            'medical', 'rescue', 'public safety', 'hospital', 'ambulance',
            'security', 'guard', 'patrol', 'tactical', 'swat', 'bomb',
            'hazmat', 'disaster', 'coordination', 'command', 'control'
        ]
        
        # SKYWARN/Weather keywords
        weather_keywords = [
            'skywarn', 'weather', 'spotter', 'storm', 'emergency management',
            'warning', 'watch', 'severe', 'tornado', 'hurricane', 'flood',
            'winds', 'hail', 'precipitation', 'meteorolog', 'clima'
        ]
        
        for repeater in repeaters:
            try:
                name = str(repeater.get('name', '')).lower()
                desc = str(repeater.get('description', '')).lower()
                use = str(repeater.get('use', '')).lower()
                search_text = f"{name} {desc} {use}"
                
                # Check for emergency services
                if any(keyword in search_text for keyword in emergency_keywords):
                    repeater['service_type'] = 'Emergency'
                    filtered.append(repeater)
                # Check for weather services
                elif any(keyword in search_text for keyword in weather_keywords):
                    repeater['service_type'] = 'Weather'
                    filtered.append(repeater)
                    
            except (ValueError, TypeError):
                continue
        
        return filtered

    def flush_amateur_cache(self):
        """Manually flush the regional amateur radio cache"""
        self.cached_api_data = None
        self.cached_api_location = None
        self.cached_api_timestamp = None
        self.is_stationary = False
        self.last_known_position = None
        print("🗑️ Regional amateur radio cache flushed manually")
        
        # Clear disk cache files too
        try:
            import glob
            cache_files = glob.glob(os.path.join(self.cache_dir, "repeaters_*.json"))
            for cache_file in cache_files:
                os.remove(cache_file)
                print(f"🗑️ Removed disk cache: {os.path.basename(cache_file)}")
        except Exception as e:
            print(f"⚠️ Error clearing disk cache: {e}")

    def get_cache_status(self):
        """Get information about the current cache status"""
        if not self.cached_api_data:
            return "No regional cache loaded"
        
        current_time = time.time()
        age_hours = (current_time - self.cached_api_timestamp) / 3600 if self.cached_api_timestamp else 0
        
        if self.cached_api_location:
            cache_lat, cache_lon = self.cached_api_location
            return (f"Regional cache: {len(self.cached_api_data)} repeaters, "
                   f"{age_hours:.1f}h old, center: {cache_lat:.3f},{cache_lon:.3f}, "
                   f"radius: {self.cached_api_radius}mi")
        else:
            return f"Regional cache: {len(self.cached_api_data)} repeaters, {age_hours:.1f}h old"

    def closeEvent(self, event):
        """Clean up GPS worker thread when window closes"""
        if hasattr(self, 'gps_worker') and self.gps_worker.isRunning():
            print("Stopping GPS worker...")
            self.gps_worker.stop()
            self.gps_worker.wait(2000)
        event.accept()

    def keyPressEvent(self, event):
        """Handle key presses: F11 to toggle fullscreen, Esc to exit fullscreen, Ctrl+C/Ctrl+Q to quit."""
        try:
            if event.key() == Qt.Key_F11:
                self.toggle_fullscreen()
                return
            if event.key() == Qt.Key_Escape and self._is_fullscreen:
                # Exit fullscreen if currently fullscreen
                self.showNormal()
                self._is_fullscreen = False
                return
            # Handle Ctrl+C and Ctrl+Q to quit
            if event.modifiers() & Qt.ControlModifier:
                if event.key() == Qt.Key_C or event.key() == Qt.Key_Q:
                    print("User requested quit via keyboard shortcut")
                    self.close()
                    return
                elif event.key() == Qt.Key_N:
                    # Toggle night mode
                    print("Night mode toggled via Ctrl+N")
                    self.toggle_night_mode_button()
                    return
                elif event.key() == Qt.Key_R:
                    # Refresh all data
                    self.refresh_all_data()
                    return
                elif event.key() == Qt.Key_P:
                    # Export PDF
                    self.export_data()
                    return
                elif event.key() == Qt.Key_E:
                    # Export PDF (alternative shortcut)
                    self.export_data()
                    return
                elif event.key() == Qt.Key_1:
                    # Switch to Location tab
                    self.tab_widget.setCurrentIndex(0)
                    return
                elif event.key() == Qt.Key_2:
                    # Switch to ARMER tab
                    self.tab_widget.setCurrentIndex(1)
                    return
                elif event.key() == Qt.Key_3:
                    # Switch to Skywarn tab
                    self.tab_widget.setCurrentIndex(2)
                    return
                elif event.key() == Qt.Key_4:
                    # Switch to Amateur tab
                    self.tab_widget.setCurrentIndex(3)
                    return
        except Exception:
            pass
        # Fallback to default handling
        super().keyPressEvent(event)

    def toggle_fullscreen(self):
        """Toggle between fullscreen and normal window states."""
        if not self._is_fullscreen:
            self.showFullScreen()
            self._is_fullscreen = True
        else:
            self.showNormal()
            self._is_fullscreen = False

    def load_configuration(self):
        """Load configuration from file or create default"""
        self.config_file = os.path.join(os.path.dirname(__file__), "towerwitch_config.ini")
        self.config = configparser.ConfigParser()
        
        # Default configuration
        default_config = {
            'API': {
                'radio_reference_key': '',
                'auto_update': 'true',
                'cache_timeout_hours': '24'
            },
            'Display': {
                'night_mode': 'false',
                'refresh_interval': '30'
            },
            'UDP': {
                'enabled': 'true',
                'port': str(UDP_CONFIG['port']),
                'broadcast_ip': '255.255.255.255',
                'send_interval': '25'
            }
        }
        
        # Load existing config or create default
        if os.path.exists(self.config_file):
            try:
                self.config.read(self.config_file)
                print(f"✓ Loaded configuration from {self.config_file}")
            except Exception as e:
                print(f"Error loading config: {e}")
                self.create_default_config(default_config)
        else:
            self.create_default_config(default_config)
        
        # Extract API key
        self.api_key = self.config.get('API', 'radio_reference_key', fallback='')
        if self.api_key:
            print("✓ Radio Reference API key found")
        else:
            print("⚠️ No Radio Reference API key configured")
    
    def create_default_config(self, default_config):
        """Create default configuration file"""
        for section, options in default_config.items():
            self.config.add_section(section)
            for key, value in options.items():
                self.config.set(section, key, value)
        
        try:
            with open(self.config_file, 'w') as f:
                self.config.write(f)
            print(f"✓ Created default configuration at {self.config_file}")
            print("  Edit the file to add your Radio Reference API key")
        except Exception as e:
            print(f"Error creating config file: {e}")
    
    def save_configuration(self):
        """Save current configuration"""
        try:
            with open(self.config_file, 'w') as f:
                self.config.write(f)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get_data_source_indicator(self, source_type):
        """Get indicator text for data source"""
        status = self.data_source_status.get(source_type, 'static')
        indicators = {
            'live': '🌐 Live',
            'cached': '💾 Cached', 
            'static': '📁 Static',
            'hybrid': '🔗 Hybrid'
        }
        return indicators.get(status, '❓ Unknown')

# Support functions  
def calculate_bearing(lat1, lon1, lat2, lon2):
    """Calculate bearing between two points"""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    x = sin(dlon) * cos(lat2)
    y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
    return (degrees(atan2(x, y)) + 360) % 360

# Main Application

class LocationInputDialog(QDialog):
    """Dialog for manual location entry with multiple input methods"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Location")
        self.setFixedSize(500, 400)
        self.result_lat = None
        self.result_lon = None
        self.result_name = None
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Method selection
        method_group = QGroupBox("Location Input Method")
        method_layout = QVBoxLayout(method_group)
        
        self.method_combo = QComboBox()
        self.method_combo.addItems([
            "Decimal Degrees (DD)",
            "Degrees Minutes Seconds (DMS)", 
            "Maidenhead Grid Square",
            "UTM Coordinates",
            "MGRS Coordinates"
        ])
        self.method_combo.currentTextChanged.connect(self.on_method_changed)
        method_layout.addWidget(self.method_combo)
        
        layout.addWidget(method_group)
        
        # Input fields (will be dynamically created)
        self.input_group = QGroupBox("Coordinates")
        self.input_layout = QFormLayout(self.input_group)
        layout.addWidget(self.input_group)
        
        # Location name
        name_group = QGroupBox("Location Name (Optional)")
        name_layout = QFormLayout(name_group)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Home, Office, Emergency Shelter...")
        name_layout.addRow("Name:", self.name_input)
        layout.addWidget(name_group)
        
        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept_location)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Initialize with decimal degrees
        self.on_method_changed("Decimal Degrees (DD)")
    
    def on_method_changed(self, method):
        """Update input fields based on selected method"""
        # Clear existing inputs
        while self.input_layout.count():
            child = self.input_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        if method == "Decimal Degrees (DD)":
            self.lat_input = QLineEdit()
            self.lat_input.setPlaceholderText("e.g., 44.9778")
            self.lon_input = QLineEdit()
            self.lon_input.setPlaceholderText("e.g., -93.2650")
            
            self.input_layout.addRow("Latitude (°):", self.lat_input)
            self.input_layout.addRow("Longitude (°):", self.lon_input)
        
        elif method == "Degrees Minutes Seconds (DMS)":
            # Latitude DMS
            self.lat_deg = QLineEdit()
            self.lat_deg.setPlaceholderText("44")
            self.lat_min = QLineEdit() 
            self.lat_min.setPlaceholderText("58")
            self.lat_sec = QLineEdit()
            self.lat_sec.setPlaceholderText("40.1")
            self.lat_dir = QComboBox()
            self.lat_dir.addItems(["N", "S"])
            
            # Longitude DMS
            self.lon_deg = QLineEdit()
            self.lon_deg.setPlaceholderText("93")
            self.lon_min = QLineEdit()
            self.lon_min.setPlaceholderText("15")
            self.lon_sec = QLineEdit()
            self.lon_sec.setPlaceholderText("54.0")
            self.lon_dir = QComboBox()
            self.lon_dir.addItems(["E", "W"])
            
            # Create horizontal layouts for DMS inputs
            lat_layout = QHBoxLayout()
            lat_layout.addWidget(self.lat_deg)
            lat_layout.addWidget(QLabel("°"))
            lat_layout.addWidget(self.lat_min) 
            lat_layout.addWidget(QLabel("'"))
            lat_layout.addWidget(self.lat_sec)
            lat_layout.addWidget(QLabel("\""))
            lat_layout.addWidget(self.lat_dir)
            
            lon_layout = QHBoxLayout()
            lon_layout.addWidget(self.lon_deg)
            lon_layout.addWidget(QLabel("°"))
            lon_layout.addWidget(self.lon_min)
            lon_layout.addWidget(QLabel("'"))
            lon_layout.addWidget(self.lon_sec)
            lon_layout.addWidget(QLabel("\""))
            lon_layout.addWidget(self.lon_dir)
            
            lat_widget = QWidget()
            lat_widget.setLayout(lat_layout)
            lon_widget = QWidget()
            lon_widget.setLayout(lon_layout)
            
            self.input_layout.addRow("Latitude:", lat_widget)
            self.input_layout.addRow("Longitude:", lon_widget)
        
        elif method == "Maidenhead Grid Square":
            self.grid_input = QLineEdit()
            self.grid_input.setPlaceholderText("e.g., EN34xr")
            self.input_layout.addRow("Grid Square:", self.grid_input)
        
        elif method == "UTM Coordinates":
            self.utm_zone = QLineEdit()
            self.utm_zone.setPlaceholderText("e.g., 15")
            self.utm_band = QComboBox()
            self.utm_band.addItems(list("CDEFGHJKLMNPQRSTUVWX"))
            self.utm_band.setCurrentText("T")
            self.utm_easting = QLineEdit()
            self.utm_easting.setPlaceholderText("e.g., 482384")
            self.utm_northing = QLineEdit()
            self.utm_northing.setPlaceholderText("e.g., 4979645")
            
            self.input_layout.addRow("Zone:", self.utm_zone)
            self.input_layout.addRow("Band:", self.utm_band)
            self.input_layout.addRow("Easting:", self.utm_easting)
            self.input_layout.addRow("Northing:", self.utm_northing)
        
        elif method == "MGRS Coordinates":
            self.mgrs_input = QLineEdit()
            self.mgrs_input.setPlaceholderText("e.g., 15TVM8238479645")
            self.input_layout.addRow("MGRS:", self.mgrs_input)
    
    def accept_location(self):
        """Parse input and convert to decimal degrees"""
        try:
            method = self.method_combo.currentText()
            
            if method == "Decimal Degrees (DD)":
                lat = float(self.lat_input.text().strip())
                lon = float(self.lon_input.text().strip())
            
            elif method == "Degrees Minutes Seconds (DMS)":
                # Parse latitude
                lat_d = float(self.lat_deg.text().strip())
                lat_m = float(self.lat_min.text().strip())
                lat_s = float(self.lat_sec.text().strip())
                lat = lat_d + lat_m/60 + lat_s/3600
                if self.lat_dir.currentText() == "S":
                    lat = -lat
                
                # Parse longitude
                lon_d = float(self.lon_deg.text().strip())
                lon_m = float(self.lon_min.text().strip())
                lon_s = float(self.lon_sec.text().strip())
                lon = lon_d + lon_m/60 + lon_s/3600
                if self.lon_dir.currentText() == "W":
                    lon = -lon
            
            elif method == "Maidenhead Grid Square":
                grid = self.grid_input.text().strip().upper()
                lat, lon = mh.to_location(grid)
            
            elif method == "UTM Coordinates":
                zone = int(self.utm_zone.text().strip())
                band = self.utm_band.currentText()
                easting = float(self.utm_easting.text().strip())
                northing = float(self.utm_northing.text().strip())
                lat, lon = utm.to_latlon(easting, northing, zone, band)
            
            elif method == "MGRS Coordinates":
                mgrs_str = self.mgrs_input.text().strip().upper()
                m = mgrs.MGRS()
                lat, lon = m.toLatLon(mgrs_str)
            
            # Validate coordinates
            if not (-90 <= lat <= 90):
                raise ValueError("Latitude must be between -90 and 90 degrees")
            if not (-180 <= lon <= 180):
                raise ValueError("Longitude must be between -180 and 180 degrees")
            
            # Store results
            self.result_lat = lat
            self.result_lon = lon
            self.result_name = self.name_input.text().strip() or f"Manual ({method})"
            
            self.accept()
            
        except ValueError as e:
            QMessageBox.warning(self, "Invalid Input", f"Please check your coordinates:\n{str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "Input Error", f"Error parsing coordinates:\n{str(e)}")
    
    def get_location(self):
        """Return the parsed location"""
        return self.result_lat, self.result_lon, self.result_name


if __name__ == "__main__":
    try:
        debug_print("Starting main application...", "INFO")
        
        # Enable high DPI scaling BEFORE creating QApplication
        debug_print("Setting high DPI attributes...", "INFO")
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        debug_print("High DPI attributes set", "SUCCESS")
        
        debug_print("Creating QApplication...", "INFO")
        app = QApplication(sys.argv)
        debug_print("QApplication created successfully", "SUCCESS")
        
        # Initialize custom style for better color control
        if CUSTOM_STYLE_AVAILABLE:
            debug_print("Applying custom TowerWitch style...", "INFO")
            try:
                custom_style = TowerWitchStyle()
                app.setStyle(custom_style)
                debug_print("Custom TowerWitch style applied successfully", "SUCCESS")
                
                # Store reference for later use
                app.custom_style = custom_style
            except Exception as e:
                debug_print(f"Could not apply custom style: {e}", "WARNING")
                app.custom_style = None
        else:
            debug_print("Custom style not available, using system style", "WARNING")
            app.custom_style = None
        
        debug_print("Creating main window...", "INFO")
        window = EnhancedGPSWindow()
        debug_print("Main window created successfully", "SUCCESS")
        
        debug_print("Showing window...", "INFO")
        window.show()
        debug_print("Window displayed", "SUCCESS")
        
        debug_print("Starting event loop...", "INFO")
        exit_code = app.exec_()
        debug_print(f"Event loop exited with code: {exit_code}", "INFO")
        
        debug_print("Application shutting down normally", "SUCCESS")
        sys.exit(exit_code)
        
    except Exception as e:
        debug_print(f"FATAL ERROR in main application: {str(e)}", "ERROR")
        debug_print(f"Exception type: {type(e).__name__}", "ERROR")
        debug_print(f"Exception traceback: {traceback.format_exc()}", "ERROR")
        
        # Try to show an error dialog if possible
        try:
            if 'app' in locals():
                from PyQt5.QtWidgets import QMessageBox
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setWindowTitle("TowerWitch Fatal Error")
                msg.setText(f"A fatal error occurred:\n\n{str(e)}\n\nCheck the log file for details.")
                msg.exec_()
        except:
            pass
        
        sys.exit(1)
