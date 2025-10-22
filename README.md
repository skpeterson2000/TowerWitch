# TowerWitch

**GPS-enabled Amateur Radio Tower & Repeater Locator**

TowerWitch is a comprehensive amateur radio application that helps locate nearby radio repeaters and emergency services communication resources using GPS positioning. Perfect for mobile operation, emergency preparedness, and exploring new areas.

## Features

### 🗼 Multi-Service Support
- **ARMER** - Allied Radio Matrix for Emergency Response (Minnesota P25 trunked system)
- **Skywarn** - Weather spotting repeater networks for inclement weather
- **Amateur Radio** - Repeaters across all bands (10m, 6m, 2m, 1.25m, 70cm, Simplex)
- **GPS Tracking** - Real-time location with bearing/distance calculations
- **Grid Systems** - Maidenhead, UTM, MGRS, USNG coordinate display

### 📱 Touch-Optimized Interface
- Large, readable fonts for mobile/tablet use
- **Night Mode** - Red-tinted display for night vision preservation
- Professional tabbed interface with color-coded sections
- Touch-friendly controls and spacing

### 🌐 Live Data Integration
- **Radio Reference API** - Live repeater database access
- **Intelligent Caching** - Reduces API calls and enables offline operation
- **Static Fallbacks** - Comprehensive built-in databases when API unavailable
- **Auto-refresh** - Updates when you move to new locations

### 🎯 Key Capabilities
- **Real-time GPS** integration with gpsd
- **Distance & Bearing** calculations to all sites
- **Frequency Management** - Complete band plans and allocations
- **Emergency Services** - Quick access to public safety frequencies
- **Mobile Ready** - Optimized for Raspberry Pi and touch displays

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

# Configure Radio Reference API (optional but recommended)
cp towerwitch_config.ini.example towerwitch_config.ini
# Edit towerwitch_config.ini with your Radio Reference API credentials

# Run TowerWitch
python3 TowerWitch-P.py
```

## Configuration

### Radio Reference API Setup
1. Sign up at [Radio Reference](https://www.radioreference.com/)
2. Get your API credentials from account settings
3. Edit `towerwitch_config.ini`:
```ini
[API]
radio_reference_username = your_username
radio_reference_password = your_password
```

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
3. **Explore Tabs** - Browse available repeaters and services
4. **Night Mode** - Toggle with Ctrl+N for night operations

### Tabs Overview
- **GPS** - Current position, speed, heading, satellite info
- **Grids** - Coordinate systems (Maidenhead, UTM, MGRS, USNG)
- **ARMER** - Minnesota P25 emergency communication sites
- **Skywarn** - Weather spotting repeater networks
- **Amateur** - Ham radio repeaters by band (10m, 6m, 2m, 1.25m, 70cm, Simplex)

### Keyboard Shortcuts
- **F11** - Toggle fullscreen
- **Ctrl+N** - Toggle night mode
- **Ctrl+Q** - Quit application

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

### Data
- **Regional Databases** - State/country-specific repeater data
- **Band Plans** - International frequency allocations
- **Emergency Services** - Local public safety frequencies

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Support

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
- **Frontend** - PyQt5 (v1.x) / Kivy (v2.x)
- **GPS** - gpsd integration
- **API** - Radio Reference REST API
- **Data** - JSON caching with INI configuration
- **Coordinates** - UTM/Maidenhead/MGRS conversion

### Performance
- **Startup** - ~3-5 seconds to full functionality
- **GPS Update** - 1Hz refresh rate
- **API Calls** - Intelligent caching minimizes requests
- **Memory** - ~50MB typical usage

---

**73s and happy mobile operation!** 📻

*TowerWitch - Because knowing where you are is half the battle.*
