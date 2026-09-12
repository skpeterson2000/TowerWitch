#!/bin/bash
# TowerWitch GUI Launcher with GPS support
cd /home/pt8/TowerWitch
# -u: stdout goes to ~/.xsession-errors, and a line about the GPS is only
# useful there if it lands when it happened, not 8 KB later.
/usr/bin/python3 -u TowerWitch_Tkinter.py
