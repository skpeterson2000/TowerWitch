#!/bin/bash
# Debug launcher for TowerWitch
cd /home/pi/TowerWitch
echo "Starting TowerWitch with debug output..."
/home/pi/TowerWitch/.venv/bin/python TowerWitch_Tkinter.py 2>&1 | tee towerwitch_debug.log
