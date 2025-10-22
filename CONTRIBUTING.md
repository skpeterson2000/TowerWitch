# Contributing to TowerWitch

Thank you for your interest in contributing to TowerWitch! We welcome contributions from the amateur radio community.

## Ways to Contribute

### 🐛 Bug Reports
- Check existing issues before creating new ones
- Include Python version, OS, and GPS hardware details
- Provide steps to reproduce the issue
- Include relevant log files (`towerwitch-p_debug.log`)

### 💡 Feature Requests
- Search existing issues for similar requests
- Describe the use case and benefit to the amateur radio community
- Consider both mobile and desktop use cases

### 🔧 Code Contributions
- Fork the repository
- Create a feature branch (`git checkout -b feature/amazing-feature`)
- Follow Python coding standards (PEP 8)
- Test on Raspberry Pi if possible
- Submit a pull request

### 📊 Data Contributions
- **Regional Repeater Data** - Static databases for areas with limited API coverage
- **Band Plans** - International frequency allocations
- **Emergency Networks** - Verified public safety repeater information

## Development Setup

### Prerequisites
```bash
# System dependencies
sudo apt update
sudo apt install python3 python3-pip gpsd gpsd-clients

# Python dependencies
pip3 install PyQt5 requests utm maidenhead mgrs

# Optional: Kivy for v2.0 development
pip3 install kivy kivymd
```

### Testing
```bash
# Test PyQt5 version
python3 TowerWitch-P.py

# Test configuration loading
python3 -c "import configparser; c=configparser.ConfigParser(); c.read('towerwitch_config.ini'); print('Config OK')"

# Test GPS (requires GPS hardware)
cgps -s
```

## Code Standards

### Python Style
- Follow PEP 8 coding standards
- Use meaningful variable names
- Comment complex amateur radio calculations
- Include docstrings for functions

### Amateur Radio Specific
- **Frequencies** - Always in MHz with 3+ decimal places
- **Coordinates** - Use decimal degrees (WGS84)
- **Call Signs** - Preserve exact capitalization
- **Emergency Services** - Verify data accuracy

### UI Guidelines
- **Touch-Friendly** - Minimum 44px touch targets
- **Accessible** - High contrast, readable fonts
- **Mobile-First** - Optimize for tablets/small screens
- **Night Mode** - Red-tinted colors for night vision

## Version Information

### TowerWitch-P (PyQt5) - v1.0
- **Stable** - Focus on bug fixes and data accuracy
- **Desktop-Oriented** - Mature interface
- **Feature Complete** - No major new features

### TowerWitch-K (Kivy) - v2.0
- **Development** - Active new development
- **Mobile-First** - Touch-optimized interface
- **Cross-Platform** - Android/iOS deployment target

## Data Guidelines

### Repeater Information
- **Verify Accuracy** - Test coordinates and frequencies when possible
- **Include Metadata** - Tone squelch, offset, notes
- **Emergency Focus** - Prioritize public service and emergency networks
- **Regional Coverage** - Focus on comprehensive area coverage

### Geographic Data
- **Coordinate Validation** - Ensure lat/lon pairs are accurate
- **Bearing Calculations** - Use great circle distance
- **Regional Boundaries** - Respect service area limits

## Pull Request Process

1. **Fork and Branch** - Create feature branch from main
2. **Develop and Test** - Test on actual hardware when possible
3. **Documentation** - Update README.md if needed
4. **Commit Messages** - Use clear, descriptive commit messages
5. **Pull Request** - Describe changes and testing performed

### Commit Message Format
```
type(scope): description

Examples:
feat(gps): add WAAS satellite support
fix(api): handle radio reference timeout gracefully
docs(readme): update installation instructions
data(skywarn): add verified Minnesota repeaters
```

## Testing Guidelines

### Hardware Testing
- **GPS Devices** - Test with USB dongles and built-in GPS
- **Raspberry Pi** - Verify performance on Pi 3B+ and 4
- **Touch Displays** - Test on 7" and 10" screens

### Software Testing
- **API Integration** - Test with and without Radio Reference API
- **Offline Operation** - Verify cache functionality
- **Night Mode** - Check red-tinted display
- **Coordinate Systems** - Validate grid conversions

## License

By contributing, you agree that your contributions will be licensed under the GNU General Public License v3.0.

## Questions?

- **Issues** - GitHub Issues for bugs and features
- **Discussions** - GitHub Discussions for general questions
- **Amateur Radio** - This is an amateur radio project - keep it in the spirit of experimentation and public service

**73s and thank you for contributing!** 📻