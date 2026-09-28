"""Assets: materials, textures, external meshes, height fields, and robot models.

Materials are registered on demand: only referenced presets appear in
<asset>, so generated MJCF does not carry unused material definitions.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

from .. import library
from . import environment
from .mjcf import set_attrs

if TYPE_CHECKING:
    from .compiler import Compiler

__all__ = ["material", "stage_asset", "build_assets", "build_robots"]


def material(c: "Compiler", name: str | None) -> str | None:
    """Register a material (preset or user-defined) and return its MJCF name."""
    if not name:
        return None
    if name in c.materials:
        return name
    user = {m["name"]: m for m in (c.spec.get("materials") or [])}
    if name in user:
        src = user[name]
        base = src.get("base")
        resolved = dict(library.MATERIALS.get(base, {})) if base else {}
        resolved.update({k: v for k, v in src.items() if k not in ("name", "base")})
    elif name in library.MATERIALS:
        resolved = dict(library.MATERIALS[name])
    else:
        raise KeyError(f"unknown material {name!r}")
    c.materials[name] = resolved

    tex = resolved.get("texture")
    if tex:
        tex_name = f"tex_{name}"
        attrs: dict = {"name": tex_name, "type": "2d"}
        if tex.get("generator"):
            # Procedural textures use material-derived filenames; compile_scene writes them.
            file_name = f"tex_{name}.png"
            c.pending_textures.append((f"assets/{file_name}", tex["generator"],
                                       tex.get("params") or {}))
            c.assets.append(f"assets/{file_name}")
            attrs["file"] = file_name
        elif tex.get("file"):
            rel = stage_asset(c, tex["file"])
            attrs["file"] = Path(rel).name
        else:
            attrs.update({
                "builtin": tex.get("builtin", "checker"),
                "rgb1": tex.get("rgb1", [0.3, 0.3, 0.3]),
                "rgb2": tex.get("rgb2", [0.4, 0.4, 0.4]),
                "width": tex.get("width", 256),
                "height": tex.get("height", 256),
            })
            if tex.get("mark", "none") != "none":
                attrs["mark"] = tex["mark"]
                attrs["markrgb"] = tex.get("markrgb", [0.8, 0.8, 0.8])
            if tex.get("random") is not None and tex.get("mark") == "random":
                attrs["random"] = tex["random"]
        c.textures[tex_name] = attrs
        resolved["_texture_name"] = tex_name
    return name


def stage_asset(c: "Compiler", rel_path: str) -> str:
    """Schedule an external file for copying into <out>/assets. Returns rel path."""
    if (not isinstance(rel_path, str) or not rel_path or "\\" in rel_path
            or rel_path.startswith("/") or any(part in ("", ".", "..")
                                               for part in rel_path.split("/"))):
        raise ValueError(f"Asset path must be relative to the scene directory: {rel_path!r}")
    src = (c.spec_dir / rel_path).resolve()
    if not src.is_relative_to(c.spec_dir.resolve()):
        raise ValueError(f"Asset path must not point outside the scene directory: {rel_path!r}")
    if not src.exists():
        raise FileNotFoundError(f"Asset file not found: {rel_path} (relative to {c.spec_dir})")
    dest_rel = f"assets/{src.name}"
    if dest_rel not in c.assets:
        c.assets.append(dest_rel)
        c.copy_jobs.append((src, dest_rel))
    return dest_rel


def build_assets(c: "Compiler", asset_el):
    sky = environment.sky_settings(c)
    set_attrs(ET.SubElement(asset_el, "texture"), name="skybox", type="skybox",
              builtin="gradient", rgb1=sky["top"], rgb2=sky["bottom"], width=256, height=1536)
    for attrs in c.textures.values():
        set_attrs(ET.SubElement(asset_el, "texture"), **attrs)
    for name, m in c.materials.items():
        el = ET.SubElement(asset_el, "material")
        set_attrs(el, name=name, rgba=m.get("rgba", [0.7, 0.7, 0.7, 1.0]),
                  texture=m.get("_texture_name"),
                  texrepeat=m.get("texrepeat") if m.get("_texture_name") else None,
                  texuniform=m.get("texuniform") if m.get("_texture_name") else None,
                  reflectance=m.get("reflectance") or None,
                  shininess=m.get("shininess"), specular=m.get("specular"),
                  emission=m.get("emission") or None,
                  metallic=m.get("metallic"), roughness=m.get("roughness"))
    for mesh in c.spec.get("meshes") or []:
        if mesh.get("generator"):
            file_name = f"mesh_{mesh['name']}.obj"
            c.pending_meshes.append((f"assets/{file_name}", mesh["generator"],
                                     mesh.get("params") or {}))
            c.assets.append(f"assets/{file_name}")
        else:
            file_name = Path(stage_asset(c, mesh["file"])).name
        set_attrs(ET.SubElement(asset_el, "mesh"), name=mesh["name"], file=file_name,
                  scale=mesh.get("scale") if mesh.get("scale") != [1, 1, 1] else None,
                  maxhullvert=mesh.get("maxhullvert"))
    hf = c.hfield_asset
    if hf:
        set_attrs(ET.SubElement(asset_el, "hfield"), **hf)
    for child_model in c.model_assets:
        # file= is resolved relative to the XML, not assetdir, so keep the
        # "assets/..." prefix here.
        set_attrs(ET.SubElement(asset_el, "model"), **child_model)


def build_robots(c: "Compiler", root, world):
    """Attach external robot MJCFs.

    The MJCF form that actually works (verified against MuJoCo 3.x) is a child
    model declared in <asset> plus <attach> inside the body that places it:

        <asset><model name="arm_model" file="assets/arm.xml"/></asset>
        <body name="arm_mount" pos="..."><attach model="arm_model" prefix="arm_"/></body>

    Every body/joint/geom of the robot gets the prefix, so several copies of
    the same robot can coexist.
    """
    for i, r in enumerate(c.spec.get("robots") or []):
        rel = stage_asset(c, r["file"])
        name = c.uniq(r.get("name") or f"robot_{i}")
        model_name = f"{name}_model"
        c.model_assets.append({"name": model_name, "file": rel})
        frame = ET.SubElement(world, "body")
        set_attrs(frame, name=f"{name}_mount", pos=r.get("pos", [0, 0, 0]),
                  **({"euler": r["euler"]} if r.get("euler") is not None
                     else {"quat": r["quat"]} if r.get("quat") is not None else {}))
        if r.get("freejoint"):
            set_attrs(ET.SubElement(frame, "freejoint"), name=f"{name}_free")
        set_attrs(ET.SubElement(frame, "attach"), model=model_name, prefix=f"{name}_")
        c.notes.append(
            f"robot '{name}': all body/joint/geom names use prefix '{name}_'; "
            f"the base attaches to body '{name}_mount' (requires MuJoCo >= 3.2)")
        c.object_index.append({"name": f"{name}_mount", "kind": "robot",
                                  "tags": ["robot"], "prefix": f"{name}_"})
