"""Bounded, deterministic transport for portable data-only content packages."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
import zlib


class PackageError(ValueError):
    """A content package violates the public interchange contract."""


@dataclass(frozen=True)
class Limits:
    archive_bytes: int = 512 * 1024 * 1024
    expanded_bytes: int = 1024 * 1024 * 1024
    file_bytes: int = 256 * 1024 * 1024
    files: int = 4096
    manifest_bytes: int = 4 * 1024 * 1024


DEFAULT_LIMITS = Limits()
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}


def safe_path(name: str) -> str:
    """Portable POSIX path, with identical meaning on Windows and Unix."""
    if (not isinstance(name, str) or not name or len(name) > 512
            or unicodedata.normalize("NFC", name) != name
            or any(ord(c) < 32 or ord(c) == 127 for c in name)
            or any(c in name for c in '\\:*?"<>|')):
        raise PackageError(f"Invalid portable path: {name!r}")
    for part in name.split("/"):
        if (part in ("", ".", "..") or part.endswith((" ", "."))
                or part.split(".")[0].upper() in _RESERVED):
            raise PackageError(f"Invalid portable path: {name!r}")
    return name


def _paths(names):
    seen = {}
    for name in names:
        key = safe_path(name).casefold()
        if key in seen:
            raise PackageError(f"Duplicate/case-colliding path: {name}, {seen[key]}")
        seen[key] = name
    for key, name in seen.items():
        parts = key.split("/")
        if any("/".join(parts[:i]) in seen for i in range(1, len(parts))):
            raise PackageError(f"File/directory path conflict: {name}")


def json_object(data: bytes, label: str = "manifest", *, limit: int = DEFAULT_LIMITS.manifest_bytes) -> dict:
    if len(data) > limit:
        raise PackageError(f"{label} exceeds JSON byte budget")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise PackageError(f"Duplicate JSON key in {label}: {key}")
            result[key] = value
        return result

    def constant(value):
        raise PackageError(f"Non-finite JSON number in {label}: {value}")

    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise PackageError(f"Non-finite JSON number in {label}")
        return result

    try:
        result = json.loads(data.decode("utf-8-sig"), object_pairs_hook=pairs,
                            parse_constant=constant, parse_float=finite_float)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise PackageError(f"Invalid {label}: {error}") from error
    if not isinstance(result, dict):
        raise PackageError(f"{label} must be a JSON object")
    return result


def parse_xml(data: bytes) -> ET.Element:
    if not isinstance(data, bytes):
        data = str(data).encode("utf-8")
    try:
        # Interchange XML is UTF-8; this also prevents UTF-16 DTD bypasses.
        source = data.decode("utf-8-sig")
        if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", source, re.I):
            raise PackageError("XML DTD and entities are forbidden")
        declaration = re.match(r'\s*<\?xml[^?]*encoding=[\'"]([^\'"]+)', source, re.I)
        if declaration and declaration.group(1).lower().replace("-", "") != "utf8":
            raise PackageError("Package XML must use UTF-8")
        return ET.fromstring(source)
    except (UnicodeError, ET.ParseError, RecursionError) as error:
        raise PackageError(f"Invalid package XML: {error}") from error


def read_archive(path: Path, *, limits: Limits = DEFAULT_LIMITS) -> dict[str, bytes]:
    path = Path(path)
    if path.stat().st_size > limits.archive_bytes:
        raise PackageError("Archive exceeds compressed byte budget")
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > limits.files:
                raise PackageError("Archive exceeds entry count budget")
            files = [item for item in entries if not item.is_dir()]
            _paths(item.filename for item in files)
            directory_keys = set()
            file_keys = {item.filename.casefold() for item in files}
            for item in entries:
                if item.orig_filename != item.filename:
                    raise PackageError("ZIP filename contains a truncated NUL or noncanonical name")
                name = item.filename.rstrip("/") if item.is_dir() else item.filename
                safe_path(name)
                mode = item.external_attr >> 16
                if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise PackageError(f"Archive links/special files are forbidden: {name}")
                if item.flag_bits & 1 or item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise PackageError(f"Encrypted/unsupported ZIP entry: {name}")
                if item.is_dir():
                    key = name.casefold()
                    parents = key.split("/")
                    if (key in directory_keys or key in file_keys
                            or any("/".join(parents[:i]) in file_keys for i in range(1, len(parents)))):
                        raise PackageError(f"Duplicate/conflicting directory: {name}")
                    directory_keys.add(key)
                if item.file_size > limits.file_bytes:
                    raise PackageError(f"Archive entry exceeds byte budget: {name}")
            if sum(item.file_size for item in entries) > limits.expanded_bytes:
                raise PackageError("Archive exceeds expanded byte budget")
            result = {}
            for item in files:
                with archive.open(item) as stream:
                    data = stream.read(min(item.file_size, limits.file_bytes) + 1)
                if len(data) != item.file_size:
                    raise PackageError(f"Archive entry size mismatch: {item.filename}")
                result[item.filename] = data
            return result
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError, zlib.error) as error:
        raise PackageError(f"Invalid ZIP archive: {error}") from error


def file_records(files: dict[str, bytes]) -> dict:
    _paths(files)
    return {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in sorted(files.items())}


def validate_files(manifest: dict, files: dict[str, bytes], manifest_name: str,
                   optional=()) -> None:
    _paths(files)
    records = manifest.get("files")
    if not isinstance(records, dict) or not records:
        raise PackageError("Manifest files must be a nonempty path-to-hash object")
    _paths(records)
    if manifest_name in records:
        raise PackageError("Manifest must not hash itself")
    if manifest_name not in files:
        raise PackageError(f"Missing manifest: {manifest_name}")
    undeclared = set(files) - set(records) - {manifest_name, *optional}
    if undeclared:
        raise PackageError(f"Undeclared files: {sorted(undeclared)}")
    for name, record in records.items():
        if (not isinstance(record, dict) or type(record.get("bytes")) is not int
                or record["bytes"] < 0 or not isinstance(record.get("sha256"), str)
                or not re.fullmatch(r"[a-f0-9]{64}", record["sha256"])):
            raise PackageError(f"Invalid file hash record: {name}")
        if name not in files:
            raise PackageError(f"Missing declared file: {name}")
        data = files[name]
        if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise PackageError(f"File size/SHA256 mismatch: {name}")


def write_archive(output: Path, files: dict[str, bytes], *, limits: Limits = DEFAULT_LIMITS) -> Path:
    """Write once, with fixed metadata. Never overwrite an existing delivery."""
    output = Path(output)
    _paths(files)
    if (len(files) > limits.files or sum(map(len, files.values())) > limits.expanded_bytes
            or any(len(data) > limits.file_bytes for data in files.values())):
        raise PackageError("Output exceeds package resource budget")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".content-", suffix=".zip", dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for name, data in sorted(files.items()):
                    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | 0o644) << 16
                    archive.writestr(info, data)
        if Path(temporary).stat().st_size > limits.archive_bytes:
            raise PackageError("Output exceeds compressed byte budget")
        # Exclusive destination creation also handles a competing writer.
        with output.open("xb") as target, open(temporary, "rb") as source:
            try:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    target.write(block)
            except BaseException:
                target.close()
                output.unlink()
                raise
        return output
    finally:
        Path(temporary).unlink(missing_ok=True)


def extract_files(files: dict[str, bytes], destination: Path) -> Path:
    """Extract validated bytes to a new directory, publishing only at completion."""
    _paths(files)
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError(f"Import destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".import-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "package"
        staging.mkdir()
        for name, data in files.items():
            path = staging.joinpath(*name.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        staging.rename(destination)
    return destination
