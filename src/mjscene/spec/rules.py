"""Semantic checks for physics constraints beyond JSON Schema.

Examples include torsional friction ignored at condim=3 and moving objects starting inside the ground
or an excessive timestep. These may compile but behave incorrectly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import library
from . import assemblies as _assemblies
from .issues import suggest

if TYPE_CHECKING:                     # avoids a cycle: validator imports rules
    from .validator import Validator

__all__ = ["semantic_checks", "all_body_names"]


def all_body_names(spec: dict) -> set[str]:
    """Every body name the compiler will emit, including assemblies and repeats."""
    names: set[str] = set()

    def walk(objs):
        for o in objs or []:
            if not isinstance(o, dict):
                continue
            base = o.get("name") or o.get("shape", "box")
            rep = o.get("repeat")
            if isinstance(rep, dict):
                counts = [int(c) for c in (list(rep.get("count") or [1, 1, 1]) + [1, 1, 1])[:3]]
                total = max(1, counts[0]) * max(1, counts[1]) * max(1, counts[2])
                names.update(f"{base}_{i}" for i in range(total))
            else:
                names.add(base)
            walk(o.get("children"))

    walk(spec.get("objects"))
    for i, a in enumerate(spec.get("assemblies") or []):
        if not isinstance(a, dict) or a.get("type") not in _assemblies.BUILDERS:
            continue
        try:
            walk(_assemblies.expand(a, i))
        except Exception:
            pass                        # assembly errors are reported elsewhere
    # NB: the ground is a bare geom in <worldbody>, not a body — callers that
    # need it add the geom name "ground" themselves.
    return names


def semantic_checks(spec: dict, v: "Validator") -> None:
    """Physics-sanity checks that a schema cannot express."""
    ts = (spec.get("physics") or {}).get("timestep", library.DEFAULT_PHYSICS["timestep"])
    if ts > 0.005:
        v.warn("physics.timestep", f"{ts}s is large; rigid contacts may penetrate or become unstable",
               "Use 0.001-0.004 or set defaults.contact to 'soft'")

    shadow_casters = 0
    lighting = spec.get("lighting") or {}
    lights = lighting.get("lights")
    if not lights:
        lights = library.LIGHTING[lighting.get("preset", "noon")]["lights"]
    lights = list(lights) + list(lighting.get("extra_lights") or [])
    for lt in lights:
        if isinstance(lt, dict) and lt.get("castshadow", True):
            shadow_casters += 1
    if shadow_casters > 3:
        v.warn("lighting.lights", f"{shadow_casters} shadow-casting lights may significantly reduce web frame rate",
               "Set castshadow=false on secondary lights")

    expected = {"box": 3, "sphere": 1, "capsule": 2, "cylinder": 2, "ellipsoid": 3, "plane": 3}

    def walk(objs, path):
        for i, o in enumerate(objs or []):
            if not isinstance(o, dict):
                continue
            p = f"{path}[{i}]"
            shape = o.get("shape", "box")
            size = o.get("size")
            fromto = o.get("fromto")
            # With fromto the long axis comes from the two endpoints, so `size`
            # only carries the cross-section: radius (capsule/cylinder) or the
            # two half-widths (box/ellipsoid).
            needed = {"capsule": 1, "cylinder": 1, "box": 2, "ellipsoid": 2}.get(shape) \
                if fromto is not None else expected.get(shape)
            if shape == "mesh":
                if not o.get("mesh"):
                    v.err(f"{p}.mesh", "shape='mesh' requires a mesh name",
                          "Declare {name, file} in top-level meshes first")
            elif shape == "none":
                pass
            elif size is None:
                v.err(f"{p}.size", f"shape='{shape}' is missing size", f"Requires {needed} numbers")
            elif needed is not None and len(size) < needed:
                v.err(f"{p}.size", f"shape='{shape}' "
                                   f"{' (with fromto)' if fromto is not None else ''}"
                                   f"requires {needed} size components, got {len(size)}")
            elif fromto is None and needed is not None and len(size) != needed:
                v.err(f"{p}.size", f"shape='{shape}' requires {needed} size components; "
                                   f"got {len(size)}")
            if size and any(s <= 0 for s in size):
                v.err(f"{p}.size", "Sizes must be positive (MuJoCo uses half-sizes and radii)")
            if o.get("fromto") is not None and shape not in ("capsule", "cylinder", "box",
                                                             "ellipsoid"):
                v.err(f"{p}.fromto", f"shape='{shape}' does not support fromto",
                      "Only capsule, cylinder, box, and ellipsoid support endpoint definitions")
            rots = [k for k in ("euler", "quat", "axisangle") if o.get(k) is not None]
            if len(rots) > 1:
                v.err(p, f"Multiple rotation representations were supplied: {rots}", "Keep only one")
            if o.get("mass") is not None and o.get("density") is not None:
                v.warn(p, "Both mass and density were supplied; MuJoCo will ignore density")
            if o.get("kind") == "static" and (o.get("joint") or o.get("joints")):
                v.err(f"{p}.kind", "Static objects cannot have joints", "Use kind='articulated'")
            if o.get("kind") == "articulated" and not (o.get("joint") or o.get("joints")):
                v.err(f"{p}.joint", "kind='articulated' requires joint or joints")
            cd = o.get("condim")
            fr = o.get("friction")
            if cd in (1, 3) and isinstance(fr, str) and library.FRICTION.get(fr, {}).get("condim", 3) > cd:
                v.warn(f"{p}.condim", f"Friction model {fr!r} requires condim>={library.FRICTION[fr]['condim']} "
                                      f"to take effect; current value is {cd}")
            pos = o.get("pos") or [0, 0, 0]
            if o.get("kind", "dynamic") == "dynamic" and len(pos) == 3 and size and pos[2] < 0:
                v.warn(f"{p}.pos", "A dynamic object starts below z=0 and may become stuck under the ground")
            walk(o.get("children"), f"{p}.children")

    # Procedural assets require exactly one of file or generator
    for i, mesh in enumerate(spec.get("meshes") or []):
        if not isinstance(mesh, dict):
            continue
        has = [k for k in ("file", "generator") if mesh.get(k)]
        if not has:
            v.err(f"meshes[{i}]", "Specify either file or generator",
                  f"Available procedural meshes: {', '.join(library.MESH_GENERATORS)}")
        elif len(has) > 1:
            v.err(f"meshes[{i}]", "Specify only one of file and generator")

    spawn = spec.get("spawn") or {}
    bounds = spawn.get("bounds")
    if isinstance(bounds, list) and len(bounds) == 6:
        for axis, lo, hi in zip("xyz", bounds[:3], bounds[3:]):
            if lo >= hi:
                v.err("spawn.bounds", f"{axis} lower bound {lo} is not below upper bound {hi}",
                      "Order is [x_min,y_min,z_min,x_max,y_max,z_max]")
        pos = spawn.get("position") or [0.0, 0.0, 0.0]
        if len(pos) == 3 and any(not (bounds[i] <= pos[i] <= bounds[i + 3]) for i in range(3)):
            v.warn("spawn.position", f"Spawn point {pos} lies outside bounds",
                   "The robot starts outside the bounds and downstream invisible walls may push it out")

    for i, mat in enumerate(spec.get("materials") or []):
        tex = (mat or {}).get("texture")
        if isinstance(tex, dict) and tex.get("generator") and tex.get("file"):
            v.err(f"materials[{i}].texture", "Specify only one of generator and file")

    walk(spec.get("objects"), "objects")

    # `scatter` / `grid_of_boxes` take *lists* of material and shape names. Those
    # are plain strings in the schema, so without this a typo only surfaces as a
    # KeyError from deep inside the compiler.
    for i, a in enumerate(spec.get("assemblies") or []):
        if not isinstance(a, dict):
            continue
        for name in a.get("materials") or []:
            if isinstance(name, str) and name not in v.material_names:
                v.err(f"assemblies[{i}].materials", f"Undefined material {name!r}",
                      suggest(name, v.material_names, "Available materials"))
        for name in a.get("shapes") or []:
            if isinstance(name, str) and name not in library.SHAPES:
                v.err(f"assemblies[{i}].shapes", f"Unknown shape {name!r}",
                      suggest(name, library.SHAPES, "Available shapes"))
        if a.get("type") == "scatter" and a.get("region") is not None \
                and len(a["region"]) != 4:
            v.err(f"assemblies[{i}].region", "region must be [x_min, y_min, x_max, y_max]")

    names: dict[str, str] = {}

    def check_dup(name, where):
        if not name:
            return
        if name in names:
            v.err(where, f"Name {name!r} is duplicated (already used at {names[name]})", "MJCF requires unique names")
        else:
            names[name] = where

    def walk_names(objs, path):
        for i, o in enumerate(objs or []):
            if isinstance(o, dict):
                check_dup(o.get("name"), f"{path}[{i}].name")
                walk_names(o.get("children"), f"{path}[{i}].children")

    walk_names(spec.get("objects"), "objects")

    # contacts.pairs reference *geom* names, which the compiler derives as
    # "<object>_geom". Catch typos here rather than in a MuJoCo stack trace.
    contacts = spec.get("contacts") or {}
    if contacts.get("pairs") or contacts.get("excludes"):
        body_names = all_body_names(spec)
        # The ground is a bare geom named "ground"; everything else is "<body>_geom".
        geom_names = {f"{n}_geom" for n in body_names} | {"ground"}
        for i, p in enumerate(contacts.get("pairs") or []):
            if not isinstance(p, dict):
                continue
            for key in ("geom1", "geom2"):
                val = p.get(key)
                if isinstance(val, str) and val not in geom_names:
                    v.warn(f"contacts.pairs[{i}].{key}", f"Geom not found {val!r}",
                           suggest(val, geom_names, "Known geoms"))
        for i, x in enumerate(contacts.get("excludes") or []):
            if not isinstance(x, dict):
                continue
            for key in ("body1", "body2"):
                val = x.get(key)
                if isinstance(val, str) and val not in body_names:
                    v.warn(f"contacts.excludes[{i}].{key}", f"Body not found {val!r}",
                           suggest(val, body_names, "Known bodies"))

    for i, c in enumerate(spec.get("cameras") or []):
        if isinstance(c, dict):
            check_dup(c.get("name"), f"cameras[{i}].name")
    for i, m in enumerate(spec.get("materials") or []):
        if isinstance(m, dict) and m.get("name") in library.MATERIALS:
            v.warn(f"materials[{i}].name", f"{m['name']!r} overrides a preset material with the same name")
