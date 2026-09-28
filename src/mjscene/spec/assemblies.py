"""Prefabs: one assembly entry expands into ordinary OBJECT dicts.

Because the output is plain spec objects, assemblies get validated, repeated,
materialised and compiled through exactly the same code path as hand-written
objects — there is no second implementation to keep in sync.

Static assemblies are wrapped in a single static container object so that the
assembly's `pos` / `euler` rotates the whole thing. Assemblies that spawn
free-floating bodies (`scatter`, `grid_of_boxes`) return top-level objects.
"""

from __future__ import annotations

import math
import random

Obj = dict


def _geom(name: str, shape: str, size, pos, **kw) -> Obj:
    o: Obj = {"name": name, "shape": shape, "size": list(size), "pos": list(pos)}
    o.update({k: v for k, v in kw.items() if v is not None})
    return o


def _container(name: str, pos, euler, children: list[Obj], material=None,
               friction=None, group=None, tags=None) -> Obj:
    # The container is a pure transform frame (no geom); children carry the shapes.
    o: Obj = {"name": name, "kind": "static", "shape": "none",
              "pos": list(pos), "children": children}
    if euler is not None:
        o["euler"] = list(euler)
    if material:
        o["material"] = material
    if friction is not None:
        o["friction"] = friction
    if group is not None:
        o["group"] = group
    if tags:
        o["tags"] = list(tags)
    return o


def _child(name, shape, size, pos, **kw) -> Obj:
    o = _geom(name, shape, size, pos, **kw)
    o["kind"] = "static"
    return o


# --------------------------------------------------------------------------- #
# Individual prefabs
# --------------------------------------------------------------------------- #


def _room(a: dict, name: str) -> list[Obj]:
    L, W, H = (a.get("size") or [10.0, 8.0, 3.0])[:3]
    t = a.get("thickness") or 0.15
    mat = a.get("material") or "wall_paint"
    openings = {o.lower() for o in (a.get("openings") or [])}
    kids: list[Obj] = []
    half = t / 2.0
    walls = {
        "north": ([L / 2, half, H / 2], [0.0, W / 2 - half, H / 2]),
        "south": ([L / 2, half, H / 2], [0.0, -W / 2 + half, H / 2]),
        "east": ([half, W / 2, H / 2], [L / 2 - half, 0.0, H / 2]),
        "west": ([half, W / 2, H / 2], [-L / 2 + half, 0.0, H / 2]),
    }
    for side, (size, pos) in walls.items():
        if side in openings:
            continue
        kids.append(_child(f"{name}_wall_{side}", "box", size, pos, material=mat,
                           friction=a.get("friction")))
    if a.get("ceiling"):
        kids.append(_child(f"{name}_ceiling", "box", [L / 2, W / 2, half], [0, 0, H],
                           material=a.get("material_2") or mat))
    return [_container(name, a.get("pos") or [0, 0, 0], a.get("euler"), kids,
                       group=a.get("group"), tags=a.get("tags"))]


def _table(a: dict, name: str) -> list[Obj]:
    L, W, H = (a.get("size") or [1.4, 0.8, 0.75])[:3]
    top_t = a.get("thickness") or 0.05
    leg = 0.05
    mat = a.get("material") or "wood"
    top_mat = a.get("material_2") or mat
    kids = [_child(f"{name}_top", "box", [L / 2, W / 2, top_t / 2], [0, 0, H - top_t / 2],
                   material=top_mat, friction=a.get("friction"), condim=4)]
    inset = leg + 0.03
    for sx in (-1, 1):
        for sy in (-1, 1):
            kids.append(_child(
                f"{name}_leg_{'p' if sx > 0 else 'n'}{'p' if sy > 0 else 'n'}",
                "box", [leg, leg, (H - top_t) / 2],
                [sx * (L / 2 - inset), sy * (W / 2 - inset), (H - top_t) / 2], material=mat))
    return [_container(name, a.get("pos") or [0, 0, 0], a.get("euler"), kids,
                       group=a.get("group"), tags=a.get("tags"))]


def _shelf(a: dict, name: str) -> list[Obj]:
    L, W, H = (a.get("size") or [1.0, 0.4, 1.8])[:3]
    levels = a.get("levels") or 4
    t = a.get("thickness") or 0.03
    mat = a.get("material") or "steel_dark"
    kids = []
    for side, sx in (("l", -1), ("r", 1)):
        kids.append(_child(f"{name}_side_{side}", "box", [t / 2, W / 2, H / 2],
                           [sx * (L / 2 - t / 2), 0, H / 2], material=mat))
    kids.append(_child(f"{name}_back", "box", [L / 2, t / 2, H / 2],
                       [0, -W / 2 + t / 2, H / 2], material=mat))
    for i in range(levels):
        z = (H - t) * (i / max(1, levels - 1)) + t / 2 if levels > 1 else H / 2
        kids.append(_child(f"{name}_level_{i}", "box", [L / 2 - t, W / 2, t / 2], [0, 0, z],
                           material=a.get("material_2") or mat, condim=4,
                           friction=a.get("friction")))
    return [_container(name, a.get("pos") or [0, 0, 0], a.get("euler"), kids,
                       group=a.get("group"), tags=a.get("tags"))]


def _stairs(a: dict, name: str) -> list[Obj]:
    steps = a.get("steps") or 6
    rise = a.get("rise") if a.get("rise") is not None else 0.15
    run = a.get("run") if a.get("run") is not None else 0.3
    width = a.get("width") or 1.2
    mat = a.get("material") or "concrete"
    kids = []
    for i in range(steps):
        h = rise * (i + 1)
        kids.append(_child(f"{name}_step_{i}", "box", [run / 2, width / 2, h / 2],
                           [run * (i + 0.5), 0.0, h / 2], material=mat,
                           friction=a.get("friction"), condim=4))
    return [_container(name, a.get("pos") or [0, 0, 0], a.get("euler"), kids,
                       group=a.get("group"), tags=a.get("tags"))]


def _ramp(a: dict, name: str) -> list[Obj]:
    L, W = (a.get("size") or [2.0, 1.2])[:2]
    angle = a.get("angle") if a.get("angle") is not None else 15.0
    t = a.get("thickness") or 0.06
    mat = a.get("material") or "rubber"
    rad = math.radians(angle)
    # Centre the slab so its lower edge sits on z = 0 of the container frame.
    kids = [_child(f"{name}_slab", "box", [L / 2, W / 2, t / 2],
                   [0.0, 0.0, L / 2 * math.sin(rad) + t / 2 * math.cos(rad)],
                   euler=[0.0, -angle, 0.0], material=mat, friction=a.get("friction"),
                   condim=4)]
    return [_container(name, a.get("pos") or [0, 0, 0], a.get("euler"), kids,
                       group=a.get("group"), tags=a.get("tags"))]


def _platform(a: dict, name: str) -> list[Obj]:
    L, W, H = (a.get("size") or [2.0, 2.0, 0.4])[:3]
    mat = a.get("material") or "concrete"
    kids = [_child(f"{name}_slab", "box", [L / 2, W / 2, H / 2], [0, 0, H / 2],
                   material=mat, friction=a.get("friction"), condim=4)]
    return [_container(name, a.get("pos") or [0, 0, 0], a.get("euler"), kids,
                       group=a.get("group"), tags=a.get("tags"))]


def _pillars(a: dict, name: str) -> list[Obj]:
    count = a.get("count") or 6
    r = (a.get("size") or [0.12])[0]
    h = a.get("height") or 2.5
    spacing = a.get("spacing") or [2.0, 2.0]
    mat = a.get("material") or "concrete"
    seed = a.get("seed", 0)
    rng = random.Random(seed)
    kids = []
    per_row = max(1, int(math.ceil(math.sqrt(count))))
    for i in range(count):
        gx, gy = i % per_row, i // per_row
        jitter = 0.0 if a.get("seed") is None else 0.25
        x = (gx - (per_row - 1) / 2) * spacing[0] + rng.uniform(-jitter, jitter)
        y = (gy - (per_row - 1) / 2) * spacing[min(1, len(spacing) - 1)] + rng.uniform(-jitter, jitter)
        kids.append(_child(f"{name}_pillar_{i}", "cylinder", [r, h / 2], [x, y, h / 2],
                           material=mat, friction=a.get("friction")))
    return [_container(name, a.get("pos") or [0, 0, 0], a.get("euler"), kids,
                       group=a.get("group"), tags=a.get("tags"))]


def _fence(a: dict, name: str) -> list[Obj]:
    L = (a.get("size") or [6.0])[0]
    h = a.get("height") or 1.0
    t = a.get("thickness") or 0.05
    posts = a.get("count") or max(2, int(L / 1.5) + 1)
    mat = a.get("material") or "steel_dark"
    kids = [_child(f"{name}_rail_top", "box", [L / 2, t / 2, t / 2], [0, 0, h - t],
                   material=mat),
            _child(f"{name}_rail_mid", "box", [L / 2, t / 2, t / 2], [0, 0, h * 0.5],
                   material=mat)]
    for i in range(posts):
        x = -L / 2 + L * i / max(1, posts - 1)
        kids.append(_child(f"{name}_post_{i}", "box", [t, t, h / 2], [x, 0, h / 2],
                           material=mat))
    return [_container(name, a.get("pos") or [0, 0, 0], a.get("euler"), kids,
                       group=a.get("group"), tags=a.get("tags"))]


def _bin(a: dict, name: str) -> list[Obj]:
    L, W, H = (a.get("size") or [0.6, 0.4, 0.25])[:3]
    t = a.get("thickness") or 0.02
    mat = a.get("material") or "plastic_blue"
    fric = a.get("friction") or "plastic"
    kids = [_child(f"{name}_bottom", "box", [L / 2, W / 2, t / 2], [0, 0, t / 2],
                   material=mat, friction=fric, condim=4)]
    for side, size, pos in (
            ("n", [L / 2, t / 2, H / 2], [0, W / 2 - t / 2, H / 2]),
            ("s", [L / 2, t / 2, H / 2], [0, -W / 2 + t / 2, H / 2]),
            ("e", [t / 2, W / 2, H / 2], [L / 2 - t / 2, 0, H / 2]),
            ("w", [t / 2, W / 2, H / 2], [-L / 2 + t / 2, 0, H / 2])):
        kids.append(_child(f"{name}_wall_{side}", "box", size, pos, material=mat,
                           friction=fric, condim=4))
    return [_container(name, a.get("pos") or [0, 0, 0], a.get("euler"), kids,
                       group=a.get("group"), tags=a.get("tags"))]


def _conveyor(a: dict, name: str) -> list[Obj]:
    L, W, H = (a.get("size") or [4.0, 0.8, 0.6])[:3]
    mat = a.get("material") or "steel_dark"
    belt = a.get("material_2") or "rubber"
    kids = [_child(f"{name}_surface", "box", [L / 2, W / 2, 0.02], [0, 0, H],
                   material=belt, friction=a.get("friction") or "rubber", condim=4)]
    for i, x in enumerate((-L / 2 + 0.15, 0.0, L / 2 - 0.15)):
        kids.append(_child(f"{name}_frame_{i}", "box", [0.06, W / 2, H / 2], [x, 0, H / 2],
                           material=mat))
    for side, sy in (("l", -1), ("r", 1)):
        kids.append(_child(f"{name}_guard_{side}", "box", [L / 2, 0.02, 0.06],
                           [0, sy * W / 2, H + 0.06], material=mat))
    return [_container(name, a.get("pos") or [0, 0, 0], a.get("euler"), kids,
                       group=a.get("group"), tags=a.get("tags"))]


def _target_pad(a: dict, name: str) -> list[Obj]:
    r = (a.get("size") or [0.25])[0]
    mat = a.get("material") or "target_marker"
    pos = a.get("pos") or [0, 0, 0]
    return [{"name": name, "kind": "static", "shape": "cylinder", "size": [r, 0.002],
             "pos": [pos[0], pos[1], pos[2] + 0.002], "material": mat,
             "collision": False, "group": a.get("group") or 0,
             "tags": (a.get("tags") or []) + ["target"]}]


def _scatter(a: dict, name: str) -> list[Obj]:
    region = a.get("region") or [-2.0, -2.0, 2.0, 2.0]
    x0, y0, x1, y1 = region[:4]
    count = a.get("count") or 12
    shapes = a.get("shapes") or ["box", "sphere", "cylinder"]
    mats = a.get("materials") or ["cardboard", "plastic_red", "plastic_blue", "wood"]
    sr = a.get("size_range") or [0.04, 0.04, 0.04, 0.14, 0.14, 0.14]
    half = len(sr) // 2
    lo, hi = sr[:half], sr[half:]
    mass_lo, mass_hi = (a.get("mass_range") or [0.2, 2.0])[:2]
    z = a.get("z") if a.get("z") is not None else 0.35
    rng = random.Random(a.get("seed", 0))
    base = a.get("pos") or [0, 0, 0]
    out: list[Obj] = []
    for i in range(count):
        shape = rng.choice(shapes)
        dims = [rng.uniform(lo[min(k, len(lo) - 1)], hi[min(k, len(hi) - 1)]) for k in range(3)]
        if shape == "sphere":
            size = [dims[0]]
        elif shape in ("capsule", "cylinder"):
            size = [dims[0], dims[2]]
        else:
            size = dims
        out.append({
            "name": f"{name}_{i}",
            "shape": shape,
            "size": size,
            "pos": [base[0] + rng.uniform(x0, x1), base[1] + rng.uniform(y0, y1),
                    base[2] + z + rng.uniform(0.0, 0.25)],
            "euler": [rng.uniform(-180, 180) for _ in range(3)],
            "kind": "static" if a.get("dynamic") is False else "dynamic",
            "mass": round(rng.uniform(mass_lo, mass_hi), 3),
            "material": rng.choice(mats),
            "friction": a.get("friction") or "cardboard",
            "condim": a.get("condim", 4),
            "contact": a.get("contact"),
            "group": a.get("group") or 0,
            "tags": (a.get("tags") or []) + ["clutter"],
        })
    return out


def _grid_of_boxes(a: dict, name: str) -> list[Obj]:
    size = a.get("size") or [0.12, 0.12, 0.12]
    spacing = a.get("spacing") or [0.4, 0.4, 0.3]
    counts = a.get("count") or 8
    nx = max(1, int(round(math.sqrt(counts))))
    ny = max(1, int(math.ceil(counts / nx)))
    base = a.get("pos") or [0, 0, 0]
    z = a.get("z") if a.get("z") is not None else size[2]
    out = []
    n = 0
    for iy in range(ny):
        for ix in range(nx):
            if n >= counts:
                break
            out.append({
                "name": f"{name}_{n}", "shape": "box", "size": list(size),
                "pos": [base[0] + (ix - (nx - 1) / 2) * spacing[0],
                        base[1] + (iy - (ny - 1) / 2) * spacing[1],
                        base[2] + z],
                "kind": "static" if a.get("dynamic") is False else "dynamic",
                "material": a.get("material") or "cardboard",
                "friction": a.get("friction") or "cardboard",
                "condim": a.get("condim", 4), "contact": a.get("contact"),
                "group": a.get("group") or 0,
                "tags": (a.get("tags") or []) + ["crate"],
            })
            n += 1
    return out


def _obstacle_course(a: dict, name: str) -> list[Obj]:
    """A canonical locomotion test strip: ramp -> steps -> gap -> pillars -> platform."""
    length = (a.get("size") or [16.0, 3.0])[0]
    width = (a.get("size") or [16.0, 3.0])[1] if len(a.get("size") or []) > 1 else 3.0
    mat = a.get("material") or "concrete"
    fric = a.get("friction") or "concrete"
    seg = length / 5.0
    out: list[Obj] = []
    out += _ramp({"pos": [0.0, 0.0, 0.0], "size": [seg, width], "angle": a.get("angle") or 12,
                  "material": mat, "friction": fric}, f"{name}_ramp")
    out += _stairs({"pos": [seg * 1.2, 0.0, 0.0], "steps": a.get("steps") or 6,
                    "rise": a.get("rise") or 0.12, "run": a.get("run") or 0.3,
                    "width": width, "material": mat, "friction": fric}, f"{name}_stairs")
    out += _platform({"pos": [seg * 2.3, 0.0, 0.0], "size": [seg * 0.8, width, 0.72],
                      "material": mat, "friction": fric}, f"{name}_gapA")
    out += _platform({"pos": [seg * 3.1, 0.0, 0.0], "size": [seg * 0.8, width, 0.72],
                      "material": mat, "friction": fric}, f"{name}_gapB")
    out += _pillars({"pos": [seg * 4.0, 0.0, 0.0], "count": 6, "size": [0.1], "height": 1.2,
                     "spacing": [0.9, 0.9], "material": "safety_orange", "seed": a.get("seed", 3)},
                    f"{name}_pillars")
    base = a.get("pos") or [0, 0, 0]
    for o in out:                                   # shift the whole strip
        o["pos"] = [o["pos"][0] + base[0], o["pos"][1] + base[1], o["pos"][2] + base[2]]
    return out


BUILDERS = {
    "room": _room,
    "walls": lambda a, n: _room({**a, "ceiling": False}, n),
    "table": _table,
    "shelf": _shelf,
    "stairs": _stairs,
    "ramp": _ramp,
    "platform": _platform,
    "pillars": _pillars,
    "fence": _fence,
    "bin": _bin,
    "conveyor": _conveyor,
    "scatter": _scatter,
    "grid_of_boxes": _grid_of_boxes,
    "obstacle_course": _obstacle_course,
    "target_pad": _target_pad,
}

# Documentation for `mjscene list assemblies`.
DOCS = {
    "room": "Four walls and optional ceiling. size=[length,width,height], thickness, openings=['north',...], ceiling",
    "walls": "Like room, but without a ceiling",
    "table": "Tabletop and four legs. size=[length,width,height], material=legs, material_2=top",
    "shelf": "Multilevel shelf. size=[length,width,height], levels, thickness",
    "stairs": "Stairs. steps, rise, run, width",
    "ramp": "Ramp. size=[length,width], angle(deg), thickness",
    "platform": "Platform. size=[length,width,height]",
    "pillars": "Pillar array. count, size=[radius], height, spacing=[dx,dy], seed",
    "fence": "Fence. size=[length], height, count=post count",
    "bin": "Bin or container. size=[length,width,height], thickness",
    "conveyor": "Static conveyor geometry. size=[length,width,height]",
    "scatter": "Scattered objects. region=[x0,y0,x1,y1], count, shapes, materials, size_range, mass_range, seed, z",
    "grid_of_boxes": "Box grid. count, size, spacing, z",
    "obstacle_course": "Legged/mobile robot course: ramp, stairs, gap, pillars. size=[total length,width]",
    "target_pad": "Translucent non-colliding target pad. size=[radius]",
}


def expand(assembly: dict, index: int) -> list[Obj]:
    kind = assembly.get("type")
    if kind not in BUILDERS:
        raise ValueError(f"unknown assembly type {kind!r}; known: {sorted(BUILDERS)}")
    name = assembly.get("name") or f"{kind}_{index}"
    return BUILDERS[kind](assembly, name)
