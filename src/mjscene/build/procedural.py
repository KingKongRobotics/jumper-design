"""Procedural texture and mesh generators.

MuJoCo's built-in textures are limited to checker, gradient, and flat; they
cannot represent directional wood or fabric. It also lacks a rounded box
primitive, making soft furniture appear unnaturally sharp. These generators
use only the standard library, preserving the dependency-free compile path
through library, spec, and build (see tests/test_layering.py).

Text-bearing textures such as signs require an external image placed in
`workspace/<scene>/assets/` because the standard library cannot rasterize fonts.

Scenes declare generators without custom scripts:

    "materials": [{"name": "floor",
                   "texture": {"generator": "wood_planks", "params": {"seed": 3}},
                   "texrepeat": [3, 3], "texuniform": true}]
    "meshes":    [{"name": "cushion", "generator": "rounded_box",
                   "params": {"size": [0.6, 0.64, 0.11], "radius": 0.05}}]
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from .png import write_rgb

__all__ = ["TEXTURE_GENERATORS", "MESH_GENERATORS", "generate_texture", "generate_mesh",
           "describe"]


# --------------------------------------------------------------------------- #
# Textures
# --------------------------------------------------------------------------- #

def wood_planks(size: int = 512, plank_width: int = 64, stagger: int = 171,
                base: tuple = (176, 126, 78), tone_spread: float = 26,
                grain: float = 13, seam: float = 58, seed: int = 0) -> list:
    """Generate staggered wood planks.

    Choose a `stagger` coprime to `size` so neighboring seams do not align.
    """
    rng = random.Random(seed)
    cols = max(1, size // plank_width)
    # Give each plank its own tone, grain frequency and phase, and dark streaks.
    seg_max = ((size - 1) + (cols - 1) * stagger) // size + 2
    planks = {(c, s): {"tone": rng.uniform(-1, 1), "freq": rng.uniform(0.9, 2.2),
                       "phase": rng.uniform(0, math.tau),
                       "streaks": [(rng.uniform(0, 1), rng.uniform(0.02, 0.09),
                                    rng.uniform(-1, 1)) for _ in range(rng.randint(3, 6))]}
              for c in range(cols) for s in range(-1, seg_max)}

    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            col = min(cols - 1, x // plank_width)
            p = planks[(col, (y + col * stagger) // size)]
            u = (x % plank_width) / plank_width
            shade = p["tone"] * tone_spread
            shade += math.sin(u * p["freq"] * math.tau + p["phase"] + y * 0.012) * grain
            for pos, width, amp in p["streaks"]:
                d = abs(u - pos)
                if d < width:
                    shade += amp * grain * 1.6 * (1.0 - d / width)
            edge = min(u, 1.0 - u)                       # Darken both sides of a seam.
            if edge < 0.018:
                shade -= seam * (1.0 - edge / 0.018)
            v = ((y + col * stagger) % size) / size      # Crosswise seam.
            if v < 0.006 or v > 0.994:
                shade -= seam * 0.7
            row.append(tuple(base[k] + shade for k in range(3)))
        rows.append(row)
    return rows


def fabric_weave(size: int = 256, threads: int = 40, base: tuple = (196, 196, 200),
                 weave: float = 22, fuzz: float = 12, drape: float = 15,
                 seed: int = 7) -> list:
    """Generate plain weave with yarn variation, fiber noise, and broad undulation.

    `drape` adds broad variation. Without it, mipmapping can average the fine
    weave into a flat color at a distance.
    """
    rng = random.Random(seed)
    cell = size / threads
    warp = [rng.uniform(-1, 1) for _ in range(threads + 2)]
    weft = [rng.uniform(-1, 1) for _ in range(threads + 2)]

    rows = []
    for y in range(size):
        wy = min(threads, int(y / cell))
        row = []
        for x in range(size):
            wx = min(threads, int(x / cell))
            over = (wx + wy) % 2 == 0
            s = weave if over else -weave
            u = (x / cell - wx) * 2 - 1
            v = (y / cell - wy) * 2 - 1
            s += (math.cos((u if over else v) * math.pi / 2) - 0.62) * weave * 0.9
            s += (warp[wx] if over else weft[wy]) * weave * 0.35
            s += rng.uniform(-fuzz, fuzz) * 0.5
            s += drape * math.sin(math.tau * x / size) * math.sin(math.tau * y / size)
            row.append(tuple(base[k] + s for k in range(3)))
        rows.append(row)
    return rows


TEXTURE_GENERATORS = {
    "wood_planks": (wood_planks, "Staggered wood planks with seams, grain, and color variation"),
    "fabric_weave": (fabric_weave, "Plain weave with yarn variation and broad undulation"),
}


# --------------------------------------------------------------------------- #
# Meshes
# --------------------------------------------------------------------------- #

def rounded_box(size=(0.5, 0.5, 0.5), radius: float = 0.05, segments: int = 12,
                uv_tiles: float = 6.0):
    """Return vertices, UVs, and triangles for a rounded box.

    This is the Minkowski sum of an inner box and a sphere. Mesh all six outer
    faces, clamp each point to the inner box, then offset outward by radius.
    Faces stay flat, edges and corners round, and the result remains convex.

    Avoid the earlier translated-sphere-octant method: entire vertex rings
    collapsed at its poles and corrupted dimensions. This mesh has no poles.

    UVs use meters multiplied by uv_tiles. MuJoCo does not apply texrepeat to
    meshes with explicit UVs, so tiling density must be baked into the UVs.
    """
    L, W, H = size
    r = min(radius, L / 2 - 1e-4, W / 2 - 1e-4, H / 2 - 1e-4)
    if r <= 0:
        raise ValueError(f"rounded_box: radius {radius} is too large for size {size} (or the box is too thin)")
    a = (L / 2 - r, W / 2 - r, H / 2 - r)
    b = (L / 2, W / 2, H / 2)
    n_seg = max(2, int(segments))

    def project(p):
        q = [max(-a[k], min(a[k], p[k])) for k in range(3)]
        d = [p[k] - q[k] for k in range(3)]
        n = math.sqrt(sum(c * c for c in d)) or 1.0
        return tuple(q[k] + d[k] / n * r for k in range(3))

    verts, uvs, faces = [], [], []
    for axis in range(3):
        for sign in (1, -1):
            u_ax, v_ax = (axis + 1) % 3, (axis + 2) % 3
            base_i = len(verts)
            for i in range(n_seg + 1):
                for j in range(n_seg + 1):
                    p = [0.0, 0.0, 0.0]
                    p[axis] = sign * b[axis]
                    p[u_ax] = (2 * i / n_seg - 1) * b[u_ax]
                    p[v_ax] = (2 * j / n_seg - 1) * b[v_ax]
                    verts.append(project(p))
                    uvs.append((p[u_ax] * uv_tiles, p[v_ax] * uv_tiles))
            for i in range(n_seg):
                for j in range(n_seg):
                    v00 = base_i + i * (n_seg + 1) + j
                    v10, v01, v11 = v00 + n_seg + 1, v00 + 1, v00 + n_seg + 2
                    if sign > 0:
                        faces += [(v00, v10, v11), (v00, v11, v01)]
                    else:                                  # Reverse winding for outward normals.
                        faces += [(v00, v11, v10), (v00, v01, v11)]
    return verts, uvs, faces


MESH_GENERATORS = {
    "rounded_box": (rounded_box, "Rounded box for soft furniture such as mattresses and cushions"),
}


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

def _call(table: dict, kind: str, name: str, params: dict | None):
    if name not in table:
        raise KeyError(f"Unknown {kind} generator {name!r}; available: {', '.join(sorted(table))}")
    fn = table[name][0]
    allowed = set(fn.__code__.co_varnames[:fn.__code__.co_argcount])
    bad = set(params or {}) - allowed
    if bad:
        raise KeyError(f"{name} does not accept parameters {sorted(bad)}; available: {', '.join(sorted(allowed))}")
    return fn(**(params or {}))


def generate_texture(name: str, path: Path, params: dict | None = None) -> None:
    write_rgb(Path(path), _call(TEXTURE_GENERATORS, "texture", name, params))


def generate_mesh(name: str, path: Path, params: dict | None = None) -> None:
    verts, uvs, faces = _call(MESH_GENERATORS, "mesh", name, params)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# generated by mjscene: {name}\n")
        for x, y, z in verts:
            fh.write(f"v {x:.5f} {y:.5f} {z:.5f}\n")
        for u, v in uvs:
            fh.write(f"vt {u:.5f} {v:.5f}\n")
        for a, b, c in faces:                              # OBJ indexes start at 1.
            fh.write(f"f {a+1}/{a+1} {b+1}/{b+1} {c+1}/{c+1}\n")


def describe() -> str:
    lines = ["Texture generators (materials[].texture.generator):"]
    lines += [f"  {n:<14} {d}" for n, (_, d) in sorted(TEXTURE_GENERATORS.items())]
    lines += ["Mesh generators (meshes[].generator):"]
    lines += [f"  {n:<14} {d}" for n, (_, d) in sorted(MESH_GENERATORS.items())]
    return "\n".join(lines)
