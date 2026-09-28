"""Embedded thumbnails are real, hash-bound PNG members."""

import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shellflow.package_io import PackageError, file_records
from shellflow.package_preview import PREVIEW_PATH, add_preview, validate_preview


def _chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))


def png():
    pixels = zlib.compress(b"\x00\xff\x00\x00\xff")
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
            + _chunk(b"IDAT", pixels) + _chunk(b"IEND", b""))


def test_embedded_preview_roundtrip_and_resigned_corruption():
    import pytest
    manifest, files = {}, {}
    add_preview(manifest, files, png())
    manifest["files"] = file_records(files)
    assert "preview" not in manifest
    assert manifest["files"][PREVIEW_PATH] == {"bytes": len(png()),
                                               "sha256": hashlib.sha256(png()).hexdigest()}
    validate_preview(json.loads(json.dumps(manifest)), dict(files))

    missing = dict(files)
    missing.pop(PREVIEW_PATH)
    with pytest.raises(PackageError):
        validate_preview(manifest, missing)

    corrupt = dict(files)
    corrupt[PREVIEW_PATH] = png()[:-1] + b"X"
    resigned = json.loads(json.dumps(manifest))
    resigned["files"] = file_records(corrupt)
    with pytest.raises(PackageError, match="PNG"):
        validate_preview(resigned, corrupt)


def test_bad_preview_metadata_or_non_png_rejected():
    import pytest
    with pytest.raises(PackageError):
        add_preview({}, {}, b"not a png")
    broken_pixels = (b"\x89PNG\r\n\x1a\n"
                     + _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
                     + _chunk(b"IDAT", b"invalid compressed pixels")
                     + _chunk(b"IEND", b""))
    with pytest.raises(PackageError, match="decoded"):
        add_preview({}, {}, broken_pixels)
    manifest, files = {}, {}
    add_preview(manifest, files, png())
    manifest["files"] = {"other.png": file_records(files)[PREVIEW_PATH]}
    with pytest.raises(PackageError, match="inventory"):
        validate_preview(manifest, files)
    manifest["files"] = file_records(files)
    manifest["preview"] = "not part of this schema"
    with pytest.raises(PackageError, match="top-level"):
        validate_preview(manifest, files)
