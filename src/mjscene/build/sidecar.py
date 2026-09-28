"""Generate `scene.viewer.json` rendering hints for the web viewer.

These fields affect rendering only: sky gradient, fog, exposure, initial
camera, and UI defaults. Physics comes entirely from scene.xml. The viewer
falls back to mjModel introspection and defaults when sidecar data is missing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import library
from . import environment

if TYPE_CHECKING:
    from .compiler import Compiler

__all__ = ["build_viewer"]


def build_viewer(c: "Compiler") -> dict:
    """Collect the rendering hints the web viewer reads alongside scene.xml."""
    sky = environment.sky_settings(c)
    lg = environment.lighting_settings(c)
    v = c.spec.get("viewer") or {}
    p = {**library.DEFAULT_PHYSICS, **(c.spec.get("physics") or {})}
    ground = c.spec.get("ground") or {}
    extent = max(list(ground.get("size", [10, 10]))[:2] + [4.0])
    cam_pos = v.get("camera_pos") or [extent * 0.55, -extent * 0.7, extent * 0.45]
    cam_target = v.get("camera_target") or [0.0, 0.0, 0.4]
    return {
        "schemaVersion": 1,
        "name": c.spec.get("name", "scene"),
        "title": c.spec.get("title") or c.spec.get("name", "scene"),
        "description": c.spec.get("description", ""),
        "tags": c.spec.get("tags") or [],
        "model": "scene.xml",
        "assets": list(c.assets),
        "sky": {"type": "gradient", "top": list(sky["top"]), "bottom": list(sky["bottom"]),
                "horizon": 0.42},
        "fog": {"enabled": bool(sky["fog_enabled"]), "color": list(sky["haze"]),
                "start": sky["fog"][0], "end": sky["fog"][1]},
        "render": {
            "shadows": v.get("shadows") if v.get("shadows") is not None else lg["shadows"],
            "shadowMapSize": min(4096, lg["shadow_size"]),
            "toneMapping": "aces",
            "exposure": v.get("exposure", 1.05),
            "ambient": list(lg["ambient"]),
            "groundGrid": False,
        },
        "camera": {"mode": "orbit", "pos": cam_pos, "target": cam_target,
                   "fovy": v.get("fovy", 50), "near": 0.02, "far": max(200.0, extent * 12)},
        "physics": {"timestep": p["timestep"], "realtime": v.get("realtime", 1.0)},
        "ui": {"paused": bool(v.get("paused", False)),
               "showContacts": bool(v.get("show_contacts", False)),
               "showFrames": False},
        "objects": c.object_index,
        "notes": c.notes,
    }
