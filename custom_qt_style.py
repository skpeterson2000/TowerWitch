#!/usr/bin/env python3
"""
Custom Qt Style for TowerWitch - Allows custom tab colors while maintaining system appearance
"""

from PyQt5.QtWidgets import QProxyStyle, QStyleOption, QStyle
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QColor, QPalette

class TowerWitchStyle(QProxyStyle):
    """Custom Qt style that respects our color overrides while maintaining system look"""
    
    def __init__(self, base_style=None):
        super().__init__(base_style)
        self.custom_tab_colors = {}
        self.debug_enabled = True
        
    def set_tab_colors(self, widget_name, colors):
        """Set custom colors for specific tab widgets"""
        self.custom_tab_colors[widget_name] = colors
        if self.debug_enabled:
            print(f"[TowerWitchStyle] Set colors for {widget_name}: {[c.name() for c in colors]}")
    
    def drawControl(self, element, option, painter, widget=None):
        """Override tab drawing to apply custom colors"""
        
        if element == QStyle.CE_TabBarTab and widget is not None:
            # Check if this widget has custom colors
            widget_name = widget.objectName() if widget else None
            parent_name = widget.parent().objectName() if widget and widget.parent() else None
            
            if self.debug_enabled and (widget_name or parent_name):
                print(f"[TowerWitchStyle] Drawing tab for widget: {widget_name}, parent: {parent_name}")
            
            # Look for custom colors for this widget
            colors = None
            if parent_name and parent_name in self.custom_tab_colors:
                colors = self.custom_tab_colors[parent_name]
            elif widget_name and widget_name in self.custom_tab_colors:
                colors = self.custom_tab_colors[widget_name]
            
            if colors and hasattr(option, 'tabIndex') and option.tabIndex < len(colors):
                # Apply custom color for this tab
                color = colors[option.tabIndex]
                
                if self.debug_enabled:
                    print(f"[TowerWitchStyle] Applying color {color.name()} to tab {option.tabIndex}")
                
                # Save original palette
                original_palette = option.palette
                
                # Create custom palette with our color
                custom_palette = QPalette(original_palette)
                custom_palette.setColor(QPalette.Button, color)
                custom_palette.setColor(QPalette.Window, color)
                custom_palette.setColor(QPalette.Base, color)
                custom_palette.setColor(QPalette.AlternateBase, color)
                
                # Apply custom palette
                option.palette = custom_palette
                
                # Draw with custom colors
                super().drawControl(element, option, painter, widget)
                
                # Restore original palette
                option.palette = original_palette
                return
        
        # Default drawing for everything else
        super().drawControl(element, option, painter, widget)
    
    def drawPrimitive(self, element, option, painter, widget=None):
        """Override primitive drawing if needed"""
        super().drawPrimitive(element, option, painter, widget)

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        """Override style hints to ensure our customizations work"""
        if hint == QStyle.SH_TabBar_Alignment:
            return Qt.AlignLeft
        return super().styleHint(hint, option, widget, returnData)