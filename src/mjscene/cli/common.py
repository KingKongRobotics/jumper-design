"""Shared CLI helpers: paths, colors, tolerant spec loading, and scene indexes.

**Workspace layout** (read workspace/README.md before changing this convention):

    workspace/<scene_name>/
        scene.json          Scene description edited by the author or AI
        assets/             Author-provided meshes, textures, and height maps
        build/              Compiled scene.xml, scene.viewer.json, and assets/

The framework directories (mjscene/, web/, schemas/, ai/) are read-only for
scene generation. All generated files belong in `workspace/<scene_name>/`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

__all__ = ["ROOT", "WORKSPACE_DIR", "SPEC_FILENAME", "BUILD_DIRNAME", "ASSETS_DIRNAME",
           "OK", "BAD", "WARN", "INFO", "colour", "load_spec", "find_specs",
           "scene_dir_of", "build_dir_of", "print_issues", "write_catalog"]


# The installed package may live in site-packages. CLI workspaces belong to
# the invocation directory, never to the installed library directory.
ROOT = Path.cwd()
WORKSPACE_DIR = ROOT / "workspace"

SPEC_FILENAME = "scene.json"
BUILD_DIRNAME = "build"
ASSETS_DIRNAME = "assets"

OK, BAD, WARN, INFO = "\033[32m✓\033[0m", "\033[31m✗\033[0m", "\033[33m!\033[0m", "·"


def colour(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def load_spec(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as first:
        cleaned = re.sub(r"(?m)^\s*//.*$", "", text)             # // line comments
        cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.S)  # /* block */
        cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)         # trailing commas
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            raise SystemExit(f"{BAD} {path} is not valid JSON: {first}") from first
        print(f"{WARN} {path.name}: comments or trailing commas were tolerated; please clean up the JSON")
        return data


def scene_dir_of(spec_path: Path) -> Path:
    """The scene folder a spec belongs to — everything it produces goes here."""
    return spec_path.resolve().parent


def build_dir_of(spec_path: Path) -> Path:
    return scene_dir_of(spec_path) / BUILD_DIRNAME


def find_specs(paths: list[str], use_all: bool) -> list[Path]:
    """Resolve CLI arguments to spec files.

    Accepts a scene name (`warehouse`), a scene folder, or a path to a
    `scene.json`. With no arguments it takes every scene in the workspace.
    """
    if use_all or not paths:
        return sorted(WORKSPACE_DIR.glob(f"*/{SPEC_FILENAME}"))
    out: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_file():
            out.append(path)
        elif path.is_dir():
            spec = path / SPEC_FILENAME
            out.append(spec if spec.exists() else path)
        elif (WORKSPACE_DIR / p / SPEC_FILENAME).exists():     # bare scene name
            out.append(WORKSPACE_DIR / p / SPEC_FILENAME)
        else:
            out.append(path)                                    # report as missing later
    return out


def print_issues(issues) -> None:
    for i in issues:
        mark = BAD if i.level == "error" else WARN
        print(f"  {mark} {colour(i.path or '<root>', '36')}: {i.message}")
        if i.hint:
            print(f"      → {i.hint}")


def write_catalog(workspace: Path = WORKSPACE_DIR) -> Path:
    """Rebuild workspace/index.json — the catalogue the web viewer reads."""
    entries = []
    for sidecar in sorted(workspace.glob(f"*/{BUILD_DIRNAME}/scene.viewer.json")):
        try:
            v = json.loads(sidecar.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        scene = sidecar.parent.parent.name
        entries.append({"name": v.get("name", scene),
                        "title": v.get("title", scene),
                        "description": v.get("description", ""),
                        "tags": v.get("tags", []),
                        "path": f"{scene}/{BUILD_DIRNAME}/scene.viewer.json"})
    workspace.mkdir(parents=True, exist_ok=True)
    index = workspace / "index.json"
    index.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    return index
