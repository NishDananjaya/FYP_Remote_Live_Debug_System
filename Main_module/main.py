#!/usr/bin/env python3
"""
WebSocket Server Data Monitor
Main entry point for the application
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.newgui import main

if __name__ == "__main__":
    main()