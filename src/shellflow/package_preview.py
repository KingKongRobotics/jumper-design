"""Embedded PNG preview contract shared by skin and map archives."""

from __future__ import annotations

import hashlib
import re
import struct
import zlib
from pathlib import Path

from .package_io import PackageError

PREVIEW_PATH = "preview/preview.png"
_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_HASH = re.compile(r"[a-f0-9]{64}\Z")


def validate_png(data: bytes) -> None:
    """Check PNG framing, required chunks, dimensions and every chunk CRC."""
    if not isinstance(data, bytes) or not data.startswith(_SIGNATURE):
        raise PackageError("Preview must contain PNG bytes")
    offset = len(_SIGNATURE)
    chunks = []
    image_data = []
    while offset + 12 <= len(data):
        size = struct.unpack_from(">I", data, offset)[0]
        end = offset + 12 + size
        if end > len(data):
            raise PackageError("Truncated preview PNG chunk")
        kind = data[offset + 4:offset + 8]
        if not re.fullmatch(rb"[A-Za-z]{4}", kind):
            raise PackageError("Invalid preview PNG chunk type")
        payload = data[offset + 8:offset + 8 + size]
        expected = struct.unpack_from(">I", data, end - 4)[0]
        if zlib.crc32(kind + payload) != expected:
            raise PackageError("Preview PNG chunk CRC mismatch")
        chunks.append(kind)
        if len(chunks) == 1:
            if kind != b"IHDR" or size != 13:
                raise PackageError("Preview PNG lacks a valid IHDR")
            width, height = struct.unpack_from(">II", payload)
            if not (0 < width <= 8192 and 0 < height <= 8192):
                raise PackageError("Preview PNG dimensions are invalid")
        elif kind == b"IHDR":
            raise PackageError("Duplicate preview PNG IHDR")
        if kind == b"IDAT":
            image_data.append(payload)
        offset = end
        if kind == b"IEND":
            if size or offset != len(data) or b"IDAT" not in chunks:
                raise PackageError("Preview PNG has invalid image data or trailing bytes")
            decoder = zlib.decompressobj()
            try:
                decoded = decoder.decompress(b"".join(image_data), 128 * 1024 * 1024 + 1)
            except zlib.error as exc:
                raise PackageError("Preview PNG image data cannot be decoded") from exc
            if (len(decoded) > 128 * 1024 * 1024 or not decoder.eof
                    or decoder.unused_data or decoder.unconsumed_tail):
                raise PackageError("Preview PNG image data is incomplete or oversized")
            return
    raise PackageError("Preview PNG lacks IEND")


def add_preview(manifest: dict, files: dict[str, bytes], preview: Path | bytes) -> None:
    """Embed a PNG; the caller then rebuilds the existing files inventory."""
    data = Path(preview).read_bytes() if isinstance(preview, Path) else preview
    validate_png(data)
    if PREVIEW_PATH in files:
        raise PackageError("Preview path already exists in package")
    files[PREVIEW_PATH] = data


def validate_preview(manifest: dict, files: dict[str, bytes]) -> None:
    """Validate the optional canonical PNG against the existing files inventory."""
    if "preview" in manifest:
        raise PackageError("Preview must use the files inventory, not a top-level field")
    records = manifest.get("files")
    if not isinstance(records, dict):
        raise PackageError("Missing file inventory")
    if PREVIEW_PATH not in files and PREVIEW_PATH not in records:
        return
    record = records.get(PREVIEW_PATH)
    if (not isinstance(record, dict) or set(record) != {"bytes", "sha256"}
            or type(record.get("bytes")) is not int or record["bytes"] <= 0
            or not isinstance(record.get("sha256"), str)
            or _HASH.fullmatch(record["sha256"]) is None):
        raise PackageError("Invalid preview file inventory record")
    data = files.get(PREVIEW_PATH)
    if data is None or len(data) != record["bytes"]:
        raise PackageError("Missing or incorrect embedded preview")
    if hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise PackageError("Preview SHA256 mismatch")
    validate_png(data)
