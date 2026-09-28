"""Resolve formal library defaults by stable content identity."""

from __future__ import annotations

import json
from pathlib import Path


DEFAULT_SKIN_ID = "jumper-original"


def default_skin_path(root: Path) -> Path:
    """Find the selected default skin without assuming a display filename."""
    library = root / "library" / "skins"
    index = json.loads((library / "index.json").read_text(encoding="utf-8"))
    matches = [item for item in index["items"] if item["id"] == DEFAULT_SKIN_ID]
    if len(matches) != 1:
        raise ValueError(f"Expected one default skin with ID {DEFAULT_SKIN_ID}")
    filename = matches[0]["file"]
    if not isinstance(filename, str) or Path(filename).name != filename or "/" in filename or "\\" in filename:
        raise ValueError("Unsafe default skin filename in library index")
    path = library / filename
    if not path.is_file():
        raise FileNotFoundError(f"Default skin listed in library index is missing: {path}")
    return path
