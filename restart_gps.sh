#!/bin/bash
# Restart GPS daemon to clear cached data
echo "Stopping gpsd..."
sudo systemctl stop gpsd
sudo systemctl stop gpsd.socket
sleep 1

echo "Clearing any stale processes..."
sudo killall gpsd 2>/dev/null || true
sleep 1

echo "Starting gpsd..."
sudo systemctl start gpsd.socket
sudo systemctl start gpsd
sleep 2

echo "Checking GPS status..."
cgps -s &
CGPS_PID=$!
sleep 5
kill $CGPS_PID 2>/dev/null || true

echo ""
echo "GPS daemon restarted. Wait 30 seconds for fix, then run:"
echo "  ./run_towerwitch.sh"
