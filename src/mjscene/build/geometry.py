"""3D objects: assembly expansion, repetition, geom attributes, and body trees.

`geom_attrs` maps collision, friction, and appearance settings to MJCF attributes.
"""

from __future__ import annotations

import copy
import random
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

from ..spec import assemblies
from .mjcf import set_attrs

if TYPE_CHECKING:
    from .compiler import Compiler

__all__ = ["expand_objects", "apply_repeat", "geom_attrs", "orientation_attrs",
           "build_object"]


def expand_objects(c: "Compiler") -> list[dict]:
    out: list[dict] = []
    for i, a in enumerate(c.spec.get("assemblies") or []):
        out.extend(assemblies.expand(a, i))
    out.extend(copy.deepcopy(c.spec.get("objects") or []))
    return [o for src in out for o in apply_repeat(c, src)]


def apply_repeat(c: "Compiler", obj: dict) -> list[dict]:
    rep = obj.get("repeat")
    if not rep:
        return [obj]
    counts = [int(c) for c in (rep.get("count") or [1, 1, 1])]
    counts = (counts + [1, 1, 1])[:3]
    spacing = (list(rep.get("spacing") or [1, 1, 1]) + [1, 1, 1])[:3]
    jitter = float(rep.get("jitter") or 0.0)
    rng = random.Random(int(rep.get("seed", 0)))
    base_pos = obj.get("pos") or [0.0, 0.0, 0.0]
    base_name = obj.get("name") or obj.get("shape", "obj")
    out = []
    n = 0
    for iz in range(counts[2]):
        for iy in range(counts[1]):
            for ix in range(counts[0]):
                clone = copy.deepcopy(obj)
                clone.pop("repeat", None)
                idx = [ix, iy, iz]
                clone["pos"] = [base_pos[k] + idx[k] * spacing[k]
                                + (rng.uniform(-jitter, jitter) if jitter else 0.0)
                                for k in range(3)]
                clone["name"] = f"{base_name}_{n}"
                out.append(clone)
                n += 1
    return out


def geom_attrs(c: "Compiler", obj: dict) -> dict:
    """Collision + friction + appearance attributes for one geom."""
    shape = obj.get("shape", "box")
    attrs: dict = {}
    fric_ref = obj.get("friction")
    condim = obj.get("condim")
    if condim is None and fric_ref is not None:
        condim = c.friction_condim(fric_ref)
    if fric_ref is not None:
        attrs["friction"] = c.friction(fric_ref)
    if condim is not None:
        attrs["condim"] = int(condim)
    cp = c.contact_profile(obj.get("contact"))
    if cp:
        attrs["solref"] = cp["solref"]
        attrs["solimp"] = cp["solimp"]
    if obj.get("solref") is not None:
        attrs["solref"] = obj["solref"]
    if obj.get("solimp") is not None:
        attrs["solimp"] = obj["solimp"]
    if obj.get("margin") is not None:
        attrs["margin"] = obj["margin"]
    if obj.get("priority") is not None:
        attrs["priority"] = int(obj["priority"])
    if obj.get("contype") is not None:
        attrs["contype"] = int(obj["contype"])
    if obj.get("conaffinity") is not None:
        attrs["conaffinity"] = int(obj["conaffinity"])
    if obj.get("collision") is False:
        attrs["contype"] = 0
        attrs["conaffinity"] = 0
    if obj.get("group"):
        attrs["group"] = int(obj["group"])
    mat = c.material(obj.get("material"))
    if mat:
        attrs["material"] = mat
    if obj.get("rgba") is not None:
        attrs["rgba"] = obj["rgba"]
    if obj.get("mass") is not None:
        attrs["mass"] = obj["mass"]
    elif obj.get("density") is not None:
        attrs["density"] = obj["density"]
    if shape == "mesh":
        attrs["mesh"] = obj["mesh"]
    return attrs


def orientation_attrs(obj: dict) -> dict:
    for key, mj in (("euler", "euler"), ("quat", "quat"), ("axisangle", "axisangle")):
        if obj.get(key) is not None:
            return {mj: obj[key]}
    return {}


def build_object(c: "Compiler", parent, obj: dict, parent_static: bool):
    shape = obj.get("shape", "box")
    kind = obj.get("kind", "dynamic")
    name = c.uniq(obj.get("name") or f"{shape}_obj")
    body = ET.SubElement(parent, "body")
    set_attrs(body, name=name, pos=obj.get("pos", [0, 0, 0]), **orientation_attrs(obj))

    if kind == "dynamic" and not parent_static:
        set_attrs(ET.SubElement(body, "freejoint"), name=f"{name}_free")
    elif kind == "articulated":
        joints = obj.get("joints") or ([obj["joint"]] if obj.get("joint") else [])
        for j, jt in enumerate(joints):
            if jt.get("type") == "free":
                set_attrs(ET.SubElement(body, "freejoint"), name=jt.get("name") or f"{name}_free")
                continue
            el = ET.SubElement(body, "joint")
            set_attrs(el, name=jt.get("name") or f"{name}_j{j}", type=jt.get("type", "hinge"),
                      axis=jt.get("axis", [0, 0, 1]), pos=jt.get("pos") or None,
                      range=jt.get("range"), damping=jt.get("damping") or None,
                      stiffness=jt.get("stiffness") or None,
                      armature=jt.get("armature") or None,
                      frictionloss=jt.get("frictionloss") or None,
                      limited=jt.get("limited"))

    if shape != "none":
        geom = ET.SubElement(body, "geom")
        gattrs = {"name": f"{name}_geom", "type": shape}
        if obj.get("fromto") is not None:
            gattrs["fromto"] = obj["fromto"]
            size = obj.get("size")
            if size:
                gattrs["size"] = size[:1] if shape in ("capsule", "cylinder") else size
        else:
            gattrs["size"] = obj.get("size") or [0.05]
        gattrs.update(geom_attrs(c, obj))
        set_attrs(geom, **gattrs)

    c.object_index.append({
        "name": name,
        "kind": kind,
        "shape": shape,
        "tags": obj.get("tags") or [],
        "pos": obj.get("pos", [0, 0, 0]),
    })

    for child in obj.get("children") or []:
        # Children of a static body stay welded; children of a dynamic body
        # either weld into the same rigid body (no joint) or become links.
        build_object(c, body, child, parent_static=(kind != "articulated"))
