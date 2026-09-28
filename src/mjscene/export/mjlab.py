"""Export target for kk-rl-mjlab and similar RL frameworks.

mjlab geometry enters through `EntityCfg.spec_fn: () -> MjSpec` and
`MjSpec.attach()`. Export follows its constraints: one freejoint per entity,
a separate static room, parent-owned option and visual settings, lights and
cameras supplied by SceneCfg, a ground geom named terrain, and asset paths
relative to their XML files. Unsupported flex elements are listed in the report.
"""

from __future__ import annotations

import json
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from . import mjcf_tools as T

__all__ = ["export", "ExportResult", "TARGET"]

TARGET = "mjlab"

# These top-level sections do not take effect in mjlab and would mislead readers.
_DROP_SECTIONS = {
    "option": "attach() does not propagate it; set timestep, integrator, and gravity in MujocoCfg",
    "visual": "overridden by the parent mjlab spec",
    "statistic": "determined by the parent spec",
}
_DROP_WORLD = {
    "light": "lights are provided by TerrainEntityCfg.lights or Scene.lights",
    "camera": "cameras are provided by the environment configuration",
    "flexcomp": "the mjlab warp backend does not support flex",
}
GROUND_GEOM_NAME = "terrain"


@dataclass
class ExportResult:
    out_dir: Path
    room_xml: Path
    props: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    static_bodies: int = 0

    def report(self) -> str:
        lines = [f"room/room.xml   Static room and furniture ({self.static_bodies} bodies)",
                 f"props/          {len(self.props)} movable objects"
                 + (f": {', '.join(self.props)}" if self.props else "")]
        lines += [f"· {n}" for n in self.notes]
        return "\n".join(lines)


def _ground_candidates(scene_dir: Path) -> set[str]:
    """Find the ground body name for a plane or custom floor."""
    names = {"ground", "floor", "ground_geom", "floor_geom", "terrain"}
    sidecar = scene_dir / "build" / "scene.viewer.json"
    if sidecar.exists():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return names
        for obj in data.get("objects", []):
            if obj.get("kind") == "ground" or "floor" in (obj.get("tags") or []):
                names.add(obj["name"])
                names.add(f"{obj['name']}_geom")
    return names


def _entity_xml(name: str, bodies: list[ET.Element], asset: ET.Element,
                default: ET.Element | None, contact: ET.Element | None,
                loose: list[ET.Element] | None = None) -> ET.Element:
    root = ET.Element("mujoco", {"model": name})
    ET.SubElement(root, "compiler", {"angle": "degree", "autolimits": "true",
                                     "meshdir": "meshes/", "texturedir": "meshes/",
                                     "eulerseq": "xyz"})
    mats, meshes = T.referenced_assets(bodies + list(loose or []))
    root.append(T.prune_asset(asset, mats, meshes))
    if default is not None:
        root.append(default)
    world = ET.SubElement(root, "worldbody")
    for el in (loose or []):          # Include loose geoms such as a ground plane.
        world.append(el)
    for b in bodies:
        world.append(b)
    if contact is not None and len(contact):
        root.append(contact)
    return root


def _mesh_files(asset: ET.Element, meshes: set[str]) -> set[str]:
    return {m.get("file") for m in asset.findall("mesh")
            if m.get("name") in meshes and m.get("file")}


def _texture_files(asset: ET.Element, mats: set[str]) -> set[str]:
    keep_tex = {m.get("texture") for m in asset.findall("material")
                if m.get("name") in mats and m.get("texture")}
    return {t.get("file") for t in asset.findall("texture")
            if t.get("name") in keep_tex and t.get("file")}


def export(scene_dir: Path | str, out_dir: Path | str | None = None) -> ExportResult:
    """Export <scene_dir>/build/scene.xml as mjlab entities."""
    scene_dir = Path(scene_dir)
    src = scene_dir / "build" / "scene.xml"
    if not src.exists():
        raise FileNotFoundError(f"Build output not found: {src}; run mjscene build first")
    out = Path(out_dir) if out_dir else scene_dir / "export" / TARGET

    root = T.load(src)
    notes = T.strip_sections(root, _DROP_SECTIONS)
    world = T.merge_worldbodies(root)          # raw_mjcf may add another worldbody.
    notes += T.strip_worldbody(world, _DROP_WORLD)

    old = T.rename_geom(world, _ground_candidates(scene_dir), GROUND_GEOM_NAME)
    if old and old != GROUND_GEOM_NAME:
        notes.append(f"Renamed ground geom {old} -> {GROUND_GEOM_NAME} for mjlab material binding")

    asset = root.find("asset")
    default = root.find("default")
    contact = root.find("contact")
    if contact is not None:
        root.remove(contact)

    static, dynamic = T.split_by_freejoint(world)
    loose = T.loose_elements(world)             # Geoms outside bodies, such as ground.
    src_assets = src.parent / "assets"

    if out.exists():
        shutil.rmtree(out)

    def copy_assets(dest: Path, bodies: list[ET.Element]) -> None:
        mats, meshes = T.referenced_assets(bodies)
        wanted = _mesh_files(asset, meshes) | _texture_files(asset, mats)
        dest.mkdir(parents=True, exist_ok=True)
        if not src_assets.exists():
            return
        for f in sorted(src_assets.iterdir()):
            if f.is_file() and f.name in wanted:
                shutil.copy2(f, dest / f.name)

    copy_assets(out / "room" / "meshes", static + loose)
    room_xml = out / "room" / "room.xml"
    T.write_xml(_entity_xml("room", static, asset, default, contact, loose), room_xml)

    props: list[str] = []
    for body in dynamic:
        name = body.get("name") or f"prop_{len(props)}"
        fj = body.find("freejoint")
        if fj is not None:
            body.remove(fj)                 # The entity adds its own joint for placement.
        pdir = out / "props" / name
        copy_assets(pdir / "meshes", [body])
        ent = _entity_xml(name, [body], asset, default, None)
        ET.SubElement(ent.find("worldbody").find("body"), "freejoint")
        T.write_xml(ent, pdir / f"{name}.xml")
        props.append(name)

    result = ExportResult(out_dir=out, room_xml=room_xml, props=props, notes=notes,
                          static_bodies=len(static))
    (out / "entities.py").write_text(_python_snippet(props), encoding="utf-8")
    (out / "README.md").write_text(_readme(result), encoding="utf-8")
    return result


def _python_snippet(props: list[str]) -> str:
    lines = "\n".join(
        f'    "{p}": EntityCfg(spec_fn=lambda p="{p}": mujoco.MjSpec.from_file(\n'
        f'        str(_HERE / "props" / p / f"{{p}}.xml"))),' for p in props)
    return f'''"""Connect the exported scene to mjlab SceneCfg (generated by mjscene export).

The room has a fixed base. mjlab wraps it in a mocap body; without a reset
event it stays at each environment origin.
"""

from pathlib import Path

import mujoco
from mjlab.entity import EntityCfg

_HERE = Path(__file__).parent

ROOM = EntityCfg(spec_fn=lambda: mujoco.MjSpec.from_file(str(_HERE / "room" / "room.xml")))

PROPS = {{
{lines}
}}

# Usage:
#   cfg.scene.entities["room"] = ROOM
#   cfg.scene.entities.update(PROPS)
#   cfg.scene.env_spacing = 8.0   # Must exceed room dimensions.
'''


def _readme(r: ExportResult) -> str:
    return f"""# mjlab export

Generated by `python -m mjscene export <scene_name> --target mjlab`. Re-export after scene changes.

```
room/room.xml     Static room and furniture ({r.static_bodies} bodies)
room/meshes/      Referenced meshes and textures (<compiler meshdir="meshes/">)
props/<name>/     {len(r.props)} movable objects, one entity and freejoint each
entities.py       Importable EntityCfg definitions
```

## Export changes

{chr(10).join('- ' + n for n in r.notes) if r.notes else '- None'}

## Integration

```python
from entities import ROOM, PROPS
cfg.scene.entities["room"] = ROOM
cfg.scene.entities.update(PROPS)
cfg.scene.env_spacing = 8.0
```

`attach()` discards MJCF physics options such as timestep, integrator, and gravity;
set these in `MujocoCfg`. Configure lights through `TerrainEntityCfg.lights` or `Scene.lights`.

Watch the viewer geom limit and `njmax`/`nconmax` preallocation. More room geoms
reduce the number of environments that can be rendered simultaneously.
"""
