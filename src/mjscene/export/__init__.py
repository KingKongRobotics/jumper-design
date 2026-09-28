"""Export compiled scenes for downstream simulation and RL frameworks.

This layer reads **build/scene.xml**, the MJCF accepted by MuJoCo, instead of
the spec. It has no dependency on spec/build.

    from mjscene.export import export_scene, TARGETS
    export_scene("mjlab", "workspace/bedroom")
"""

from __future__ import annotations

from pathlib import Path

from . import mjcf_tools, mjlab, scene_package

__all__ = ["export_scene", "TARGETS", "mjlab", "scene_package", "mjcf_tools"]

# Target name -> (export function, short description)
TARGETS = {
    mjlab.TARGET: (mjlab.export,
                   "kk-rl-mjlab / mjlab: room entity plus one prop entity per movable object"),
    scene_package.TARGET: (scene_package.export,
                           "kk-scene-package/1: one <name>.map for BE UNLIMITED"
                           " experiments and kk-rl-mjlab simulation"),
}


def export_scene(target: str, scene_dir: Path | str, out_dir: Path | str | None = None,
                 *, legacy_zip: bool = False):
    """Export a compiled scene directory to the selected target."""
    if target not in TARGETS:
        raise KeyError(f"Unknown export target {target!r}; available: {', '.join(sorted(TARGETS))}")
    if target == scene_package.TARGET:
        return scene_package.export(scene_dir, out_dir, legacy_zip=legacy_zip)
    if legacy_zip:
        raise ValueError("--legacy-zip only applies to target package")
    return TARGETS[target][0](scene_dir, out_dir)
