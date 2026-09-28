"""MJCF attribute formatting and geometry helpers.

MuJoCo XML attributes use space-separated values. `fmt` converts Python
booleans, floats, and lists to MJCF text. `set_attrs` applies attributes and
skips None values so callers do not need repeated conditionals.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections.abc import Sequence

__all__ = ["fmt", "set_attrs", "norm", "cross", "look_at"]


def fmt(value: object) -> str:
    """MJCF attribute formatting: compact, no scientific notation surprises."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, float):
        s = f"{value:.6g}"
        return "0" if s in ("-0", "-0.0") else s
    if isinstance(value, (list, tuple)):
        return " ".join(fmt(v) for v in value)
    return str(value)


def set_attrs(el: ET.Element, **values: object) -> ET.Element:
    """Set MJCF attributes, skipping None. A trailing '_' escapes Python keywords."""
    for key, value in values.items():
        if value is None:
            continue
        el.set(key.rstrip("_"), fmt(value))
    return el


def norm(v: Sequence[float]) -> list[float]:
    """Normalise a 3-vector; degenerate input falls back to straight down."""
    n = math.sqrt(sum(c * c for c in v))
    return [c / n for c in v] if n > 1e-12 else [0.0, 0.0, -1.0]


def cross(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def look_at(pos: Sequence[float], target: Sequence[float]) -> list[float]:
    """Return MJCF `xyaxes` (camera right + up) for a camera at pos looking at target."""
    fwd = norm([target[i] - pos[i] for i in range(3)])
    up_world = [0.0, 0.0, 1.0]
    if abs(fwd[2]) > 0.999:                       # looking straight down/up
        up_world = [0.0, 1.0, 0.0]
    right = norm(cross(fwd, up_world))
    up = norm(cross(right, fwd))
    return right + up
