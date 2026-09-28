#!/usr/bin/env python3
"""Check indexed and non-ignored working files without exposing matched values."""
from __future__ import annotations

import argparse
import codecs
import json
from pathlib import Path
import re
import subprocess
import sys

TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".ps1", ".sh", ".csv", ".xml"}
MACHINE_PATH = re.compile(r"(?i)(?<![\w])(?:[a-z]:[\\/][^\s\"'<>]+|/(?:Users|home)/[a-z0-9_.-]+(?:/|$))")
SECRET_TOKEN = re.compile(r"(?:\b(?:sk|ghp|github_pat|glpat)[_-][A-Za-z0-9_-]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
SECRET_ASSIGNMENT = re.compile(
    r'''(?ix)(?:[a-z0-9_]+_)?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)
    ["']?\s*[:=]\s*["']([^"'\r\n]{16,})["']''')
UNQUOTED_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:[a-z0-9_]+_)?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)"
    r"\s*[:=]\s*([A-Za-z0-9_./+=$%{}<>:-]{16,})(?=\s|$|[,;}])")
BEARER_VALUE = re.compile(r"(?i)\bbearer\s+([A-Za-z0-9_./+=$%{}<>:-]{20,})")
ENV_REFERENCE = re.compile(r"(?i)(?:\$\{|\$env:|^\$[a-z_][a-z0-9_]*$|%[a-z_][a-z0-9_]*%|\bos\.(?:getenv|environ)\b|^<[^>]+>$|^(?:YOUR_|REPLACE_|EXAMPLE_|PLACEHOLDER|UNSET))")
LFS_PREFIX = b"version https://git-lfs.github.com/spec/v1"
LFS_POINTER = re.compile(rb"\Aversion https://git-lfs\.github\.com/spec/v1\r?\n"
                         rb"oid sha256:([a-f0-9]{64})\r?\nsize (0|[1-9][0-9]*)\r?\n?\Z")
PREFIX_BYTES = 4096


def git(root: Path, *args: str, input_data: bytes | None = None) -> bytes:
    process = subprocess.run(["git", "-C", str(root), *args], input=input_data, capture_output=True, check=False)
    if process.returncode:
        raise RuntimeError("Git inspection failed")
    return process.stdout


def lfs_attributes(root: Path, names: set[str], cached: bool = False) -> dict[str, bool]:
    if not names:
        return {}
    payload = b"".join(name.encode("utf-8") + b"\x00" for name in sorted(names))
    flags = ("--cached",) if cached else ()
    data = git(root, "check-attr", "-z", *flags, "filter", "--stdin", input_data=payload)
    fields = data.split(b"\x00")
    if fields[-1:] == [b""]:
        fields.pop()
    if len(fields) % 3:
        raise RuntimeError("Git attribute inspection returned invalid output")
    return {fields[i].decode("utf-8"): fields[i + 2] == b"lfs" for i in range(0, len(fields), 3)}


def line_findings(line: str, number: int) -> list[tuple[str, int]]:
    result = set()
    if MACHINE_PATH.search(line):
        result.add(("machine_absolute_path", number))
    if SECRET_TOKEN.search(line):
        result.add(("suspected_credential", number))
    for pattern in (SECRET_ASSIGNMENT, UNQUOTED_SECRET_ASSIGNMENT, BEARER_VALUE):
        for match in pattern.finditer(line):
            if not ENV_REFERENCE.search(match.group(1)):
                result.add(("suspected_credential", number))
    return sorted(result)


def text_encoding(prefix: bytes) -> str | None:
    if prefix.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        return "utf-32"
    if prefix.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    if b"\x00" in prefix:
        return None
    try:
        codecs.getincrementaldecoder("utf-8-sig")().decode(prefix, final=False)
    except UnicodeDecodeError:
        return None
    return "utf-8-sig"


def working_lfs_findings(path: Path, prefix: bytes) -> list[tuple[str, int]]:
    """Skip large binary payloads; stream text so LFS cannot conceal credentials."""
    encoding = text_encoding(prefix)
    if encoding is None:
        return []
    result = []
    try:
        with path.open("r", encoding=encoding) as stream:
            for number, line in enumerate(stream, 1):
                result.extend(line_findings(line, number))
    except UnicodeDecodeError:
        # A binary payload may happen to begin with a valid UTF-8 header.
        pass
    return result


def text_findings(data: bytes) -> list[tuple[str, int]]:
    try:
        if data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
            text = data.decode("utf-32")
        elif data.startswith((b"\xff\xfe", b"\xfe\xff")):
            text = data.decode("utf-16")
        elif b"\x00" in data:
            return []
        else:
            text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return []
    result = set()
    for number, line in enumerate(text.splitlines(), 1):
        result.update(line_findings(line, number))
    return sorted(result)


def audit(root: Path, max_file_bytes: int) -> dict:
    root = root.resolve()
    tracked = {p.decode("utf-8") for p in git(root, "ls-files", "--cached", "-z").split(b"\x00") if p}
    untracked = {p.decode("utf-8") for p in git(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\x00") if p}
    candidates = tracked | untracked
    working_lfs = lfs_attributes(root, candidates)
    indexed_lfs = lfs_attributes(root, tracked, cached=True)
    lfs_names = {name for name in candidates if working_lfs.get(name) or indexed_lfs.get(name)}
    findings = []
    scanned_versions = 0
    lfs_working_tree_bytes = 0
    lfs_index_files_checked = 0
    for name in sorted(candidates):
        path = root / name
        if path.is_symlink():
            findings.append({"file": name, "type": "symlink_requires_review", "source": "working_tree"})
            continue
        if not path.resolve().is_relative_to(root):
            findings.append({"file": name, "type": "path_outside_repository", "source": "working_tree"})
            continue
        versions = []
        if name in tracked:
            indexed_size = int(git(root, "cat-file", "-s", ":" + name).strip())
            # Check both attribute versions: adding an unstaged LFS rule must not
            # hide a raw binary already present in the Git index.
            if indexed_lfs.get(name) or working_lfs.get(name):
                lfs_index_files_checked += 1
                if indexed_size > PREFIX_BYTES:
                    findings.append({"file": name, "type": "lfs_index_not_pointer", "source": "index"})
                else:
                    data = git(root, "show", ":" + name)
                    if LFS_POINTER.fullmatch(data) is None:
                        findings.append({"file": name, "type": "lfs_index_not_pointer", "source": "index"})
                    versions.append(("index", data))
            elif indexed_size > max_file_bytes:
                findings.append({"file": name, "type": "file_exceeds_size_limit", "source": "index"})
            else:
                versions.append(("index", git(root, "show", ":" + name)))
        if path.is_file():
            if working_lfs.get(name):
                size = path.stat().st_size
                lfs_working_tree_bytes += size
                with path.open("rb") as stream:
                    prefix = stream.read(PREFIX_BYTES)
                if prefix.startswith(LFS_PREFIX) and (size > PREFIX_BYTES or LFS_POINTER.fullmatch(prefix) is None):
                    findings.append({"file": name, "type": "invalid_lfs_worktree_pointer", "source": "working_tree"})
                scanned_versions += 1
                for kind, line in working_lfs_findings(path, prefix):
                    findings.append({"file": name, "type": kind, "source": "working_tree", "line": line})
            elif path.stat().st_size > max_file_bytes:
                findings.append({"file": name, "type": "file_exceeds_size_limit", "source": "working_tree"})
            else:
                versions.append(("working_tree", path.read_bytes()))
        for source, data in versions:
            scanned_versions += 1
            for kind, line in text_findings(data):
                findings.append({"file": name, "type": kind, "source": source, "line": line})
    return {"passed": not findings, "candidate_files": len(tracked | untracked),
            "scanned_versions": scanned_versions, "max_file_bytes": max_file_bytes,
            "lfs_files": len(lfs_names), "lfs_working_tree_bytes": lfs_working_tree_bytes,
            "lfs_index_files_checked": lfs_index_files_checked,
            "scope": "index plus tracked working files and non-ignored untracked files; ignored local data is excluded",
            "findings": findings,
            "limitations": "Pattern-based publication check; does not establish licensing rights or guarantee absence of every secret. LFS binary payloads receive only a prefix probe; LFS index entries must be pointers. LFS remote object availability is not checked."}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--max-file-mib", type=float, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.max_file_mib <= 0:
        parser.error("--max-file-mib must be positive")
    try:
        report = audit(args.root, int(args.max_file_mib * 1024 * 1024))
    except (RuntimeError, OSError, ValueError):
        print("Publication check could not inspect repository files.", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Publication check: {'PASS' if report['passed'] else 'FAIL'}; {report['candidate_files']} candidate files")
        print(f"LFS: {report['lfs_files']} files; {report['lfs_working_tree_bytes']} working-tree bytes")
        for finding in report["findings"]:
            line = f":{finding['line']}" if "line" in finding else ""
            print(f"{finding['file']}{line}: {finding['type']} ({finding['source']})")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
