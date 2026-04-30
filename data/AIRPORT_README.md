# Adding Your Own Airports to TowerWitch

## Quick Start

Your three airports have been added:
- **KPWC** - Pine River Regional (CTAF 122.9, UNICOM 122.8, AWOS 118.325)
- **KAIT** - Aitkin Municipal/Steve Kurtz Field (CTAF 122.9, UNICOM 122.8, AWOS 118.375)
- **Y49** - Crosby Municipal (CTAF 122.9, UNICOM 122.8)

They'll automatically appear in the Aviation > Nearby tab when you're within 100nm!

## Adding More Airports

### Method 1: Edit the Template (Easiest)

1. Copy `airport_frequencies_template.csv` to `airport_frequencies_custom.csv`
2. Edit `airport_frequencies_custom.csv` with your favorite text editor
3. Add your airports following the format in the template
4. Restart TowerWitch - it will automatically load your custom airports!

### Method 2: Edit Main File (Not Recommended)

You can add directly to `airport_frequencies.csv` but your changes may be overwritten by updates.

## Airport Frequency Reference

### Common CTAF Frequencies
- **122.7 MHz** - Common at many small airports
- **122.8 MHz** - Most common CTAF/UNICOM
- **122.9 MHz** - Very common (default multicom)
- **123.0 MHz** - Popular in northern regions
- **123.05 MHz** - Less common but used
- **123.075 MHz** - Regional variants

### Typical Services
- **CTAF** - Common Traffic Advisory Frequency (required)
- **UNICOM** - Usually 122.8 MHz for pilot services
- **AWOS/ASOS** - Automated weather (118.x or 135.x range)
- **Tower** - Controlled airports only
- **Ground** - Controlled airports only
- **ATIS** - Automated Terminal Information Service

## Need Airport Coordinates?

The system already has coordinates for these Minnesota airports:
- KMSP, KDLH, KRST, KSTC (major Class C/D)
- KFCM, KMIC, KANE, KSGS (Twin Cities area)
- KBRD, KPWC, KAIT, Y49 (Brainerd Lakes area)
- KGPZ, KBJI, KINL (northern Minnesota)
- And many more...

**To add a new airport:**
1. Add frequencies to `airport_frequencies_custom.csv`
2. Add coordinates in the code (or ask me to add them!)

## Example Custom Airport Entry

```csv
122.9,0,,,Little Falls - CTAF,LXL CTAF,CSQ,,AM,BM,Airport,KLXL,CTAF
122.8,0,,,Little Falls - UNICOM,LXL UNICOM,CSQ,,AM,BM,Airport,KLXL,UNICOM
118.525,0,,,Little Falls - AWOS,LXL AWOS,CSQ,,AM,BM,Airport,KLXL,AWOS
```

## Finding Airport Information

### Online Resources:
- **SkyVector** - skyvector.com (best for quick frequency lookups)
- **AirNav** - airnav.com (comprehensive airport database)
- **FAA Chart Supplement** - faa.gov (official source)
- **ForeFlight/Garmin Pilot** - if you subscribe

### What You Need:
1. Airport identifier (ICAO code like KLXL, or FAA code like Y49)
2. CTAF frequency (required for Class E/G airports)
3. UNICOM if different from CTAF
4. AWOS/ASOS/ATIS frequency if available
5. Approximate lat/lon (I can help with this)

## Questions?

Just give me airport codes and I'll add them with proper frequencies and coordinates!
