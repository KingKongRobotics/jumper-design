"""Check whether MuJoCo accepts MJCF and map errors back to scene specs.

Errors include the XML line, related element, and a likely fix so authors can
identify the field to change without reading a MuJoCo stack trace.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .runtime import HAVE_MUJOCO, MUJOCO_ERROR, mujoco

__all__ = ["ModelCheck", "check_model"]


@dataclass
class ModelCheck:
    ok: bool
    error: str = ""
    error_line: int | None = None
    error_element: str = ""
    hint: str = ""
    stats: dict = field(default_factory=dict)


_LINE_RE = re.compile(r"line\s+(\d+)", re.I)
_NAME_RE = re.compile(r'(?:name|geom1|geom2|body1|body2|mesh|material|hfield)\s*=\s*"([^"]+)"')

# Frequent MuJoCo compile errors -> what to change in the spec.
# The patterns are matched against real MuJoCo 3.x messages — don't paraphrase
# them from memory, run the failure and copy the wording (see tests).
_HINTS: list[tuple[str, str]] = [
    (r"material '.*' not found|unknown material",
     "This material is missing from materials; run `mjscene list materials` for presets"),
    (r"mesh '.*' not found|unknown mesh",
     "The mesh referenced by shape='mesh' is undeclared; add {name, file} to top-level meshes"),
    (r"geom '.*' not found in collision",
     "The geom in contacts.pairs does not exist; object geom names use '<object_name>_geom' and the ground is 'ground'"),
    (r"repeated name", "MJCF names must be globally unique; rename or remove the duplicate"),
    (r"mass and inertia of moving bodies must be larger than mjMINVAL",
     "A moving body has zero mass; set mass>0 or density>0, or add at least one geom"),
    (r"inertia must satisfy A \+ B >= C",
     "The inertia tensor is invalid. Check shape='mesh' geometry (repair it or reduce maxhullvert)"
     " or a handwritten <inertial> in raw_mjcf"),
    (r"Error opening file|resource not found|could not open file",
     "Resource file missing; check the relative meshes[].file or ground.elevation_file path"
     " and confirm the file was copied into <scene>/assets/"),
    (r"could not find model|attach",
     "Robot attach failed; robots[].file must point to complete MJCF with top-level"
     " <mujoco> and <worldbody>, and MuJoCo must be version 3.2 or newer"),
    (r"hfield", "Invalid height field; check ground.height_scale > 0 and assets/terrain.png"),
    (r"keyframe", "The keyframe degree-of-freedom count does not match the model"),
    (r"Error: (\w+) attribute", "Invalid attribute name or value; check the related spec field"),
]


def _hint_for(msg: str) -> str:
    for pattern, hint in _HINTS:
        if re.search(pattern, msg, re.I):
            return hint
    return ""


def check_model(xml_path: Path | str) -> ModelCheck:
    if not HAVE_MUJOCO:
        return ModelCheck(ok=False, error=f"The mujoco Python package is not installed ({MUJOCO_ERROR})",
                          hint="Install it with `pip install mujoco` or use the project .venv")
    xml_path = Path(xml_path)
    try:
        model = mujoco.MjModel.from_xml_path(str(xml_path))
    except Exception as exc:
        msg = str(exc).strip()
        line = None
        element = ""
        m = _LINE_RE.search(msg)
        if m:
            line = int(m.group(1))
            element = _element_at_line(xml_path, line)
        return ModelCheck(ok=False, error=msg, error_line=line, error_element=element,
                          hint=_hint_for(msg))
    stats = {
        "nbody": model.nbody, "ngeom": model.ngeom, "nq": model.nq, "nv": model.nv,
        "nu": model.nu, "nlight": model.nlight, "nmat": model.nmat, "ntex": model.ntex,
        "nmesh": model.nmesh, "nhfield": model.nhfield, "ncam": model.ncam,
        "njnt": model.njnt, "extent": round(float(model.stat.extent), 3),
        "timestep": float(model.opt.timestep),
    }
    return ModelCheck(ok=True, stats=stats)


def _element_at_line(xml_path: Path, line: int) -> str:
    """Best-effort: the nearest name="..." at or above the offending line."""
    try:
        lines = xml_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    # Prefer every name-ish attribute on the offending line, then search upwards.
    if 0 < line <= len(lines):
        hits = _NAME_RE.findall(lines[line - 1])
        if hits:
            return ", ".join(hits)
    for i in range(min(line, len(lines)) - 2, max(-1, line - 12), -1):
        m = _NAME_RE.search(lines[i])
        if m:
            return m.group(1)
    return ""
