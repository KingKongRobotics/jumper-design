"""Command-line entry point: `python -m mjscene <command>`.

    new / build / validate / list / schema / prompt / doctor
"""

from __future__ import annotations

from .app import build_parser, main

__all__ = ["main", "build_parser"]
