"""Check English-only repository text and public package metadata.

Historical source identifiers may use Unicode escapes to preserve exact lookup
semantics. Public package strings are decoded before checking, so escaping a
display title cannot bypass this gate. Binary engineering evidence is immutable.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import zipfile

HAN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\U00020000-\U0003134f]")
TEXT = {".py", ".md", ".json", ".xml", ".urdf", ".toml", ".yaml", ".yml", ".txt", ".csv", ".html", ".js", ".ts", ".css", ".sh", ".ps1", ".ini", ".cfg"}


def text_has_han(data: bytes, suffix: str, decoded_json: bool = False) -> bool:
    value = data.decode("utf-8-sig")
    if suffix == ".json" and decoded_json:
        value = json.dumps(json.loads(value), ensure_ascii=False)
    return bool(HAN.search(value))


def check_package(path: Path) -> list[str]:
    issues = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if HAN.search(name):
                issues.append(f"{path}: non-English member name")
            suffix = Path(name).suffix.lower()
            if suffix in TEXT and text_has_han(archive.read(name), suffix, True):
                issues.append(f"{path}:{name}: non-English package text")
    return issues


def audit(root: Path, require_packages: bool = False) -> dict:
    result = subprocess.run(["git", "-c", f"safe.directory={root.resolve().as_posix()}", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"], capture_output=True, check=True)
    names = sorted(set(result.stdout.decode("utf-8").split("\0")) - {""})
    issues, skipped, checked = [], [], 0
    ignored = subprocess.run(["git", "-c", f"safe.directory={root.resolve().as_posix()}", "-C", str(root), "ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--", "src", "scripts", "tests"], capture_output=True, check=True)
    for name in ignored.stdout.decode("utf-8").split("\0"):
        if name.endswith(".py"):
            issues.append(f"{name}: Python source excluded by Git ignore rules")
    for name in names:
        path = root / name
        if not path.is_file():
            continue  # Deleted tracked paths are not part of the candidate tree.
        if HAN.search(name):
            issues.append(f"{name}: non-English file name")
        suffix = path.suffix.lower()
        if suffix in {".skin", ".map"}:
            with path.open("rb") as stream:
                pointer = stream.read(80).startswith(b"version https://git-lfs.github.com/spec/v1")
            if pointer:
                skipped.append(name)
                if require_packages:
                    issues.append(f"{name}: LFS payload required")
            else:
                issues.extend(check_package(path))
                checked += 1
        elif suffix in TEXT or path.name in {".gitignore", ".gitattributes"}:
            try:
                if text_has_han(path.read_bytes(), suffix):
                    issues.append(f"{name}: non-English repository text")
            except UnicodeDecodeError:
                issues.append(f"{name}: expected UTF-8 text")
    return {"ok": not issues, "files_checked": len(names), "packages_checked": checked, "lfs_payloads_skipped": skipped, "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--require-packages", action="store_true")
    args = parser.parse_args()
    result = audit(args.root, args.require_packages)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
