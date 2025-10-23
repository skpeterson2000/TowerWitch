# TowerWitch

**GPS-enabled Amateur Radio Tower & Repeater Locator**

TowerWitch is a comprehensive amateur radio application that helps locate nearby radio repeaters and emergency services communication resources using GPS positioning. Perfect for mobile operation, emergency preparedness, and exploring new areas.

## Features

### 🗼 Multi-Service Support
- **ARMER** - Allied Radio Matrix for Emergency Response (Minnesota P25 trunked system)
- **SKYWARN** - Weather spotting repeater networks for severe weather operations
- **NOAA Weather Radio** - All 7 standard frequencies with distance calculations
- **Amateur Radio** - Repeaters across all bands (10m, 6m, 2m, 1.25m, 70cm, Simplex)
- **GPS Tracking** - Real-time location with bearing/distance calculations
- **Grid Systems** - Maidenhead, UTM, MGRS, USNG coordinate display

### 📱 Touch-Optimized Interface
- Large, readable fonts for mobile/tablet use
- **Night Mode** - Red-tinted display for night vision preservation
- **5-Tab Interface** - Streamlined tabbed layout with color-coded sections
- **Utilities Button** - Separate dialog for location tools and data management
- Touch-friendly controls and spacing
- **Tab Colors** - Purple (Location), Red (ARMER), Orange (SKYWARN), Green (NOAA), Blue (Amateur)

### 🌐 Live Data Integration
- **Radio Reference API** - Live repeater database access (premium account)
- **CSV Databases** - Comprehensive built-in data (no account needed)
- **Intelligent Caching** - Reduces API calls and enables offline operation
- **Static Fallbacks** - Works without internet connectivity
- **Auto-refresh** - Updates when you move to new locations

### 🎯 Key Capabilities
- **Real-time GPS** integration with gpsd
- **Distance & Bearing** calculations to all sites
- **Frequency Management** - Complete band plans and allocations
- **Emergency Services** - Quick access to public safety frequencies
- **Mobile Ready** - Optimized for Raspberry Pi and touch displays

### 📤 Export & Broadcasting
- **PDF Export** - Professional reports with configurable tower count (10 towers default)
- **UDP Broadcasting** - Real-time closest towers via JSON over UDP
- **Network Integration** - Broadcast location and tower data for external systems
- **Configurable Output** - Customizable broadcast intervals and destinations
- **Clean Logging** - Minimal console output with comprehensive error handling

## Versions

### TowerWitch-P (PyQt5) - v1.0 MVP ✅
- **Current stable release**
- Full-featured desktop application
- Mature PyQt5 interface
- Complete GPS and Radio Reference integration

### TowerWitch-K (Kivy) - v1.0 In Development 🚧
- Native touch interface
- Mobile deployment (Android APK)
- Cross-platform consistency
- Enhanced mobile features

## Installation

### Prerequisites
```bash
# Install system dependencies
sudo apt update
sudo apt install python3 python3-pip gpsd gpsd-clients

# Install Python dependencies
pip3 install PyQt5 requests utm maidenhead mgrs
```

### Quick Start
```bash
# Clone the repository
git clone https://github.com/yourusername/TowerWitch.git
cd TowerWitch

# Use automated launcher (recommended)
chmod +x towerwitch.sh
./towerwitch.sh

# OR configure manually:
# Copy configuration template (optional - works without API)
cp towerwitch_config.ini.example towerwitch_config.ini
# Edit towerwitch_config.ini with your Radio Reference API credentials (optional)

# Run TowerWitch directly
python3 TowerWitch-P.py
```

**Note:** TowerWitch works immediately with built-in CSV databases - no API setup required!

## Configuration

### Radio Reference API Setup (Recommended)
1. Sign up at [Radio Reference](https://www.radioreference.com/)
2. Get your API credentials from account settings
3. Edit `towerwitch_config.ini`:
```ini
[API]
radio_reference_username = your_username
radio_reference_password = your_password
```

### Alternative: CSV Data Sources (No API Required)
**Don't have a Radio Reference premium account?** TowerWitch includes comprehensive CSV databases:

- **`trs_sites_3508.csv`** - Complete ARMER (Minnesota P25) site database
- **`AmateurSimplex.csv`** - Amateur radio simplex frequencies by band
- **Built-in Static Data** - Extensive repeater databases for emergency fallback

TowerWitch automatically uses these CSV sources when:
- No API credentials are configured
- API is temporarily unavailable
- Working in offline environments
- Limited API calls remaining

**Benefits of CSV mode:**
- ✅ **No subscription required** - Works immediately out of the box
- ✅ **Offline capability** - Perfect for remote field operations  
- ✅ **Fast performance** - No network delays
- ✅ **Emergency backup** - Always available as fallback

### GPS Configuration
TowerWitch uses `gpsd` for GPS data:
```bash
# Start GPS daemon
sudo systemctl enable gpsd
sudo systemctl start gpsd

# Test GPS connection
cgps -s
```

## Usage

### Basic Operation
1. **Launch** TowerWitch-P.py
2. **GPS Lock** - Wait for GPS acquisition (shown in header)
   - Green "GPS: Active (Stationary)" - GPS locked, not moving
   - Green "GPS: Active (Walking X.X mph)" - GPS locked, walking speed
   - Orange "GPS: Active (Vehicle XX mph)" - GPS locked, vehicle speed
3. **Explore Tabs** - Browse available repeaters and services
4. **Night Mode** - Click 🌙 button for red-tinted night operations
5. **Fullscreen** - Press F11 for full-screen mobile operation

### Motion-Aware Updates
TowerWitch automatically adjusts update behavior based on your speed:
- **Stationary** (0-1.1 mph) - Full updates for all services
- **Walking** (1.1-5 mph) - Full updates for all services  
- **Vehicle** (>5 mph) - Smart updates: ARMER/SKYWARN every 25s, Amateur every 35s

### Tabs Overview
- **Location** - GPS coordinates, speed, heading + Grid systems (Maidenhead, UTM, MGRS)
- **ARMER** - Minnesota P25 emergency communication sites (10 closest towers default)
- **SKYWARN** - Weather spotting repeater networks for severe weather operations
- **NOAA** - Weather Radio frequencies (162.400-162.550 MHz) sorted by distance
- **Amateur** - Ham radio repeaters by band (10m, 6m, 2m, 1.25m, 70cm, Simplex)
- **Utilities** - Location tools and data management (accessed via 🔧 button)

### Data Sources & Modes
**With Radio Reference API:**
- Live repeater data from premium database
- Automatic location-based updates
- Comprehensive coverage

**Without API (CSV Mode):**
- Built-in ARMER database (trs_sites_3508.csv)
- Simplex frequencies (AmateurSimplex.csv)
- Static repeater fallback data
- Full offline operation

### Keyboard Shortcuts
- **F11** - Toggle fullscreen
- **Escape** - Exit fullscreen (when in fullscreen mode)
- **Ctrl+Q** - Quit application
- **Ctrl+C** - Quit application (alternative)
- **Ctrl+N** - Toggle night mode
- **Ctrl+R** - Refresh all data
- **Ctrl+P** - Export PDF to Downloads folder
- **Ctrl+E** - Export PDF to Downloads folder (alternative)
- **Ctrl+1** - Switch to Location tab
- **Ctrl+2** - Switch to ARMER tab
- **Ctrl+3** - Switch to SKYWARN tab
- **Ctrl+4** - Switch to NOAA tab
- **Ctrl+5** - Switch to Amateur tab

### Button Controls
- **🔄 Refresh All** - Force refresh all repeater data (Ctrl+R)
- **📄 Export PDF** - Export current data to PDF in Downloads folder (Ctrl+P or Ctrl+E)
- **🔧 Utilities** - Open utilities dialog with location tools and data management
- **🌙 Night Mode** - Toggle red-tinted night vision display (Ctrl+N)

### Advanced Features
- **Motion-Aware Updates** - Automatic update intervals based on GPS speed
- **Intelligent Caching** - Reduces API calls and enables offline operation
- **Distance & Bearing** - Calculated to all repeaters from current position
- **Color-Coded Display** - Tab colors and status indicators for quick identification
- **Touch Optimization** - Large buttons and readable fonts for mobile devices
- **Unified Location Tab** - GPS and coordinate systems in one view
- **PDF Export** - Professional reports with configurable tower count
- **Emergency Ready** - Works offline with CSV databases when API unavailable
- **NOAA Weather Radio** - All 7 standard frequencies with distance-based priority
- **Utilities Dialog** - Separate window for location tools and data management
- **Clean UDP Logging** - Minimal console output with comprehensive error handling

## Screenshots

*[Screenshots would go here showing the main interface, night mode, different tabs]*

## Hardware Compatibility

### Tested Platforms
- **Raspberry Pi 3B+/4** - Primary development platform
- **Linux Desktop** - Ubuntu, Debian, Fedora
- **Touch Displays** - 7" and larger recommended

### GPS Hardware
- **USB GPS dongles** (recommended)
- **HAT-based GPS** modules for Raspberry Pi
- **Built-in GPS** (laptops/tablets)

## Contributing

We welcome contributions! Areas where help is needed:

### Development
- **Kivy Version** - Help with TowerWitch-K mobile development
- **Feature Requests** - New bands, services, or capabilities
- **Bug Reports** - Testing and issue identification
- **Documentation** - User guides and tutorials

### Data Sources
- **Radio Reference API** - Premium live database access
- **CSV Files** - Local databases included (no subscription required)
  - `trs_sites_3508.csv` - Complete ARMER site data
  - `AmateurSimplex.csv` - Amateur simplex frequencies
- **Static Databases** - Emergency fallback data
- **Regional Files** - State/country-specific repeater data
- **Band Plans** - International frequency allocations
- **Emergency Services** - Local public safety frequencies

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Support

### Quick Tips
- **No GPS?** Check `sudo systemctl status gpsd` and ensure GPS hardware is connected
- **Slow Updates?** Normal behavior - updates every 25-35 seconds during motion for battery conservation
- **No Radio Reference Data?** Application works fine with built-in CSV databases - no API required
- **Touch Screen Issues?** Use fullscreen mode (F11) for optimal mobile experience
- **Night Operations?** Night mode (Ctrl+N) preserves night vision with red-tinted display

### Keyboard Quick Reference
```
F11             - Fullscreen toggle
Escape          - Exit fullscreen  
Ctrl+N          - Night mode
Ctrl+R          - Refresh data
Ctrl+P/E        - Export PDF
Ctrl+1/2/3/4/5  - Switch tabs (Location/ARMER/SKYWARN/NOAA/Amateur)
Ctrl+Q/C        - Quit
```

### Community
- **Issues** - Report bugs via GitHub Issues
- **Discussions** - Feature requests and general discussion
- **Wiki** - Detailed documentation and tutorials

### Author
Developed for the amateur radio community with focus on emergency preparedness and mobile operation.

## Roadmap

### v1.x (PyQt5 - Current)
- [x] Core GPS and repeater functionality
- [x] Radio Reference API integration
- [x] Night mode and touch optimization
- [ ] Map integration
- [ ] Export capabilities

### v2.x (Kivy - Future)
- [ ] Native mobile interface
- [ ] Android APK deployment
- [ ] Enhanced touch gestures
- [ ] Offline map support
- [ ] Voice announcements

## Technical Details

### File Structure
```
TowerWitch/
├── TowerWitch-P.py                  # PyQt5 version (v1.0)
├── TowerWitch-K.py                  # Kivy version (v2.0 prototype)
├── towerwitch_config.ini            # Configuration file
├── towerwitch_config.ini.example    # Configuration template
├── trs_sites_3508.csv              # ARMER site database
├── AmateurSimplex.csv              # Simplex frequency database
├── radio_cache/                    # API response cache directory
├── custom_qt_style.py              # Custom PyQt5 styling
├── KIVY_ROADMAP.md                 # Kivy development roadmap
├── LICENSE                         # GPL v3.0 license
└── README.md                       # This file
```

### Architecture
- **Frontend** - PyQt5 (v1.x) with 5-tab interface and utilities dialog
- **GPS** - gpsd integration with motion-aware updates
- **API** - Radio Reference REST API with intelligent caching
- **Data** - JSON caching with INI configuration
- **Coordinates** - UTM/Maidenhead/MGRS conversion
- **UDP** - Configurable broadcasting with error handling
- **Export** - PDF generation with configurable tower count

### Performance
- **Startup** - ~3-5 seconds to full functionality
- **GPS Update** - 1Hz refresh rate
- **API Calls** - Intelligent caching minimizes requests
- **Memory** - ~50MB typical usage

---

**73s and happy mobile operation!** 📻

*TowerWitch - Because knowing where you are is half the battle.*
