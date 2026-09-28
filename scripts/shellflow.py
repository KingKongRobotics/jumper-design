#!/usr/bin/env python3
"""Run the repository CLI without installing a Python package."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from shellflow.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
