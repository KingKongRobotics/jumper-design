"""Standard-library PNG writer for grayscale and RGB images.

Procedural assets must work on any machine, so terrain height maps, wood
floors, and fabric textures use this module without Pillow or NumPy.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

__all__ = ["write_gray", "write_rgb"]


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


def _write(path: Path, width: int, height: int, color_type: int, raw: bytes) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)))
        fh.write(_chunk(b"IDAT", zlib.compress(raw, 9)))
        fh.write(_chunk(b"IEND", b""))


def write_gray(path: Path, rows) -> None:
    """Write 8-bit grayscale rows of 0..255 values."""
    raw = bytearray()
    for row in rows:
        raw.append(0)                                    # filter type 0
        raw.extend(max(0, min(255, int(v))) for v in row)
    _write(path, len(rows[0]), len(rows), 0, bytes(raw))


def write_rgb(path: Path, rows) -> None:
    """Write 8-bit RGB rows of (r, g, b) values."""
    raw = bytearray()
    for row in rows:
        raw.append(0)
        for r, g, b in row:
            raw += bytes((max(0, min(255, int(r))), max(0, min(255, int(g))),
                          max(0, min(255, int(b)))))
    _write(path, len(rows[0]), len(rows), 2, bytes(raw))
