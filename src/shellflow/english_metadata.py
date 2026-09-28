"""Producer-side language gate for public package metadata.

Consumers still accept historical packages and Unicode input. This gate only
applies when producing a new public .skin or .map archive.
"""

from __future__ import annotations

import re

from .package_io import PackageError


_HAN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\U00020000-\U0003134f]")


def require_english_text(value: str, field: str, *, allow_empty: bool = False) -> None:
    """Reject Han text in newly authored public display fields."""
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise PackageError(f"{field} must be English text for a new public package")
    if not value.strip() and allow_empty:
        return
    if _HAN.search(value):
        raise PackageError(f"{field} must be English text for a new public package; translate the display metadata before export")
