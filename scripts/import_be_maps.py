#!/usr/bin/env python3
"""Snapshot BE UNLIMITED's 13 built-in environments as validated map sources.

Run from robot-shell-workflow: python scripts/import_be_maps.py [--be-root PATH]
The TypeScript bridge evaluates current source code; generated scene-package.json
and scene.xml are self-contained inputs for the normal .map archive writer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from shellflow.map_package import validate  # noqa: E402

NAMES = {
    "home": "Home", "bedroom": "Bedroom", "soccer": "Soccer Field", "plaza": "Corner Plaza",
    "warehouse": "Warehouse Challenge", "pingpong": "Ping-Pong Retrieval", "pouring": "Pouring Drinks",
    "mine": "Mine Survey", "litter": "Litter Cleanup", "studio": "Showcase Stage",
    "flat": "Open Field", "obstacles": "Obstacle Course", "arena": "Arena",
}
SOURCE_TS = ("src/simulator/scene.ts", "src/simulator/bedroom-data.ts",
             "src/simulator/soft-props.ts", "src/components/simulator-scene-details.ts",
             "src/components/simulator-environment.ts", "src/components/simulator-props.ts",
             "src/components/simulator-soft-props.ts")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rgba(color: str | None, visible: bool = True) -> str:
    if color is None:
        color = "#7a947a"
    if len(color) != 7 or not color.startswith("#"):
        raise ValueError(f"unsupported source color: {color}")
    values = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return " ".join(f"{v:.9g}" for v in (*values, 1 if visible else 0))


def generated_scene(record: dict) -> bytes:
    root = ET.Element("mujoco", {"model": f"be_{record['id']}"})
    ET.SubElement(root, "compiler", {"angle": "radian"})
    world = ET.SubElement(root, "worldbody")
    fragment = ET.fromstring("<fragment>" + record["xmlFragment"] + "</fragment>")
    world.extend(fragment)
    geometry = {g["name"]: g for g in record["geometry"]}
    props = {f"prop:{p['id']}": p for p in record["props"]}
    for geom in world.iter("geom"):
        name = geom.get("name")
        if name in geometry:
            source = geometry[name]
            geom.set("rgba", rgba(source.get("color"), source.get("visible", True)))
    for body in world.findall("body"):
        prop = props.get(body.get("name"))
        if not prop:
            continue
        for index, geom in enumerate(body.findall("geom")):
            parts = prop.get("colliders") or []
            color = parts[index].get("color") if index < len(parts) else None
            geom.set("rgba", rgba(color or prop["color"]))
    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def bedroom_files(be_root: Path) -> dict[str, bytes]:
    source = be_root / "public/simulator/scenes/bedroom"
    xml = (source / "scene.xml").read_bytes()
    root = ET.fromstring(xml)
    compiler = root.find("compiler")
    asset_dir = compiler.get("assetdir", "") if compiler is not None else ""
    result = {"scene.xml": xml}
    for element in root.iter():
        for attr, value in element.attrib.items():
            if attr != "file" and not (element.tag == "texture" and attr.startswith("file")):
                continue
            rel = (Path(asset_dir) / value).as_posix()
            if rel.startswith("/") or ".." in Path(rel).parts:
                raise ValueError(f"unsafe bedroom asset: {rel}")
            result[rel] = (source / rel).read_bytes()
    return result


def package_manifest(record: dict, files: dict[str, bytes], source_hashes: dict) -> dict:
    scene = ET.fromstring(files["scene.xml"])
    world = scene.find("worldbody")
    if world is None:
        raise ValueError(f"{record['id']}: no worldbody")
    asset = scene.find("asset")
    compiler = scene.find("compiler")
    asset_dir = compiler.get("assetdir", "") if compiler is not None else ""
    free_props = []
    for body in world.iter("body"):
        free = body.find("freejoint")
        if free is None:
            continue
        name = body.get("name")
        if not name:
            raise ValueError(f"{record['id']}: unnamed free body")
        item = {"name": name, "body": name, "freeJoint": True,
                "geoms": [g.get("name") for g in body.iter("geom") if g.get("name")],
                "position": [float(v) for v in body.get("pos", "0 0 0").split()]}
        if free.get("name"):
            item["freeJointName"] = free.get("name")
        free_props.append(item)
    names = {g.get("name") for g in world.iter("geom")}
    ground = "floor_geom" if record["id"] == "bedroom" else "ground"
    if ground not in names:
        raise ValueError(f"{record['id']}: ground geom missing")
    counts = {
        "geoms": sum(1 for _ in world.iter("geom")),
        "bodies": sum(1 for _ in world.iter("body")),
        "lights": sum(1 for _ in world.iter("light")),
        "textures": sum(1 for _ in asset.iter("texture")) if asset is not None else 0,
        "materials": sum(1 for _ in asset.iter("material")) if asset is not None else 0,
        "meshes": sum(1 for _ in asset.iter("mesh")) if asset is not None else 0,
    }
    flex = [{"id": e.get("name")} for tag in ("flex", "flexcomp")
            for e in scene.iter(tag) if e.get("name")]
    spawn = record["spawn"] or {"position": [0, 0, 0], "yaw": 0}
    if record["id"] == "pouring":
        # BE's display scene has no robot spawn. The generic origin lies inside
        # the counter, so place the robot on open floor facing the work surface.
        spawn = {"position": [0.25, -1.15, 0], "yaw": 90}
    required = ["rigid"] + (["flex"] if flex else [])
    source = {"repository": "BE-UNLIMITED/be-unlimited", "files": source_hashes}
    if record["id"] == "pouring":
        source["spawnAdjustment"] = (
            "BE has no robot spawn; origin intersects the counter "
            "(x -0.5..1, y -0.75..0.25, z 0..0.24). "
            "Place robot on open floor facing the counter."
        )
    return {
        "schema": "kk-scene-package/1", "id": record['id'],
        "title": NAMES[record["id"]], "version": "1.1.0", "use": "watching",
        "exportedBy": {"repo": "robot-shell-workflow", "tool": "scripts/import_be_maps.py"},
        "source": source,
        "requiredCapabilities": required,
        "world": {"file": "scene.xml", "assetDir": asset_dir,
                  "terrainType": "none", "ground": {"geom": ground},
                  "counts": counts, "attach": {"prefix": "scn_"}},
        "props": free_props, "flex": flex,
        "lights": [{"name": e.get("name")} for e in world.iter("light") if e.get("name")],
        "cameras": [e.get("name") for e in world.iter("camera") if e.get("name")],
        "spawn": spawn,
        "files": {name: {"bytes": len(data), "sha256": sha(data)}
                  for name, data in sorted(files.items())},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--be-root", type=Path,
                        default=ROOT.parent / "BE-UNLIMITED/be-unlimited")
    args = parser.parse_args()
    be_root = args.be_root.resolve()
    cmd = ["node", str(ROOT / "scripts/import_be_maps.mjs"), str(be_root)]
    records = json.loads(subprocess.check_output(cmd, cwd=ROOT))
    if set(r["id"] for r in records) != set(NAMES) or len(records) != len(NAMES):
        raise ValueError("BE scene registry differs from expected 13 environments")
    source_hashes = {name: sha((be_root / name).read_bytes()) for name in SOURCE_TS}
    with tempfile.TemporaryDirectory(prefix="be-web-visuals-") as temp:
        subprocess.run(["node", str(ROOT / "scripts/export_web_visuals.mjs"), str(be_root), temp], check=True)
        visuals = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in Path(temp).glob("*.json")}
    destination = ROOT / "library/map-sources/be-unlimited"
    for record in records:
        files = bedroom_files(be_root) if record["id"] == "bedroom" else {
            "scene.xml": generated_scene(record)}
        hashes = dict(source_hashes)
        if record["id"] == "bedroom":
            for name, data in files.items():
                origin = f"public/simulator/scenes/bedroom/{name}"
                hashes[origin] = sha(data)
        manifest = package_manifest(record, files, hashes)
        package = dict(files)
        package["scene-package.json"] = (json.dumps(manifest, ensure_ascii=False,
                                                    indent=2) + "\n").encode("utf-8")
        if record["id"] in visuals:
            from web_visuals import apply_visuals
            package = apply_visuals(package, visuals[record["id"]])
        from shellflow.web_appearance import complete_appearance
        package = complete_appearance(package, linear=record["id"] == "bedroom")
        validate(package, capabilities=set(manifest["requiredCapabilities"]))
        directory = destination / record["id"]
        directory.mkdir(parents=True, exist_ok=True)
        for name, data in package.items():
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        print(f"{record['id']}: {len(package)} files, {manifest['world']['counts']['geoms']} geoms, "
              f"{len(manifest['props'])} props, {','.join(manifest['requiredCapabilities'])}")


if __name__ == "__main__":
    main()
