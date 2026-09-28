"""Validate and publish one .skin or .map to the standard content library."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from shellflow.content_library import publish

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--preview', type=Path)
    parser.add_argument('--library', type=Path, default=ROOT / 'library')
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(publish(args.package, args.library, args.profile, preview=args.preview), ensure_ascii=False))
