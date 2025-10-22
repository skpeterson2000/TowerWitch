# TowerWitch v2.0 - Kivy Version Roadmap

## Project Goals
Convert TowerWitch from PyQt5 to Kivy for better touch interface and mobile deployment

## Advantages We'll Gain
- **Native Touch Support**: Multi-touch, gestures, swipe navigation
- **Mobile Deployment**: Android APK, iOS app potential
- **Better Performance**: Optimized for ARM devices like Raspberry Pi
- **Modern UI**: Animations, Material Design, better graphics
- **Cross-Platform**: Consistent look everywhere

## Architecture Plan

### Core Components to Port
1. **GPS Worker** → Kivy Clock scheduling
2. **Radio Reference API** → Keep as-is (pure Python)
3. **Data Models** → Keep as-is (amateur bands, ARMER, Skywarn)
4. **Configuration** → Keep as-is (INI file handling)

### UI Transformation
1. **Main Tabs** → Kivy TabbedPanel or custom navigation
2. **Tables** → Custom RecycleView or DataTable widgets
3. **Maps** → Kivy Garden MapView integration
4. **Forms** → Touch-optimized input widgets

### New Features Possible
1. **Swipe Navigation** between bands
2. **Pull-to-Refresh** for data updates
3. **Location Services** for mobile GPS
4. **Offline Maps** for field use
5. **Voice Announcements** for hands-free operation

## Development Phases

### Phase 1: Core Framework (v2.0-alpha)
- [ ] Set up Kivy project structure
- [ ] Port GPS data display to Kivy
- [ ] Create basic tabbed navigation
- [ ] Implement touch-friendly table display

### Phase 2: Feature Parity (v2.0-beta)
- [ ] Port all PyQt5 functionality
- [ ] ARMER, Skywarn, Amateur radio data
- [ ] Night mode support
- [ ] Configuration management

### Phase 3: Mobile Enhancements (v2.0-rc)
- [ ] Android APK building
- [ ] Touch gesture optimization
- [ ] Mobile-specific features
- [ ] Performance optimization

### Phase 4: Advanced Features (v2.0-final)
- [ ] Map integration
- [ ] Offline operation
- [ ] Advanced touch UI
- [ ] App store deployment

## Technical Considerations

### Dependencies
- `kivy` - Main framework
- `kivymd` - Material Design components
- `kivy-garden.mapview` - Map support
- Keep existing: `requests`, `utm`, `maidenhead`, `mgrs`

### File Structure
```
towerwitch-kivy/
├── main.py              # Main Kivy app
├── towerwitch.kv         # UI layout definitions
├── screens/             # Individual screen widgets
│   ├── gps_screen.py
│   ├── armer_screen.py
│   ├── skywarn_screen.py
│   └── amateur_screen.py
├── widgets/             # Custom widgets
│   ├── data_table.py
│   └── touch_button.py
├── core/                # Business logic (reused from v1.0)
│   ├── gps_worker.py
│   ├── radio_api.py
│   └── data_models.py
└── assets/              # Images, sounds, etc.
```

### Mobile-Specific Features
- **GPS Integration**: Use Kivy's plyer for mobile GPS
- **Touch Optimization**: Larger touch targets, swipe gestures
- **Responsive Layout**: Adapt to different screen sizes
- **Battery Awareness**: Efficient update cycles
- **Offline Mode**: Cache data for field use

## Timeline Estimate
- **Phase 1**: 2-3 weeks (basic framework)
- **Phase 2**: 3-4 weeks (feature parity)
- **Phase 3**: 2-3 weeks (mobile optimization)
- **Phase 4**: 2-3 weeks (advanced features)

**Total**: ~10-12 weeks for complete v2.0

## Success Metrics
- [ ] All v1.0 features working in Kivy
- [ ] Touch interface more responsive than PyQt5
- [ ] Successful Android APK deployment
- [ ] Better performance on Raspberry Pi
- [ ] Positive user feedback on mobile experience

---

*This roadmap will be updated as development progresses*