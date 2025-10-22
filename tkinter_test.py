#!/usr/bin/env python3
"""Simple tkinter test"""

import tkinter as tk
from tkinter import ttk
import sys

def test_tkinter():
    """Test basic tkinter functionality"""
    print("🔍 Testing tkinter GUI system...")
    
    try:
        # Create root window
        root = tk.Tk()
        root.title("Tkinter Test")
        root.geometry("400x300")
        
        # Add a label
        label = tk.Label(root, text="If you see this window, tkinter is working!", 
                        font=('Arial', 12))
        label.pack(pady=20)
        
        # Add colored tabs test
        notebook = ttk.Notebook(root)
        
        # Test frame 1
        frame1 = ttk.Frame(notebook)
        notebook.add(frame1, text="🟣 Test Tab 1")
        
        # Test frame 2  
        frame2 = ttk.Frame(notebook)
        notebook.add(frame2, text="🔵 Test Tab 2")
        
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Add content to tabs
        ttk.Label(frame1, text="Purple test tab content", 
                 font=('Arial', 14)).pack(pady=50)
        ttk.Label(frame2, text="Blue test tab content", 
                 font=('Arial', 14)).pack(pady=50)
        
        # Close button
        ttk.Button(root, text="Close Test", 
                  command=root.destroy).pack(pady=10)
        
        print("✅ Tkinter window created successfully!")
        print("🎨 Test window should be visible now")
        
        # Run the GUI
        root.mainloop()
        
        print("👋 Test window closed")
        return True
        
    except Exception as e:
        print(f"❌ Tkinter test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_tkinter()
    if success:
        print("✅ Tkinter GUI system is working!")
    else:
        print("❌ Tkinter GUI system has problems")
        sys.exit(1)