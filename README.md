# TowerWitch Enhanced - GPS Tower Locator

An enhanced GPS-enabled tower locator application for amateur radio operators, emergency services, and communications enthusiasts.

## Features

### 🏗️ Comprehensive Radio Infrastructure
- **Amateur Radio Repeaters**: 2m, 70cm, 6m, 10m, and 1.25m band coverage
- **Simplex Frequencies**: 25 standardized calling and special frequencies
- **ISS Communications**: Space station voice and packet frequencies
- **Digital Modes**: APRS, D-STAR, and packet radio frequencies
- **Skywarn Network**: Enhanced emergency weather communications
- **ARMER System**: Minnesota state communications infrastructure
- **Regional Coverage**: Smart caching with 200-mile radius

### 📡 Advanced Location Services
- **Real-time GPS**: gpsd integration for live positioning
- **Multiple Coordinate Systems**: Lat/Lon, UTM, USNG, Maidenhead
- **Distance & Bearing**: Accurate calculations to all sites
- **Smart Caching**: Regional cache with 24-hour refresh

### 🌐 API Integration
- **Radio Reference API**: Live repeater database access
- **Enhanced Filtering**: Emergency services keyword detection
- **Hybrid Data Strategy**: API + static fallback
- **Geographic Validation**: Coordinate verification

### 🛠️ User Interface
- **Touch-Optimized**: Designed for 10" touchscreens (1024x600)
- **Tabbed Interface**: Organized by service type
- **Real-time Updates**: Automatic GPS and data refresh
- **Configuration Management**: Persistent settings

## Recent Enhancements

### Skywarn Detection Overhaul (700% Improvement)
- **Enhanced API Filtering**: 15+ emergency service keywords
- **Multi-field Search**: Name, description, and usage fields
- **Frequency-based Detection**: VHF/UHF emergency allocations
- **Deduplication Logic**: Prevents duplicate entries
- **Static Database**: 18 verified Minnesota emergency repeaters
- **Hybrid Strategy**: Live API (7 repeaters) + static fallback (18 repeaters)

### Technical Improvements
- **Geographic Coordinate Validation**: Ensures valid lat/lon pairs
- **Smart Regional Caching**: 200-mile coverage with 24-hour refresh
- **Enhanced Error Handling**: Robust API failure recovery
- **Performance Optimization**: Reduced API calls and faster responses

## Installation

### Prerequisites
```bash
sudo apt-get update
sudo apt-get install python3-pyqt5 python3-pip gpsd gpsd-clients
pip3 install utm maidenhead mgrs requests
```

### Configuration
1. Copy `towerwitch_config.ini.example` to `towerwitch_config.ini`
2. Add your Radio Reference API key:
```ini
[API]
radio_reference_key = your_api_key_here
```

### Running
```bash
python3 TowerWitch_Enhanced.py
```

## Technical Architecture

### Core Components
- **RadioReferenceAPI**: API client with smart caching
- **GPSThread**: Real-time location services
- **EnhancedGPSWindow**: Main PyQt5 interface
- **Multi-band Support**: Comprehensive amateur radio coverage

### Data Sources
- **Live API**: Radio Reference database
- **Static Database**: Verified emergency repeaters
- **GPS Integration**: Real-time positioning
- **Cache System**: Regional data persistence

### Coordinate Systems
- **Geographic**: Decimal degrees (WGS84)
- **UTM**: Universal Transverse Mercator
- **USNG**: United States National Grid
- **Maidenhead**: Amateur radio grid squares

## File Structure
```
tw25/
├── TowerWitch_Enhanced.py      # Main application
├── towerwitch_config.ini       # Configuration file
├── trs_sites_3508.csv         # ARMER site database
├── radio_cache/               # API response cache
└── KC9SP/                     # Additional utilities
```

## Recent Changes

### Map Functionality Removal
- Removed problematic mapping features that failed to properly place repeaters
- Cleaned up folium dependencies and related code
- Simplified interface by removing non-functional map tab
- User can create separate mapping utility as needed

### Performance Enhancements
- 700% improvement in Skywarn repeater detection (1→7 repeaters)
- Enhanced emergency service keyword detection
- Comprehensive static database with 18 verified emergency repeaters
- Smart geographic coordinate validation

## License
This project is licensed under the MIT License.

## Contributing
Contributions welcome! Please ensure all emergency service data is verified and accurate.

## Support
For issues or questions, please create an issue in the repository.