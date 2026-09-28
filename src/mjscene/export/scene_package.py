"""Export a `kk-scene-package/1` archive for two simulation consumers.

BE UNLIMITED attaches the world to a robot in browser MuJoCo. kk-rl-mjlab
attaches it to MjSpec for play, not training: a room at the world origin would
otherwise appear only in the origin environment of a parallel training run.

The format follows kk-rl-mjlab's `scenes/tools/export_web_scene.py`. A prop with
`file` is an independent model placed near each robot; a prop without `file`
is a body already positioned in the world file.

The world must be attached rather than concatenated into the host MJCF.
Tests with MuJoCo 3.14 and browser MuJoCo 3.13 found that direct concatenation
can reinterpret host joint limits in degrees, overwrite mass and contact
defaults, and silently replace the host timestep. `<attach>` keeps parent
compiler, default, and option settings and prefixes scene names. This exporter
removes child `<option>` and `<visual>` sections that attach would ignore and
records the physics values as advisory settings.

Outputs are an unpacked `<out>/<name>.scene/` directory for review and an
uploadable `<out>/<name>.map`. With legacy_zip=True the archive name is
`<name>.scene.zip` with the same protocol.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import mjcf_tools as T

__all__ = ["export", "PackageResult", "TARGET", "SCHEMA", "LIMITS", "MANIFEST"]

TARGET = "package"
SCHEMA = "kk-scene-package/1"
#: Manifest name defined by kk-rl-mjlab's scenes/tools/export_web_scene.py.
MANIFEST = "scene-package.json"
#: Watching scenes are for simulation, not parallel training environments.
USE = "watching"
#: Tell consumers which MuJoCo version this MJCF targets.
MUJOCO_AT_LEAST = "3.2"

#: Enforce package limits before upload; consumers validate them again.
LIMITS = {
    "files": 256,
    "archive_bytes": 64 * 1024 * 1024,
    "expanded_bytes": 192 * 1024 * 1024,
}
#: Warn about budgets that may slow a browser running the robot simultaneously.
BUDGET_HINTS = {"geoms": 400, "bodies": 600, "props": 48}

# attach ignores these sections and would only warn about them.
_DROP_SECTIONS = {
    "option": "attach() retains host integration settings; values are recorded in manifest.physics.advisory",
    "visual": "rendering is controlled by the host",
}


@dataclass
class PackageResult:
    out_dir: Path
    package_dir: Path
    archive: Path
    manifest: dict
    notes: list[str] = field(default_factory=list)

    def report(self) -> str:
        m = self.manifest
        c = m["world"]["counts"]
        lines = [
            f"{self.archive.name}   {self.archive.stat().st_size / 1e6:.2f} MB"
            f" ({len(m['files'])} files)",
            f"attach prefix {m['world']['attach']['prefix']!r}"
            f" -> attached names look like {m['world']['attach']['prefix']}<scene_name>",
            f"geoms {c['geoms']} · bodies {c['bodies']} · movable props {len(m['props'])}"
            f" · flex {len(m['flex'])} · lights {len(m['lights'])} · cameras {len(m['cameras'])}",
        ]
        if m["props"]:
            ids = [p["name"] for p in m["props"]]
            lines.append("Movable props: " + ", ".join(ids[:8]) + (" ..." if len(ids) > 8 else ""))
        lines += [f"· {n}" for n in self.notes]
        return "\n".join(lines)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk_bodies(el: ET.Element, depth: int = 0):
    """Yield (body element, depth) in depth-first order."""
    for body in el.findall("body"):
        yield body, depth
        yield from _walk_bodies(body, depth + 1)


def _floats(value: str | None) -> list[float] | None:
    if not value:
        return None
    try:
        return [float(x) for x in value.split()]
    except ValueError:
        return None


def _props(world: ET.Element, defaults: dict) -> list[dict]:
    """Describe freejoint bodies that consumers track and can drag.

    Search at any depth because nested bodies can have free joints. These
    entries omit `file`: they are world bodies at absolute positions. In
    contrast, independent mjlab props have `file` and may be positioned near
    each robot with `initPositionRelativeToRobot`.
    """
    out = []
    for body, depth in _walk_bodies(world):
        free = body.find("freejoint")
        if free is None:
            continue
        name = body.get("name")
        if not name:
            continue
        geoms = [g for g in body.iter("geom") if g.get("name")]
        entry: dict = {
            "name": name,
            "body": name,
            "freeJoint": True,
            "geoms": [g.get("name") for g in geoms],
            # Contact parameters affect motion even when rendering is unchanged.
            "contact": [{
                "geom": g.get("name"),
                "condim": int(g.get("condim") or defaults.get("condim") or 3),
                "friction": _floats(g.get("friction")) or defaults.get("friction"),
                "solref": _floats(g.get("solref")) or defaults.get("solref"),
            } for g in geoms],
        }
        if free.get("name"):
            entry["freeJointName"] = free.get("name")
        pos = _floats(body.get("pos"))
        if pos:
            # Absolute world position, not robot-relative; see propsAreInTheWorld.
            entry["position"] = pos
        if depth:
            entry["nested"] = True
        out.append(entry)
    return out


def _physics_advisory(root: ET.Element) -> dict:
    """Integration settings from scene tuning, advisory because attach ignores them."""
    opt = root.find("option")
    if opt is None:
        return {"advisory": True}
    adv: dict = {"advisory": True,
                 "note": "attach() retains the host <option>; these are scene tuning values "
                         "that the host may choose to apply"}
    for key, cast in (("timestep", float), ("integrator", str), ("solver", str),
                      ("iterations", int), ("ls_iterations", int), ("cone", str),
                      ("impratio", float), ("noslip_iterations", int)):
        if opt.get(key) is not None:
            adv[key] = cast(opt.get(key))
    if opt.get("gravity"):
        adv["gravity"] = [float(x) for x in opt.get("gravity").split()]
    return adv


def _root_defaults(root: ET.Element) -> dict:
    """Read top-level `<default><geom>` contact settings for undeclared geom values.

    The manifest must report effective values. For example, a condim=4 default
    must not be reported as condim=3 just because individual geoms omit it.
    """
    d = root.find("default")
    geom = d.find("geom") if d is not None else None
    if geom is None:
        return {}
    out: dict = {}
    if geom.get("condim"):
        out["condim"] = int(geom.get("condim"))
    for key in ("friction", "solref"):
        vals = _floats(geom.get(key))
        if vals:
            out[key] = vals
    return out


def _ground(world: ET.Element, defaults: dict) -> dict:
    """Return contact settings for the first plane ground geom.

    Indoor scenes may use a floor body instead, in which case return no plane
    rather than inventing one in the manifest.
    """
    for geom in world.iter("geom"):
        if geom.get("type") != "plane":
            continue
        return {
            "geom": geom.get("name") or "",
            "friction": _floats(geom.get("friction")) or defaults.get("friction"),
            "solref": _floats(geom.get("solref")) or defaults.get("solref"),
            "condim": int(geom.get("condim") or defaults.get("condim") or 3),
            "priority": int(geom.get("priority") or 0),
        }
    return {}


def _collision(world: ET.Element) -> tuple[list[str], list[dict]]:
    """Return decorative geoms and colliding geoms with their masks.

    Both matter: treating decoration as solid adds invisible walls, while
    treating solid geoms as decoration lets the robot pass through them.
    """
    decorative: list[str] = []
    colliding: list[dict] = []
    for geom in world.iter("geom"):
        name = geom.get("name")
        if not name:
            continue
        contype = int(geom.get("contype") or 1)
        conaffinity = int(geom.get("conaffinity") or 1)
        if contype == 0 and conaffinity == 0:
            decorative.append(name)
        elif contype != 1 or conaffinity != 1:
            colliding.append({"geom": name, "contype": contype,
                              "conaffinity": conaffinity})
    return decorative, colliding


def _counts(root: ET.Element, world: ET.Element) -> dict:
    """Count declared XML elements for the manifest without loading MuJoCo.

    Compiled models with flex may add one body per vertex, so the declared
    `<body>` count only matches model.nbody when no flex is present.
    """
    asset = root.find("asset")
    # Count from worldbody; <default><geom> is a default, not another geom.
    return {
        "geoms": sum(1 for _ in world.iter("geom")),
        "bodies": sum(1 for _ in _walk_bodies(world)),
        "lights": sum(1 for _ in world.iter("light")),
        "textures": sum(1 for _ in asset.iter("texture")) if asset is not None else 0,
        "materials": sum(1 for _ in asset.iter("material")) if asset is not None else 0,
        "meshes": sum(1 for _ in asset.iter("mesh")) if asset is not None else 0,
    }


def _rules(props: list[dict], decorative: list[str], colliding: list[dict],
           flex: list[dict], ground: dict) -> dict:
    """Record facts whose loss would change behavior without changing rendering.

    This follows the same criterion as the corresponding kk-rl-mjlab function.
    """
    rules: dict[str, str] = {}
    rules["worldIsAttachedNotSpliced"] = (
        "Mount world.file with MuJoCo <attach>; do not splice its XML into the host. "
        "Tests show <compiler angle=\"degree\"> can reinterpret host joint limits "
        "(1.57 rad becomes 0.027 rad), while root <default><geom density> can change "
        "host mass and contact settings. The model may still compile and render."
    )
    if props:
        rules["propsAreInTheWorld"] = (
            f"These {len(props)} props have no file: they are bodies in world.file. "
            f"Their positions are absolute world coordinates, not robot-relative offsets. "
            f"Treating them as offsets could silently pile objects at the origin."
        )
    if decorative:
        rules["decorativeGeomsAreNonColliding"] = (
            f"The {len(decorative)} decorativeGeoms use contype=0/conaffinity=0. "
            f"Preserve this; making them solid would add invisible robot barriers."
        )
    private = [g for g in colliding if not (g["contype"] & 1)]
    if private:
        rules["privateCollisionChannels"] = (
            f"The masks for {', '.join(g['geom'] for g in private)} exclude bit 0, "
            f"so they collide only on matching channels. Preserve those masks."
        )
    if ground.get("priority"):
        rules["groundOutranksTheFeet"] = (
            f"Ground priority={ground['priority']} makes its friction parameters "
            f"override the robot foot parameters in MuJoCo. Removing priority "
            f"changes grip without changing the rendered scene."
        )
    if flex:
        rules["flexNeedsASupportingBackend"] = (
            f"This package contains {len(flex)} flex elements. Backends without flex "
            f"support, such as mjlab warp, must explicitly reject or report omission."
        )
    return rules


def _spawn(spec: dict, world: ET.Element) -> dict | None:
    sp = spec.get("spawn")
    if not sp:
        return None
    out = {"position": list(sp.get("position") or [0.0, 0.0, 0.0]),
           "yaw": float(sp.get("yaw") or 0.0),
           "clearance": float(sp.get("clearance") if sp.get("clearance") is not None else 0.4)}
    if sp.get("bounds"):
        out["bounds"] = list(sp["bounds"])
    site = next((s.get("name") for s in world.iter("site") if s.get("name") == "spawn"), None)
    if site:
        # Let the host query the compiled model's world coordinates by site name.
        out["site"] = site
    return out


def export(scene_dir: Path | str, out_dir: Path | str | None = None,
           *, legacy_zip: bool = False) -> PackageResult:
    scene_dir = Path(scene_dir)
    build = scene_dir / "build"
    xml_path = build / "scene.xml"
    if not xml_path.exists():
        raise FileNotFoundError(f"{xml_path} does not exist; run mjscene build {scene_dir.name} first")
    out_dir = Path(out_dir) if out_dir else scene_dir / "export" / TARGET

    spec = {}
    spec_path = build / "scene.spec.json"
    if spec_path.exists():
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    name = spec.get("name") or scene_dir.name

    root = T.load(xml_path)
    notes = T.strip_sections(root, _DROP_SECTIONS)
    physics = _physics_advisory(ET.parse(xml_path).getroot())   # Original before stripping.
    world = T.merge_worldbodies(root)

    defaults = _root_defaults(root)
    props = _props(world, defaults)
    flex = [{"id": f.get("name")} for f in world.iter("flexcomp") if f.get("name")]
    lights = [{"name": lt.get("name"), "type": lt.get("type", "spot"),
               "castshadow": lt.get("castshadow", "true") != "false"}
              for lt in world.iter("light") if lt.get("name")]
    cameras = [c.get("name") for c in world.iter("camera") if c.get("name")]

    # ---- Write package directory --------------------------------------- #
    package_dir = out_dir / f"{name}.scene"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    (package_dir / "assets").mkdir(parents=True)
    T.write_xml(root, package_dir / "scene.xml")

    src_assets = build / "assets"
    referenced = {el.get("file") for tag in ("texture", "mesh", "hfield")
                  for el in root.iter(tag) if el.get("file")}
    copied, unused = [], []
    if src_assets.is_dir():
        for f in sorted(src_assets.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(src_assets)
            if str(rel) not in referenced and rel.name not in referenced:
                unused.append(str(rel))
                continue
            dest = package_dir / "assets" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            copied.append(f"assets/{rel.as_posix()}")
    if unused:
        notes.append(f"Excluded {len(unused)} assets not referenced by scene.xml"
                     f" ({', '.join(unused[:3])}{' ...' if len(unused) > 3 else ''})")

    missing = sorted(r for r in referenced
                     if not (package_dir / "assets" / r).exists()
                     and not (package_dir / "assets" / Path(r).name).exists())
    if missing:
        raise FileNotFoundError(
            f"scene.xml references files missing from build/assets: {', '.join(missing)}; "
            f"rerun mjscene build {scene_dir.name}")

    # Register VFS assets by package path. MuJoCo may fall back to basename
    # matching, so reject collisions that could substitute a robot mesh.
    by_base: dict[str, list[str]] = {}
    for rel in copied:
        by_base.setdefault(Path(rel).name.lower(), []).append(rel)
    clashes = {k: v for k, v in by_base.items() if len(v) > 1}
    if clashes:
        raise ValueError(f"Duplicate asset basenames could confuse MuJoCo VFS: {clashes}")

    files = {}
    for rel in ["scene.xml", *copied]:
        p = package_dir / rel
        files[rel] = {"bytes": p.stat().st_size, "sha256": _sha256(p)}

    decorative, colliding = _collision(world)
    ground = _ground(world, defaults)
    manifest = {
        "schema": SCHEMA,
        "id": name,
        "title": spec.get("title") or name,
        "description": spec.get("description") or "",
        "tags": spec.get("tags") or [],
        # This is a watching scene for simulation, not a training environment.
        "use": USE,
        "exportedBy": {
            "repo": "scene-generator",
            "tool": f"mjscene export --target {TARGET}",
            "mujocoAtLeast": MUJOCO_AT_LEAST,
        },
        "world": {
            "file": "scene.xml",
            "assetDir": "assets",
            "terrainType": (spec.get("ground") or {}).get("type") or "none",
            "ground": ground,
            "counts": _counts(root, world),
            "decorativeGeoms": decorative,
            "collidingGeoms": colliding,
            "attach": {
                "prefix": "scn_",
                "note": "Mount with <asset><model name=… file=\"scene.xml\"/></asset> "
                        "and <attach model=… prefix=…/>. Manifest names omit the prefix; "
                        "add it when querying the model",
            },
            "vfs": "Register each package file under its package path in MjVFS or "
                   "the assets dictionary (scene.xml uses assetdir=assets)",
        },
        "physics": physics,
        "props": props,
        "flex": flex,
        "lights": lights,
        "cameras": cameras,
        "rules": _rules(props, decorative, colliding, flex, ground),
        "files": files,
    }
    spawn = _spawn(spec, world)
    if spawn:
        manifest["spawn"] = spawn
    else:
        notes.append("The spec has no spawn, so consumers will use their own default position; "
                     "adding spawn to scene.json is recommended")

    (package_dir / MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (package_dir / "README.md").write_text(_readme(manifest), encoding="utf-8")

    # ---- Package -------------------------------------------------------- #
    # The public mjscene CLI and shellflow's one-shot export must enforce the
    # same consumer contract. Validate the staged bytes before publishing an
    # archive, so a raw_mjcf escape or mismatched asset never leaves a .map.
    from shellflow.map_package import validate as validate_map
    staged = {f.relative_to(package_dir).as_posix(): f.read_bytes()
              for f in package_dir.rglob("*") if f.is_file()}
    validate_map(staged)

    # Fixed timestamps and permissions make repeated exports byte-identical,
    # so the archive SHA256 reliably identifies the uploaded version.
    archive = out_dir / (f"{name}.scene.zip" if legacy_zip else f"{name}.map")
    n_files = len(staged)
    if n_files > LIMITS["files"]:
        raise ValueError(f"Package has {n_files} files, above the limit of {LIMITS['files']}")
    temporary = out_dir / f".{archive.name}.{uuid.uuid4().hex}.tmp"
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as z:
            for rel, data in sorted(staged.items()):
                info = zipfile.ZipInfo(rel, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                z.writestr(info, data)
        if temporary.stat().st_size > LIMITS["archive_bytes"]:
            raise ValueError(f"Archive size {temporary.stat().st_size / 1e6:.1f} MB "
                             f"exceeds the {LIMITS['archive_bytes'] / 1e6:.0f} MB limit")
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)
    for key, cap in (("geoms", BUDGET_HINTS["geoms"]), ("bodies", BUDGET_HINTS["bodies"])):
        if manifest["world"]["counts"][key] > cap:
            notes.append(f"{key} count {manifest['world']['counts'][key]} exceeds the suggested {cap}; "
                         f"browser frame rate may drop while simulating the robot")
    if len(props) > BUDGET_HINTS["props"]:
        notes.append(f"Movable prop count {len(props)} exceeds the suggested {BUDGET_HINTS['props']}")
    if flex:
        notes.append(f"Contains {len(flex)} flex elements; the host must use a flex-capable backend")

    return PackageResult(out_dir=out_dir, package_dir=package_dir, archive=archive,
                         manifest=manifest, notes=notes)


def _readme(m: dict) -> str:
    c = m["world"]["counts"]
    props = "\n".join(f"| `{p['name']}` | {len(p['geoms'])} |" for p in m["props"][:20]) \
        or "| None | |"
    prefix = m["world"]["attach"]["prefix"]
    return f"""# {m['title']}

{m['description']}

`{m['schema']}` scene package generated by `mjscene export --target {TARGET}`.
The manifest is `{MANIFEST}`.

## Usage

Register every package file under its package path in MuJoCo VFS (the `assets`
dictionary in Python), then attach the scene:

```xml
<asset><model name="scene" file="{m['world']['file']}"/></asset>
<worldbody>
  <attach model="scene" prefix="{prefix}"/>
</worldbody>
```

**Use `<attach>` instead of splicing XML into the host.** Direct concatenation
can reinterpret host joint limits through `<compiler angle="degree">`
(1.57 rad becomes 0.027 rad) and change host mass and contact parameters through
`<default><geom density>`. Attach isolates these settings and retains parent values.

`rules` records facts whose loss would change behavior without changing rendering.

## Contents

Geoms {c['geoms']} · bodies {c['bodies']} · lights {c['lights']} · textures {c['textures']} ·
materials {c['materials']} · meshes {c['meshes']} · flex {len(m['flex'])} · cameras {len(m['cameras'])}

Movable props (`props[]` has **no `file`**, so these are world bodies with
absolute `position` values; add the `{prefix}` prefix when querying names):

| Name | Geom count |
| --- | --- |
{props}

## Advisory integration settings

`<attach>` ignores the child model's `<option>`, so this package omits it.
Scene tuning values are in `physics`; consumers decide whether to apply them.
Changing the host timestep may affect the robot policy.
"""
