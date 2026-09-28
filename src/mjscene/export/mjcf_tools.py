"""MJCF operations shared by export targets.

Exporters read the **compiled** scene.xml accepted by MuJoCo, not the spec.
This module trims and splits XML without depending on spec or build layers.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

__all__ = ["load", "merge_worldbodies", "strip_sections", "strip_worldbody",
           "split_by_freejoint", "loose_elements", "referenced_assets", "prune_asset",
           "rename_geom", "write_xml"]


def load(xml_path: Path) -> ET.Element:
    return ET.parse(xml_path).getroot()


def merge_worldbodies(root: ET.Element) -> ET.Element:
    """Merge multiple <worldbody> elements into one and return it.

    `raw_mjcf` can append a second <worldbody>, which MuJoCo merges. A simple
    `find("worldbody")` would miss its contents.
    """
    bodies = root.findall("worldbody")
    if not bodies:
        return ET.SubElement(root, "worldbody")
    first = bodies[0]
    for extra in bodies[1:]:
        for child in list(extra):
            first.append(child)
        root.remove(extra)
    return first


def loose_elements(world: ET.Element) -> list[ET.Element]:
    """Elements in worldbody outside bodies, such as a ground geom or site.

    Omitting them could remove the ground entirely.
    """
    keep = []
    for child in list(world):
        if child.tag in ("geom", "site"):
            keep.append(child)
            world.remove(child)
    return keep


def strip_sections(root: ET.Element, tags: dict[str, str]) -> list[str]:
    """Remove top-level sections such as <option> or <visual>; tags map to reasons."""
    notes = []
    for tag, why in tags.items():
        for el in root.findall(tag):
            root.remove(el)
            notes.append(f"Removed <{tag}>: {why}")
    return notes


def strip_worldbody(world: ET.Element, tags: dict[str, str]) -> list[str]:
    """Remove selected element types from worldbody, such as lights or cameras."""
    notes = []
    for tag, why in tags.items():
        for el in list(world.findall(tag)):
            world.remove(el)
            name = el.get("name")
            notes.append(f"Removed <{tag}{' name=' + name if name else ''}>: {why}")
    return notes


def split_by_freejoint(world: ET.Element) -> tuple[list[ET.Element], list[ET.Element]]:
    """Split worldbody bodies into static and freejoint groups.

    Downstream RL frameworks commonly require at most one free joint per entity.
    """
    static, dynamic = [], []
    for body in list(world.findall("body")):
        (dynamic if body.find("freejoint") is not None else static).append(body)
        world.remove(body)
    return static, dynamic


def referenced_assets(bodies: list[ET.Element]) -> tuple[set[str], set[str]]:
    """Find materials and meshes referenced by these bodies and their children."""
    mats: set[str] = set()
    meshes: set[str] = set()

    def collect(g: ET.Element) -> None:
        if g.get("material"):
            mats.add(g.get("material"))
        if g.get("mesh"):
            meshes.add(g.get("mesh"))

    def walk(el: ET.Element) -> None:
        # The element itself may be a geom, such as ground directly in worldbody.
        # Searching descendants alone would miss its material.
        if el.tag == "geom":
            collect(el)
            return
        for g in el.findall("geom"):
            collect(g)
        for b in el.findall("body"):
            walk(b)

    for b in bodies:
        walk(b)
    return mats, meshes


def prune_asset(asset: ET.Element, mats: set[str], meshes: set[str],
                keep_hfield: bool = True) -> ET.Element:
    """Keep only referenced materials, textures, and meshes for each export."""
    out = ET.Element("asset")
    keep_tex: set[str] = set()
    kept_mats = []
    for mat in asset.findall("material"):
        if mat.get("name") in mats:
            kept_mats.append(mat)
            if mat.get("texture"):
                keep_tex.add(mat.get("texture"))
    for tex in asset.findall("texture"):
        if tex.get("name") in keep_tex:
            out.append(tex)
    out.extend(kept_mats)
    for mesh in asset.findall("mesh"):
        if mesh.get("name") in meshes:
            out.append(mesh)
    if keep_hfield:
        for hf in asset.findall("hfield"):
            out.append(hf)
    return out


def rename_geom(world: ET.Element, candidates: set[str], new_name: str) -> str | None:
    """Rename matching geoms and return the original name."""
    def walk(el: ET.Element) -> str | None:
        for g in el.findall("geom"):
            if g.get("name") in candidates:
                old = g.get("name")
                g.set("name", new_name)
                return old
        for b in el.findall("body"):
            found = walk(b)
            if found:
                return found
        return None

    return walk(world)


def write_xml(root: ET.Element, path: Path) -> None:
    ET.indent(root, space="  ")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<?xml version="1.0" encoding="utf-8"?>\n'
                    + ET.tostring(root, encoding="unicode") + "\n", encoding="utf-8")
