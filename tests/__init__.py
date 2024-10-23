# tests/__init__.py
"""
Test suite for the Mac Computer Control system.
"""

import os
import sys

# Add src directory to Python path for testing
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))