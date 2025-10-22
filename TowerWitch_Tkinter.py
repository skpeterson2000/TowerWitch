#!/usr/bin/env python3
"""
TowerWitch - Enhanced GPS Tower Locator (Tkinter Version)
A comprehensive amateur radio repeater and emergency services tower locator
with GPS integration, multiple band support, and enhanced visual interface.

This tkinter version provides better control over styling and colored tabs.
"""

import tkinter as tk
from tkinter import ttk
import configparser
import os
import sys
import json
import csv
from datetime import datetime
from math import radians, cos, sin, asin, sqrt, atan2, degrees
import threading
import time
import subprocess

# Try to import GPS libraries
try:
    import gpsd
    GPS_AVAILABLE = True
except ImportError:
    GPS_AVAILABLE = False
    print("⚠️ GPS libraries not available - GPS functionality disabled")

class RadioReferenceAPI:
    """Simplified API class for Radio Reference data"""
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.cache_dir = os.path.join(os.path.expanduser("~"), ".towerwitch_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def get_skywarn_repeaters(self, lat, lon, radius=100):
        """Get Skywarn repeaters - using cached data for now"""
        return []
    
    def get_amateur_repeaters(self, lat, lon, radius=200):
        """Get amateur repeaters - using cached data for now"""
        return []
    
    def load_from_cache(self, data_type, location_key):
        """Load cached data"""
        cache_file = os.path.join(self.cache_dir, f"{data_type}_{location_key}.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return None

class GPSWorker:
    """Simple GPS worker for demonstration"""
    def __init__(self, callback):
        self.callback = callback
        self.running = False
        self.thread = None
    
    def start(self):
        """Start GPS monitoring"""
        self.running = True
        if GPS_AVAILABLE:
            self.thread = threading.Thread(target=self._gps_loop, daemon=True)
            self.thread.start()
        else:
            # Simulate GPS data for demo
            self.callback({
                'lat': 44.9778,
                'lon': -93.2650,
                'alt': 260.0,
                'time': datetime.now().isoformat(),
                'mode': 3,
                'satellites_used': 8
            })
    
    def _gps_loop(self):
        """GPS monitoring loop"""
        while self.running:
            try:
                # GPS implementation would go here
                time.sleep(1)
            except Exception as e:
                print(f"GPS error: {e}")
    
    def stop(self):
        """Stop GPS monitoring"""
        self.running = False

class TowerWitchTkinter:
    """Main application class using tkinter"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("TowerWitch - Enhanced GPS Tower Locator (Tkinter)")
        self.root.geometry("1024x600")
        
        # Configuration
        self.config_file = os.path.join(os.path.dirname(__file__), "towerwitch_config.ini")
        self.load_configuration()
        
        # Initialize APIs
        self.radio_api = RadioReferenceAPI(self.api_key)
        
        # GPS data
        self.last_lat = 44.9778  # Default Minneapolis
        self.last_lon = -93.2650
        self.gps_worker = None
        
        # Amateur radio data
        self.amateur_2m_data = []
        self.amateur_70cm_data = []
        self.amateur_simplex_data = []
        
        # Night mode state
        self.night_mode_on = False
        
        # Create the interface
        self.create_widgets()
        self.setup_colored_tabs()
        self.load_static_data()
        self.start_gps()
        
        # Update datetime
        self.update_datetime()
    
    def load_configuration(self):
        """Load configuration from INI file"""
        self.config = configparser.ConfigParser()
        
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)
            print(f"✓ Loaded configuration from {self.config_file}")
        else:
            # Create default config
            self.config['API'] = {
                'radio_reference_key': 'your_api_key_here',
                'force_refresh_cache': 'false'
            }
            self.config['GPS'] = {
                'update_interval': '5',
                'movement_threshold': '0.01'
            }
            
            with open(self.config_file, 'w') as f:
                self.config.write(f)
            print(f"✓ Created default configuration at {self.config_file}")
        
        # Get API key
        self.api_key = self.config.get('API', 'radio_reference_key', fallback=None)
        if self.api_key and self.api_key != 'your_api_key_here':
            print("✓ Radio Reference API key found")
        else:
            print("⚠️ No Radio Reference API key configured")
    
    def create_widgets(self):
        """Create the main interface widgets"""
        # Configure style for dark theme
        style = ttk.Style()
        style.theme_use('clam')  # Use clam theme as base
        
        # Configure dark theme colors
        style.configure('TLabel', background='#2b2b2b', foreground='#ffffff')
        style.configure('TFrame', background='#2b2b2b')
        style.configure('Treeview', background='#3b3b3b', foreground='#ffffff', 
                       fieldbackground='#3b3b3b')
        style.configure('Treeview.Heading', background='#4a4a4a', foreground='#ffffff')
        
        # Main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Header frame
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Title
        title_label = ttk.Label(header_frame, text="🗼 TowerWitch (Tkinter)", 
                               font=('Arial', 16, 'bold'))
        title_label.pack(side=tk.LEFT)
        
        # DateTime display
        self.datetime_label = ttk.Label(header_frame, text="", 
                                       font=('Arial', 12))
        self.datetime_label.pack(side=tk.RIGHT)
        
        # GPS status
        self.gps_status = ttk.Label(header_frame, text="GPS: Starting...", 
                                   font=('Arial', 10))
        self.gps_status.pack(side=tk.RIGHT, padx=(0, 20))
        
        # Control buttons frame
        controls_frame = ttk.Frame(main_frame)
        controls_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Night mode toggle
        self.night_mode_var = tk.BooleanVar()
        night_mode_btn = ttk.Checkbutton(controls_frame, text="Night Mode", 
                                        variable=self.night_mode_var,
                                        command=self.toggle_night_mode)
        night_mode_btn.pack(side=tk.LEFT)
        
        # Refresh button
        refresh_btn = ttk.Button(controls_frame, text="Refresh Data", 
                                command=self.refresh_all_data)
        refresh_btn.pack(side=tk.LEFT, padx=(10, 0))
        
        # Create main notebook (tabbed interface)
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Create tabs
        self.create_gps_tab()
        self.create_grid_tab()
        self.create_armer_tab()
        self.create_skywarn_tab()
        self.create_amateur_tab()
    
    def setup_colored_tabs(self):
        """Setup colored tabs using ttk.Style"""
        style = ttk.Style()
        
        # Configure the main notebook tab style with colors
        style.configure("TNotebook.Tab", 
                       padding=[12, 8],
                       focuscolor='none')
        
        # Map different colors based on tab state
        style.map("TNotebook.Tab",
                 background=[('selected', '#3498DB'), ('active', '#5DADE2')],
                 foreground=[('selected', '#ffffff'), ('active', '#ffffff')])
        
        print("🎨 Base tab styles configured!")
    
    def apply_tab_colors(self):
        """Apply colors using tkinter's Frame-based approach"""
        # Since ttk tab styling is limited, let's use a simpler visual approach
        # with colored frames and better organization
        print("🎨 Tkinter tab coloring - using improved visual organization")
        
        # Update tab text with better colored indicators
        self.update_tab_indicators()
    
    def update_tab_indicators(self):
        """Update tab text with clear colored emoji indicators"""
        try:
            # Main tabs with clear color coding
            main_tabs = [
                ("🟣 GPS", "GPS Data"),
                ("🟢 Grids", "Grid Systems"), 
                ("🔴 ARMER", "ARMER Sites"),
                ("🟠 Skywarn", "Weather Emergency"),
                ("🔵 Amateur", "Amateur Radio")
            ]
            
            # Update main tab labels
            for i, (colored_text, tooltip) in enumerate(main_tabs):
                if i < self.notebook.index("end"):
                    self.notebook.tab(i, text=colored_text)
                    print(f"✅ Updated main tab {i}: {colored_text}")
            
            # Update amateur sub-tabs  
            amateur_tabs = [
                "🔴 10m Band",
                "🟡 6m Band", 
                "🔵 2m Band",
                "🟢 1.25m Band",
                "🟠 70cm Band",
                "🟪 Simplex"
            ]
            
            for i, tab_text in enumerate(amateur_tabs):
                if i < self.amateur_notebook.index("end"):
                    self.amateur_notebook.tab(i, text=tab_text)
                    print(f"✅ Updated amateur tab {i}: {tab_text}")
                    
        except Exception as e:
            print(f"⚠️ Error updating tab indicators: {e}")
    
    def create_gps_tab(self):
        """Create GPS data tab"""
        gps_frame = ttk.Frame(self.notebook)
        self.notebook.add(gps_frame, text="🟣 GPS")
        
        # GPS info label
        info_label = ttk.Label(gps_frame, text="GPS Location and Status Information", 
                              font=('Arial', 12, 'bold'))
        info_label.pack(pady=10)
        
        # GPS data tree
        columns = ('Property', 'Value', 'Unit')
        self.gps_tree = ttk.Treeview(gps_frame, columns=columns, show='headings', height=10)
        
        # Define column headings and widths
        for col in columns:
            self.gps_tree.heading(col, text=col)
            self.gps_tree.column(col, width=200)
        
        # Add scrollbar
        gps_scroll = ttk.Scrollbar(gps_frame, orient=tk.VERTICAL, command=self.gps_tree.yview)
        self.gps_tree.configure(yscrollcommand=gps_scroll.set)
        
        # Pack GPS tree and scrollbar
        self.gps_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 0))
        gps_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Initialize GPS data
        self.update_gps_display()
    
    def create_grid_tab(self):
        """Create grid systems tab"""
        grid_frame = ttk.Frame(self.notebook)
        self.notebook.add(grid_frame, text="🟢 Grids")
        
        info_label = ttk.Label(grid_frame, text="Maidenhead Grid and UTM Coordinates", 
                              font=('Arial', 12, 'bold'))
        info_label.pack(pady=10)
        
        # Grid data will be added here
        grid_info = ttk.Label(grid_frame, text="Grid system information will be displayed here")
        grid_info.pack(pady=20)
    
    def create_armer_tab(self):
        """Create ARMER tab"""
        armer_frame = ttk.Frame(self.notebook)
        self.notebook.add(armer_frame, text="🔴 ARMER")
        
        info_label = ttk.Label(armer_frame, text="ARMER Radio Sites and Talkgroups", 
                              font=('Arial', 12, 'bold'))
        info_label.pack(pady=10)
        
        # ARMER data will be added here
        armer_info = ttk.Label(armer_frame, text="ARMER site information will be displayed here")
        armer_info.pack(pady=20)
    
    def create_skywarn_tab(self):
        """Create Skywarn tab"""
        skywarn_frame = ttk.Frame(self.notebook)
        self.notebook.add(skywarn_frame, text="🟠 Skywarn")
        
        info_label = ttk.Label(skywarn_frame, text="Skywarn Weather Emergency Repeaters", 
                              font=('Arial', 12, 'bold'))
        info_label.pack(pady=10)
        
        # Skywarn data tree
        columns = ('Call Sign', 'Location', 'Frequency', 'Tone', 'Distance', 'Bearing')
        self.skywarn_tree = ttk.Treeview(skywarn_frame, columns=columns, show='headings', height=15)
        
        for col in columns:
            self.skywarn_tree.heading(col, text=col)
            width = 150 if col in ['Call Sign', 'Frequency'] else 200
            self.skywarn_tree.column(col, width=width)
        
        self.skywarn_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Load Skywarn data
        self.load_skywarn_data()
    
    def create_amateur_tab(self):
        """Create amateur radio tab with sub-tabs for different bands"""
        amateur_frame = ttk.Frame(self.notebook)
        self.notebook.add(amateur_frame, text="🔵 Amateur")
        
        # Create sub-notebook for amateur bands
        self.amateur_notebook = ttk.Notebook(amateur_frame)
        self.amateur_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create band tabs with colored indicators
        self.create_band_tab("🔴 10m", "10 Meters (28-29.7 MHz)")
        self.create_band_tab("🟡 6m", "6 Meters (50-54 MHz)")
        self.create_band_tab("🔵 2m", "2 Meters (144-148 MHz)")
        self.create_band_tab("🟢 1.25m", "1.25 Meters (220-225 MHz)")
        self.create_band_tab("🟠 70cm", "70 Centimeters (420-450 MHz)")
        self.create_band_tab("🟪 Simplex", "Simplex & Special Frequencies")
    
    def create_band_tab(self, tab_name, description):
        """Create a tab for a specific amateur radio band"""
        band_frame = ttk.Frame(self.amateur_notebook)
        self.amateur_notebook.add(band_frame, text=tab_name)
        
        # Band description
        desc_label = ttk.Label(band_frame, text=description, 
                              font=('Arial', 12, 'bold'))
        desc_label.pack(pady=10)
        
        # Band data tree
        columns = ('Call Sign', 'Location', 'Output', 'Input', 'Tone', 'Distance', 'Bearing')
        band_tree = ttk.Treeview(band_frame, columns=columns, show='headings', height=12)
        
        for col in columns:
            band_tree.heading(col, text=col)
            width = 120 if col in ['Call Sign', 'Output', 'Input', 'Tone'] else 150
            band_tree.column(col, width=width)
        
        band_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Store tree reference for data population - fix naming
        band_clean = tab_name.split(' ', 1)[1]  # Remove emoji
        # Handle special cases for proper attribute names
        if band_clean == "1.25m":
            attr_name = "amateur_125m_tree"
        elif band_clean == "70cm":
            attr_name = "amateur_70cm_tree"
        else:
            attr_name = f'amateur_{band_clean.replace(".", "").lower()}_tree'
        
        setattr(self, attr_name, band_tree)
        print(f"📻 Created tree attribute: {attr_name}")
    
    def load_static_data(self):
        """Load static repeater and frequency data"""
        print("📻 Loading static amateur radio data...")
        
        # Load Skywarn data
        self.load_skywarn_data()
        
        # Load amateur band data
        self.load_amateur_data()
        
        # Load simplex data
        self.load_simplex_data()
    
    def load_skywarn_data(self):
        """Load Skywarn repeater data"""
        skywarn_repeaters = [
            {"call": "W0EAR", "location": "Minneapolis ARES", "freq": "146.94", "tone": "114.8", "lat": 44.9778, "lon": -93.2650},
            {"call": "WB0CMZ", "location": "Ramsey County ARES", "freq": "145.43", "tone": "123.0", "lat": 44.9537, "lon": -93.0900},
            {"call": "KC0YHH", "location": "Anoka County ARES", "freq": "145.45", "tone": "131.8", "lat": 45.1975, "lon": -93.3063},
            {"call": "W0MSP", "location": "MSP Emergency Coord", "freq": "147.42", "tone": "100.0", "lat": 44.8848, "lon": -93.2223},
            {"call": "K0USC", "location": "Duluth SKYWARN", "freq": "146.76", "tone": "131.8", "lat": 46.7867, "lon": -92.1005},
        ]
        
        # Clear existing data
        for item in self.skywarn_tree.get_children():
            self.skywarn_tree.delete(item)
        
        # Populate tree with distance calculations
        for repeater in skywarn_repeaters:
            distance = self.calculate_distance(self.last_lat, self.last_lon, 
                                             repeater["lat"], repeater["lon"])
            bearing = self.calculate_bearing(self.last_lat, self.last_lon, 
                                           repeater["lat"], repeater["lon"])
            
            values = (
                repeater["call"],
                repeater["location"],
                f"{repeater['freq']} MHz",
                f"{repeater['tone']} Hz",
                f"{distance:.1f} mi",
                f"{bearing:.0f}°"
            )
            
            item = self.skywarn_tree.insert('', 'end', values=values)
            
            # Color code by distance
            if distance < 25:
                self.skywarn_tree.set(item, 'Call Sign', f"🟢 {repeater['call']}")
            elif distance < 75:
                self.skywarn_tree.set(item, 'Call Sign', f"🟡 {repeater['call']}")
            else:
                self.skywarn_tree.set(item, 'Call Sign', f"🔴 {repeater['call']}")
    
    def load_amateur_data(self):
        """Load amateur radio repeater data"""
        # Sample 2m repeaters
        repeaters_2m = [
            {"call": "W0AIH", "location": "Minneapolis", "output": "146.94", "input": "146.34", "tone": "114.8", "lat": 44.9778, "lon": -93.2650},
            {"call": "K0TB", "location": "St. Paul", "output": "145.23", "input": "144.63", "tone": "107.2", "lat": 44.9537, "lon": -93.0900},
            {"call": "WA0TDA", "location": "Bloomington", "output": "147.06", "input": "147.66", "tone": "103.5", "lat": 44.8408, "lon": -93.2985},
        ]
        
        # Sample 70cm repeaters  
        repeaters_70cm = [
            {"call": "W0AIH", "location": "Minneapolis", "output": "442.20", "input": "447.20", "tone": "114.8", "lat": 44.9778, "lon": -93.2650},
            {"call": "K0TB", "location": "St. Paul", "output": "444.85", "input": "449.85", "tone": "107.2", "lat": 44.9537, "lon": -93.0900},
        ]
        
        # Populate band trees with correct band identifiers
        self.populate_band_tree(repeaters_2m, '2m')
        self.populate_band_tree(repeaters_70cm, '70cm')
    
    def populate_band_tree(self, repeaters, band):
        """Populate a specific band tree with repeater data"""
        # Fix band naming to match our attribute names
        if band == "125m":
            tree_name = 'amateur_125m_tree' 
        elif band == "70cm":
            tree_name = 'amateur_70cm_tree'
        else:
            tree_name = f'amateur_{band}_tree'
            
        if hasattr(self, tree_name):
            tree = getattr(self, tree_name)
            
            # Clear existing data
            for item in tree.get_children():
                tree.delete(item)
            
            # Populate with repeater data
            for repeater in repeaters:
                distance = self.calculate_distance(self.last_lat, self.last_lon,
                                                 repeater["lat"], repeater["lon"])
                bearing = self.calculate_bearing(self.last_lat, self.last_lon,
                                               repeater["lat"], repeater["lon"])
                
                values = (
                    repeater["call"],
                    repeater["location"],
                    f"{repeater['output']} MHz",
                    f"{repeater['input']} MHz", 
                    f"{repeater['tone']} Hz",
                    f"{distance:.1f} mi",
                    f"{bearing:.0f}°"
                )
                
                tree.insert('', 'end', values=values)
            print(f"📻 Populated {tree_name} with {len(repeaters)} repeaters")
        else:
            print(f"⚠️ Tree {tree_name} not found for band {band}")
    
    def load_simplex_data(self):
        """Load simplex frequency data"""
        simplex_file = os.path.join(os.path.dirname(__file__), "AmateurSimplex.csv")
        if os.path.exists(simplex_file):
            try:
                with open(simplex_file, 'r') as f:
                    reader = csv.DictReader(f)
                    self.amateur_simplex_data = list(reader)
                print(f"✅ Loaded {len(self.amateur_simplex_data)} simplex frequencies")
            except Exception as e:
                print(f"⚠️ Error loading simplex data: {e}")
                self.amateur_simplex_data = []
        
        # Populate simplex tree if it exists
        if hasattr(self, 'amateur_simplex_tree'):
            self.populate_simplex_tree()
    
    def populate_simplex_tree(self):
        """Populate simplex frequency tree"""
        tree = self.amateur_simplex_tree
        
        # Clear existing data
        for item in tree.get_children():
            tree.delete(item)
        
        # Add simplex frequencies
        for entry in self.amateur_simplex_data:
            values = (
                entry.get('frequency_display', ''),
                entry.get('description', ''),
                entry.get('type', ''),
                entry.get('mode', ''),
                entry.get('tone', ''),
                '',  # Distance - not applicable for simplex
                ''   # Bearing - not applicable for simplex
            )
            tree.insert('', 'end', values=values)
    
    def calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two points using haversine formula"""
        R = 3959  # Earth radius in miles
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        return R * c
    
    def calculate_bearing(self, lat1, lon1, lat2, lon2):
        """Calculate bearing from point 1 to point 2"""
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlon = lon2 - lon1
        y = sin(dlon) * cos(lat2)
        x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
        bearing = atan2(y, x)
        return (degrees(bearing) + 360) % 360
    
    def start_gps(self):
        """Start GPS monitoring"""
        print("✓ GPS Worker started")
        self.gps_worker = GPSWorker(self.on_gps_update)
        self.gps_worker.start()
    
    def on_gps_update(self, gps_data):
        """Handle GPS data updates"""
        if gps_data:
            self.last_lat = gps_data.get('lat', self.last_lat)
            self.last_lon = gps_data.get('lon', self.last_lon)
            
            # Update GPS display
            self.update_gps_display(gps_data)
            
            # Update status
            self.gps_status.config(text=f"GPS: {gps_data.get('mode', 0)}D Fix")
    
    def update_gps_display(self, gps_data=None):
        """Update GPS data display"""
        if not gps_data:
            gps_data = {
                'lat': self.last_lat,
                'lon': self.last_lon,
                'alt': 260.0,
                'time': datetime.now().isoformat(),
                'mode': 3,
                'satellites_used': 8
            }
        
        # Clear existing GPS data
        for item in self.gps_tree.get_children():
            self.gps_tree.delete(item)
        
        # Add GPS data rows
        gps_items = [
            ('Latitude', f"{gps_data.get('lat', 0):.6f}", '°'),
            ('Longitude', f"{gps_data.get('lon', 0):.6f}", '°'),
            ('Altitude', f"{gps_data.get('alt', 0):.1f}", 'ft'),
            ('Fix Mode', str(gps_data.get('mode', 0)), 'D'),
            ('Satellites', str(gps_data.get('satellites_used', 0)), ''),
            ('Time', gps_data.get('time', ''), ''),
        ]
        
        for prop, value, unit in gps_items:
            self.gps_tree.insert('', 'end', values=(prop, value, unit))
    
    def update_datetime(self):
        """Update date/time display"""
        now = datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M:%S")
        self.datetime_label.config(text=time_str)
        
        # Schedule next update
        self.root.after(1000, self.update_datetime)
    
    def toggle_night_mode(self):
        """Toggle night mode"""
        self.night_mode_on = self.night_mode_var.get()
        
        if self.night_mode_on:
            # Apply night mode colors
            print("🌙 Night mode enabled")
            # Would implement night mode styling here
        else:
            # Apply day mode colors
            print("☀️ Day mode enabled")
            # Would implement day mode styling here
    
    def refresh_all_data(self):
        """Refresh all data sources"""
        print("🔄 Refreshing all data...")
        self.load_static_data()
        self.update_gps_display()
    
    def run(self):
        """Start the application"""
        try:
            # Apply colored tabs after everything is created
            self.root.after(100, self.apply_tab_colors)
            
            # Bring window to front and focus it
            self.root.lift()
            self.root.attributes('-topmost', True)
            self.root.after(1000, lambda: self.root.attributes('-topmost', False))
            
            print("🎨 TowerWitch Tkinter version started!")
            print(f"📱 Window geometry: {self.root.geometry()}")
            print("🖥️ Starting main event loop...")
            
            # Start the main loop
            self.root.mainloop()
            
        except Exception as e:
            print(f"❌ Error in main loop: {e}")
            import traceback
            traceback.print_exc()

def main():
    """Main entry point"""
    root = tk.Tk()
    app = TowerWitchTkinter(root)
    
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n👋 TowerWitch shutting down...")
    finally:
        if app.gps_worker:
            app.gps_worker.stop()

if __name__ == "__main__":
    main()