"""Scene environment: physics options, visual settings, lights, and ground.

These functions take `Compiler` as the first argument, read `c.spec`, and
write `c.notes` or `c.assets`. Their logic remains separate from the class.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

from .. import library
from .mjcf import norm, set_attrs

if TYPE_CHECKING:
    from .compiler import Compiler

__all__ = ["sky_settings", "lighting_settings", "build_option", "build_visual",
           "build_default", "build_lights", "build_ground", "SHADOW_SIZE"]

SHADOW_SIZE = {"low": 1024, "medium": 2048, "high": 4096, "ultra": 8192}


def sky_settings(c: "Compiler") -> dict:
    s = c.spec.get("sky") or {}
    base = dict(library.SKY[s.get("preset", "day")])
    for k in ("top", "bottom", "haze"):
        if s.get(k) is not None:
            base[k] = s[k]
    if s.get("fog_range") is not None:
        base["fog"] = s["fog_range"]
    base["fog_enabled"] = s.get("fog", True)
    return base


def lighting_settings(c: "Compiler") -> dict:
    lg = c.spec.get("lighting") or {}
    preset = library.LIGHTING[lg.get("preset", "noon")]
    lights = copy.deepcopy(lg.get("lights") or preset["lights"])
    lights += copy.deepcopy(lg.get("extra_lights") or [])
    ambient = lg.get("ambient") or preset["ambient"]
    shadows = lg.get("shadows", True)
    return {"lights": lights, "ambient": ambient, "shadows": shadows,
            "shadow_size": SHADOW_SIZE[lg.get("shadow_quality", "high")],
            "headlight": lg.get("headlight", False)}


def build_option(c: "Compiler", root):
    p = {**library.DEFAULT_PHYSICS, **(c.spec.get("physics") or {})}
    el = ET.SubElement(root, "option")
    set_attrs(el, timestep=p["timestep"], gravity=p["gravity"], integrator=p["integrator"],
              solver=p["solver"], iterations=p["iterations"], ls_iterations=p["ls_iterations"],
              cone=p["cone"], impratio=p.get("impratio"), jacobian=p.get("jacobian"),
              noslip_iterations=p.get("noslip_iterations") or None)
    if any(p.get("wind") or []):
        set_attrs(el, wind=p["wind"])
    if p.get("density"):
        set_attrs(el, density=p["density"])
    if p.get("viscosity"):
        set_attrs(el, viscosity=p["viscosity"])
    if p["timestep"] > 0.004 and p["integrator"] == "Euler":
        c.notes.append("A large timestep with the Euler integrator may destabilize contacts; "
                       "consider integrator='implicitfast'")


def build_visual(c: "Compiler", root):
    sky = sky_settings(c)
    lg = lighting_settings(c)
    el = ET.SubElement(root, "visual")
    amb = lg["ambient"]
    if lg["headlight"]:
        set_attrs(ET.SubElement(el, "headlight"), ambient=amb, diffuse=[0.4, 0.4, 0.4],
                  specular=[0.1, 0.1, 0.1])
    else:
        # Ambient light belongs to <headlight>. MuJoCo ignores its entire
        # block, including ambient, when inactive. Keep it active but set
        # diffuse/specular to zero so lighting.ambient still takes effect.
        set_attrs(ET.SubElement(el, "headlight"), ambient=amb, diffuse=[0.0, 0.0, 0.0],
                  specular=[0.0, 0.0, 0.0])
    fog_start, fog_end = sky["fog"]
    set_attrs(ET.SubElement(el, "map"), fogstart=fog_start, fogend=fog_end,
              shadowclip=6, shadowscale=1.2, znear=0.005)
    set_attrs(ET.SubElement(el, "quality"), shadowsize=lg["shadow_size"], offsamples=8)
    set_attrs(ET.SubElement(el, "global"), azimuth=140, elevation=-22, offwidth=1280, offheight=720)
    rgba = ET.SubElement(el, "rgba")
    set_attrs(rgba, haze=list(sky["haze"]) + [1.0], fog=list(sky["haze"]) + [1.0])


def build_default(c: "Compiler", root):
    d = c.defaults
    el = ET.SubElement(root, "default")
    geom = ET.SubElement(el, "geom")
    cp = c.contact_profile(d.get("contact"))
    set_attrs(geom, condim=int(d["condim"]), friction=c.friction(d["friction"]),
              margin=d.get("margin") or None, gap=d.get("gap") or None,
              density=d.get("density"), solmix=d.get("solmix") if d.get("solmix") != 1 else None)
    if cp:
        set_attrs(geom, solref=cp["solref"], solimp=cp["solimp"])


def build_lights(c: "Compiler", world):
    lg = lighting_settings(c)
    world.append(ET.Comment(" lighting "))
    for i, lt in enumerate(lg["lights"]):
        name = c.uniq(lt.get("name") or f"light_{i}")
        direction = lt.get("dir")
        if direction is None and lt.get("target") is not None:
            pos = lt.get("pos") or [0, 0, 3]
            direction = [lt["target"][k] - pos[k] for k in range(3)]
        direction = norm(direction or [0, 0, -1])
        el = ET.SubElement(world, "light")
        castshadow = bool(lt.get("castshadow", True)) and lg["shadows"]
        set_attrs(el, name=name, type=lt.get("type", "directional"),
                  pos=lt.get("pos", [0, 0, 3]), dir=direction,
                  diffuse=lt.get("diffuse", [0.6, 0.6, 0.6]),
                  specular=lt.get("specular", [0.2, 0.2, 0.2]),
                  ambient=lt.get("ambient") if any(lt.get("ambient") or []) else None,
                  castshadow=castshadow,
                  active=False if lt.get("active") is False else None)
        if lt.get("type") == "spot":
            set_attrs(el, cutoff=lt.get("cutoff", 45), exponent=lt.get("exponent", 10))
        if lt.get("attenuation") is not None:
            set_attrs(el, attenuation=lt["attenuation"])


def build_ground(c: "Compiler", world, asset_el):
    g = c.spec.get("ground") or {}
    gtype = g.get("type", "plane")
    if gtype == "none":
        return
    mat = c.material(g.get("material", "grid"))
    fric_ref = g.get("friction", "concrete")
    condim = g.get("condim") or c.friction_condim(fric_ref) or c.defaults["condim"]
    cp = c.contact_profile(g.get("contact"))
    size = g.get("size", [20.0, 20.0])
    pos = g.get("pos", [0.0, 0.0, 0.0])
    world.append(ET.Comment(" ground "))

    if gtype == "plane":
        el = ET.SubElement(world, "geom")
        set_attrs(el, name=c.uniq("ground"), type="plane",
                  size=[size[0], size[1], g.get("grid_spacing", 1.0)],
                  pos=pos, material=mat, friction=c.friction(fric_ref), condim=int(condim))
        if cp:
            set_attrs(el, solref=cp["solref"], solimp=cp["solimp"])
        c.object_index.append({"name": "ground", "kind": "ground", "tags": ["floor"]})
        return

    # heightfield
    t = g.get("terrain") or {}
    res = int(t.get("resolution", 128))
    # The generated PNG is always normalised to [0, 1]; the world height comes
    # entirely from the hfield's z size. `terrain.amplitude` is the author-facing
    # way to say "how tall", `height_scale` overrides it when given explicitly.
    z_scale = float(g.get("height_scale") or max(0.05, float(t.get("amplitude", 0.3))))
    if t.get("kind") == "steps" and g.get("height_scale") is None:
        # For stairs the meaningful knob is the per-step rise, not total height.
        steps = max(2, int(t.get("step_count", 6)))
        z_scale = float(t.get("step_height", 0.15)) * (steps - 1)
        c.notes.append(
            f"terrain.kind='steps': total height is step_height x (step_count-1) = "
            f"{z_scale:.3f}m (set ground.height_scale for a direct override)")
    if g.get("elevation_file"):
        rel = c.stage_asset(g["elevation_file"])
        file_name = Path(rel).name
        meta = {"source": g["elevation_file"]}
    else:
        file_name = "terrain.png"
        rel = f"assets/{file_name}"
        c.pending_terrain = {
            "rel": rel,
            "kind": t.get("kind", "hills"),
            "res": res,
            "seed": int(t.get("seed", 0)),
            "frequency": float(t.get("frequency", 3.0)),
            "octaves": int(t.get("octaves", 4)),
            "flat_radius_frac": min(0.45, float(t.get("flat_radius", 0.0)) / max(1e-6, size[0] * 2)),
            "step_count": int(t.get("step_count", 6)),
            "slope_deg": float(t.get("slope", 0.0)),
        }
        c.assets.append(rel)
        meta = {"generated": True}
    c.hfield_asset = {"name": "terrain", "file": file_name,
                      "size": [size[0], size[1], z_scale, g.get("base_depth", 0.5)]}
    el = ET.SubElement(world, "geom")
    set_attrs(el, name=c.uniq("ground"), type="hfield", hfield="terrain", pos=pos,
              material=mat, friction=c.friction(fric_ref), condim=int(condim))
    if cp:
        set_attrs(el, solref=cp["solref"], solimp=cp["solimp"])
    c.object_index.append({"name": "ground", "kind": "ground", "tags": ["floor", "terrain"],
                           "meta": meta})
