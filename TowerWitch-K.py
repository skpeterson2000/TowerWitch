#!/usr/bin/env python3
"""
TowerWitch-K v2.0 - Kivy Version
Proof of concept for GPS data display in Kivy
"""

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.label import Label
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.clock import Clock
from datetime import datetime
import time

class GPSDataWidget(GridLayout):
    """GPS data display widget similar to PyQt5 version"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cols = 2
        self.padding = 10
        self.spacing = 5
        
        # GPS data labels (similar to PyQt5 table)
        self.gps_data = {
            'Latitude': '44.9778°',
            'Longitude': '-93.2650°',
            'Altitude': '825 ft',
            'Speed': '0.0 mph',
            'Heading': '0°',
            'Fix Type': '3D',
            'Satellites': '8',
            'Last Update': 'Searching...'
        }
        
        self.labels = {}
        self.create_gps_display()
        
        # Update every second
        Clock.schedule_interval(self.update_time, 1.0)
    
    def create_gps_display(self):
        """Create the GPS data display"""
        for key, value in self.gps_data.items():
            # Label for the measurement name
            name_label = Label(
                text=key,
                font_size='16sp',
                bold=True,
                color=(0.8, 0.8, 0.8, 1),
                size_hint_y=None,
                height='40dp'
            )
            
            # Label for the value
            value_label = Label(
                text=value,
                font_size='16sp',
                color=(0, 1, 0, 1),  # Green text
                size_hint_y=None,
                height='40dp'
            )
            
            self.add_widget(name_label)
            self.add_widget(value_label)
            self.labels[key] = value_label
    
    def update_time(self, dt):
        """Update the last update time"""
        current_time = datetime.now().strftime("%H:%M:%S")
        if 'Last Update' in self.labels:
            self.labels['Last Update'].text = current_time

class ARMERDataWidget(GridLayout):
    """ARMER data display widget"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cols = 1
        self.padding = 10
        self.spacing = 5
        
        # Header
        header = Label(
            text='ARMER Sites Near You',
            font_size='20sp',
            bold=True,
            color=(1, 1, 1, 1),
            size_hint_y=None,
            height='50dp'
        )
        self.add_widget(header)
        
        # Sample ARMER data
        sites = [
            "Minneapolis Metro | Hennepin | 15.2 mi | NE | NAC 293",
            "St. Paul Capitol | Ramsey | 18.7 mi | E | NAC 293", 
            "Anoka County | Anoka | 22.1 mi | N | NAC 293",
            "Dakota County | Dakota | 25.8 mi | S | NAC 293"
        ]
        
        for site in sites:
            site_label = Label(
                text=site,
                font_size='14sp',
                color=(0.9, 0.9, 0.9, 1),
                size_hint_y=None,
                height='40dp',
                text_size=(None, None)
            )
            self.add_widget(site_label)

class TowerWitchKivyApp(App):
    """TowerWitch-K v2.0 Kivy application"""
    
    def build(self):
        # Create main tabbed interface
        tab_panel = TabbedPanel(
            do_default_tab=False,
            background_color=(0.2, 0.2, 0.2, 1),
            tab_width=120
        )
        
        # GPS Tab
        gps_tab = TabbedPanelItem(text='GPS')
        gps_tab.add_widget(GPSDataWidget())
        tab_panel.add_widget(gps_tab)
        
        # Grids Tab
        grids_tab = TabbedPanelItem(text='Grids')
        grids_content = Label(
            text='Grid Systems\n\nMaidenhead: EN34wx\nUTM: 15T 482517E 4983233N\nMGRS: 15TWM8251783233\nUSNG: 15TWM8251783233',
            font_size='16sp',
            color=(1, 1, 1, 1)
        )
        grids_tab.add_widget(grids_content)
        tab_panel.add_widget(grids_tab)
        
        # ARMER Tab
        armer_tab = TabbedPanelItem(text='ARMER')
        armer_tab.add_widget(ARMERDataWidget())
        tab_panel.add_widget(armer_tab)
        
        # Skywarn Tab
        skywarn_tab = TabbedPanelItem(text='Skywarn')
        skywarn_content = Label(
            text='Skywarn Weather Repeaters\n\nW0MN - Minneapolis\nKC0IOX - St. Cloud\nW0MSF - Mankato',
            font_size='16sp',
            color=(1, 1, 1, 1)
        )
        skywarn_tab.add_widget(skywarn_content)
        tab_panel.add_widget(skywarn_tab)
        
        # Amateur Tab
        amateur_tab = TabbedPanelItem(text='Amateur')
        amateur_content = Label(
            text='Amateur Radio Repeaters\n\n2m: 146.940 MHz\n70cm: 442.950 MHz\n1.25m: 224.180 MHz',
            font_size='16sp', 
            color=(1, 1, 1, 1)
        )
        amateur_tab.add_widget(amateur_content)
        tab_panel.add_widget(amateur_tab)
        
        return tab_panel

if __name__ == '__main__':
    TowerWitchKivyApp().run()