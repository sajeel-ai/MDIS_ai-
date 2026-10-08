"""Pytest Root Configuration."""

import sys
import os

# Add backend root directory to sys.path so 'import app' resolves cleanly
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
