#!/usr/bin/env python3
"""CLI for the optional simulation producer; install the project's sim extra."""
from pathlib import Path
import sys

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, 'reconfigure'):
        stream.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
try:
    from shellflow.simulation import main
except ImportError as error:
    import json
    print(json.dumps({'ok': False, 'error': str(error), 'action': 'Install the sim extra in the Python environment running this command.'}))
    raise SystemExit(2)

if __name__ == '__main__':
    raise SystemExit(main())
