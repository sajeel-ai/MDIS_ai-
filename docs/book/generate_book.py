#!/usr/bin/env python3
"""Cognate AI — Complete Technical Book Generator (entry point)."""
import subprocess, sys, os
from pathlib import Path

# Run the actual generator parts
parts_dir = Path(__file__).parent / "_parts"
result = subprocess.run(
    [sys.executable, str(parts_dir / "main.py")],
    cwd=str(parts_dir),
    capture_output=False
)
sys.exit(result.returncode)
