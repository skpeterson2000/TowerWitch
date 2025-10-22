# Changelog

All notable changes to TowerWitch will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-10-22

### Added - TowerWitch-P (PyQt5) MVP Release
- **GPS Integration** - Real-time GPS tracking with gpsd
- **Amateur Radio Bands** - 10m, 6m, 2m, 1.25m, 70cm, Simplex frequencies
- **Emergency Services** - ARMER P25 system and Skywarn networks
- **Grid Systems** - Maidenhead, UTM, MGRS, USNG coordinate display
- **Radio Reference API** - Live repeater database integration
- **Touch Interface** - Optimized for tablets and touch displays
- **Night Mode** - Red-tinted display for night vision preservation
- **Intelligent Caching** - Reduces API calls and enables offline operation
- **Distance/Bearing** - Great circle calculations to all sites
- **Professional UI** - Clean tabbed interface with consistent styling

### Features
- **Multi-Service Support** - Amateur, emergency, and public service frequencies
- **Regional Coverage** - 200-mile radius with smart caching
- **Static Fallbacks** - Built-in databases when API unavailable
- **Configuration Management** - INI-based settings with examples
- **Cross-Platform** - Linux desktop and Raspberry Pi support

### Technical
- **PyQt5 Framework** - Mature desktop application framework
- **GPS Daemon Integration** - Standard gpsd interface
- **REST API Client** - Radio Reference database access
- **JSON Caching** - Efficient data storage and retrieval
- **Coordinate Conversion** - Multiple grid system support

## [2.0.0] - In Development

### Planned - TowerWitch-K (Kivy) Mobile Version
- **Native Touch Interface** - Built for mobile from ground up
- **Android Deployment** - APK for mobile devices
- **Enhanced Gestures** - Swipe navigation and touch optimizations
- **Offline Maps** - Integrated mapping for field use
- **Voice Announcements** - Hands-free operation support
- **Cross-Platform** - Consistent experience across devices

## Version History

### Development Milestones
- **v0.1** - Initial GPS and basic repeater display
- **v0.5** - Radio Reference API integration
- **v0.8** - Emergency services and night mode
- **v0.9** - Touch optimization and caching
- **v1.0** - MVP release with full feature set

### Future Roadmap
- **v1.1** - Bug fixes and performance improvements
- **v1.5** - Map integration and export capabilities
- **v2.0** - Kivy mobile version
- **v2.5** - Android/iOS deployment
- **v3.0** - Advanced mobile features

## Breaking Changes

### v1.0.0
- Renamed from `TowerWitch_Enhanced.py` to `TowerWitch-P.py`
- Updated configuration format to include more options
- Changed log file location to `towerwitch-p_debug.log`
- Removed experimental map features for stability

### v2.0.0 (Planned)
- Complete UI framework change from PyQt5 to Kivy
- New mobile-first interface design
- Different configuration options for mobile deployment

## Known Issues

### v1.0.0
- Map integration removed due to coordinate placement issues
- Limited to Radio Reference API regions
- Requires GPS hardware for full functionality
- System Qt themes may override custom colors on some systems

## Support

- **Issues** - Report bugs via GitHub Issues
- **Documentation** - Check README.md and CONTRIBUTING.md
- **Community** - Amateur radio focused development
- **License** - GNU GPL v3.0

---

**73s and happy mobile operation!** 📻