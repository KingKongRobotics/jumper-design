#!/usr/bin/env python3
"""Import the user-maintained Jumper URDF into a new robot profile."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, 'reconfigure'):
        stream.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from shellflow.robot_import import import_jumper


def main(argv=None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path,
                        help='Directory containing urdf/jumper.urdf and meshes/visual/*.stl')
    parser.add_argument('--output', type=Path, default=root / 'robots/jumper')
    parser.add_argument('--legacy-profile', type=Path,
                        default=root / 'robots/jumper-v1-6/profile.json')
    parser.add_argument('--source-audit', required=True, type=Path,
                        help='Current-source SHA-bound link/mesh comparison and seam audit')
    args = parser.parse_args(argv)
    try:
        result = import_jumper(args.source, args.output, legacy_profile=args.legacy_profile,
                               source_audit=args.source_audit)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, ImportError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
