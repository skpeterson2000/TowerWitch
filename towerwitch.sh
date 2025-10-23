#!/bin/bash
# TowerWitch Launcher Script
# Automatically handles dependencies and launches TowerWitch-P

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}🗼 TowerWitch-P Launcher${NC}"
echo "=================================="

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if Python package is installed
python_package_exists() {
    python3 -c "import $1" >/dev/null 2>&1
}

# Check Python 3
if ! command_exists python3; then
    echo -e "${RED}❌ Python 3 is not installed${NC}"
    echo "Please install Python 3: sudo apt install python3"
    exit 1
fi

echo -e "${GREEN}✅ Python 3 found${NC}"

# Check pip
if ! command_exists pip3; then
    echo -e "${YELLOW}⚠️  pip3 not found, installing...${NC}"
    sudo apt update && sudo apt install -y python3-pip
fi

# Check required Python packages
REQUIRED_PACKAGES=("PyQt5" "requests" "utm" "maidenhead" "mgrs")
MISSING_PACKAGES=()

for package in "${REQUIRED_PACKAGES[@]}"; do
    if python_package_exists "$package"; then
        echo -e "${GREEN}✅ $package installed${NC}"
    else
        echo -e "${YELLOW}⚠️  $package missing${NC}"
        MISSING_PACKAGES+=("$package")
    fi
done

# Install missing packages
if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    echo -e "${BLUE}📦 Installing missing packages...${NC}"
    for package in "${MISSING_PACKAGES[@]}"; do
        echo "Installing $package..."
        pip3 install "$package" --user
    done
fi

# Check GPS daemon
if command_exists gpsd; then
    echo -e "${GREEN}✅ gpsd found${NC}"
    
    # Check if gpsd is running
    if pgrep gpsd > /dev/null; then
        echo -e "${GREEN}✅ gpsd is running${NC}"
    else
        echo -e "${YELLOW}⚠️  gpsd not running, attempting to start...${NC}"
        if command_exists systemctl; then
            sudo systemctl start gpsd 2>/dev/null || echo -e "${YELLOW}⚠️  Could not start gpsd automatically${NC}"
        fi
    fi
else
    echo -e "${YELLOW}⚠️  gpsd not found${NC}"
    echo "For GPS functionality, install: sudo apt install gpsd gpsd-clients"
fi

# Check configuration file
if [ -f "towerwitch_config.ini" ]; then
    echo -e "${GREEN}✅ Configuration file found${NC}"
else
    echo -e "${YELLOW}⚠️  Configuration file not found${NC}"
    if [ -f "towerwitch_config.ini.example" ]; then
        echo "Creating default configuration from example..."
        cp towerwitch_config.ini.example towerwitch_config.ini
        echo -e "${BLUE}📝 Edit towerwitch_config.ini to add your Radio Reference API credentials${NC}"
    fi
fi

# Check for TowerWitch-P.py
if [ ! -f "TowerWitch-P.py" ]; then
    echo -e "${RED}❌ TowerWitch-P.py not found in current directory${NC}"
    exit 1
fi

echo -e "${GREEN}✅ All checks complete${NC}"
echo ""

# Check for saved preference
PREF_FILE="$HOME/.towerwitch_launch_pref"
AUTO_LAUNCH=true

# Load saved preference if it exists
if [ -f "$PREF_FILE" ]; then
    SAVED_CHOICE=$(cat "$PREF_FILE" 2>/dev/null)
    if [[ "$SAVED_CHOICE" =~ ^[1-5]$ ]]; then
        choice=$SAVED_CHOICE
        echo -e "${BLUE}Using saved preference: Option $choice${NC}"
    else
        AUTO_LAUNCH=false
    fi
else
    # Default to option 1 for first-time users
    choice=1
    echo -e "${GREEN}🚀 Auto-launching TowerWitch-P (standard mode)...${NC}"
    echo -e "${BLUE}💡 To change launch options, run with --menu flag${NC}"
fi

# Check for menu flag
if [[ "$1" == "--menu" ]] || [[ "$1" == "-m" ]] || [ "$AUTO_LAUNCH" = false ]; then
    # Show launch options
    echo -e "${BLUE}Launch Options:${NC}"
    echo "1) Standard launch"
    echo "2) Launch with X11 backend (if having display issues)"
    echo "3) Launch in debug mode"
    echo "4) Check GPS status"
    echo "5) Exit"
    echo "6) Save preference and launch"
    echo ""
    
    read -p "Select option (1-6): " choice
    
    # Handle preference saving
    if [ "$choice" = "6" ]; then
        echo ""
        echo -e "${BLUE}Save which option as default?${NC}"
        echo "1) Standard launch"
        echo "2) Launch with X11 backend"
        echo "3) Launch in debug mode"
        echo ""
        read -p "Save option (1-3): " pref_choice
        
        if [[ "$pref_choice" =~ ^[1-3]$ ]]; then
            echo "$pref_choice" > "$PREF_FILE"
            echo -e "${GREEN}✅ Saved option $pref_choice as default${NC}"
            choice=$pref_choice
        else
            echo -e "${RED}❌ Invalid preference choice${NC}"
            exit 1
        fi
    fi
fi

case $choice in
    1)
        echo -e "${GREEN}🚀 Launching TowerWitch-P...${NC}"
        python3 TowerWitch-P.py
        ;;
    2)
        echo -e "${GREEN}🚀 Launching TowerWitch-P with X11 backend...${NC}"
        QT_QPA_PLATFORM=xcb python3 TowerWitch-P.py
        ;;
    3)
        echo -e "${GREEN}🐛 Launching TowerWitch-P in debug mode...${NC}"
        echo "Debug output will be saved to towerwitch-p_debug.log"
        python3 TowerWitch-P.py --debug
        ;;
    4)
        echo -e "${BLUE}🛰️  Checking GPS status...${NC}"
        if command_exists cgps; then
            echo "GPS daemon status (press Ctrl+C to exit):"
            cgps -s
        else
            echo "cgps not found. Install with: sudo apt install gpsd-clients"
            if command_exists gpspipe; then
                echo "Using gpspipe for GPS check:"
                timeout 5s gpspipe -w -n 5 2>/dev/null || echo "No GPS data received"
            fi
        fi
        ;;
    5)
        echo -e "${BLUE}👋 Goodbye!${NC}"
        exit 0
        ;;
    6)
        # This case is handled above in the preference saving logic
        ;;
    *)
        echo -e "${RED}Invalid option. Use --menu to see all options.${NC}"
        exit 1
        ;;
esac