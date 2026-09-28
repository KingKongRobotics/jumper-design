"""Procedural heightfield generation.

MuJoCo reads heightfields from a grayscale PNG, so this module contains a tiny
dependency-free PNG writer plus a few seeded terrain generators. Same seed ->
same terrain, which matters for reproducible robot experiments.
"""

from __future__ import annotations

import math
import random

from .png import write_gray


# --------------------------------------------------------------------------- #
# Value noise
# --------------------------------------------------------------------------- #


def _lattice(seed: int, size: int = 256) -> list[list[float]]:
    rng = random.Random(seed)
    return [[rng.random() for _ in range(size)] for _ in range(size)]


def _smooth(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)                      # smoothstep


def _value_noise(grid, x: float, y: float) -> float:
    n = len(grid)
    x0, y0 = int(math.floor(x)) % n, int(math.floor(y)) % n
    x1, y1 = (x0 + 1) % n, (y0 + 1) % n
    fx, fy = _smooth(x - math.floor(x)), _smooth(y - math.floor(y))
    a = grid[y0][x0] * (1 - fx) + grid[y0][x1] * fx
    b = grid[y1][x0] * (1 - fx) + grid[y1][x1] * fx
    return a * (1 - fy) + b * fy


def _fbm(grid, x: float, y: float, octaves: int) -> float:
    total, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
    for _ in range(octaves):
        total += amp * _value_noise(grid, x * freq, y * freq)
        norm += amp
        amp *= 0.5
        freq *= 2.0
    return total / norm


# --------------------------------------------------------------------------- #
# Generators: return a resolution x resolution field normalised to [0, 1]
# --------------------------------------------------------------------------- #


def generate_field(kind: str, res: int, *, seed: int = 0, frequency: float = 3.0,
                   octaves: int = 4, flat_radius_frac: float = 0.0,
                   step_count: int = 6, slope_deg: float = 0.0) -> list[list[float]]:
    grid = _lattice(seed + 1)
    field = [[0.0] * res for _ in range(res)]
    rng = random.Random(seed + 7)

    bumps = []
    if kind == "bumps":
        for _ in range(max(4, int(frequency) * 4)):
            bumps.append((rng.uniform(0, 1), rng.uniform(0, 1),
                          rng.uniform(0.03, 0.12), rng.uniform(0.4, 1.0)))

    for j in range(res):
        for i in range(res):
            u, v = i / (res - 1), j / (res - 1)
            if kind == "flat":
                h = 0.0
            elif kind == "hills":
                h = _fbm(grid, u * frequency, v * frequency, octaves)
            elif kind == "rough":
                h = _fbm(grid, u * frequency * 4, v * frequency * 4, max(octaves, 5))
            elif kind == "bumps":
                h = 0.0
                for bx, by, br, bh in bumps:
                    d2 = (u - bx) ** 2 + (v - by) ** 2
                    h += bh * math.exp(-d2 / (2 * br * br))
                h = min(1.0, h)
            elif kind == "dunes":
                ridge = math.sin((u * frequency + _fbm(grid, u * 2, v * 2, 3) * 1.5) * math.pi)
                h = 0.5 + 0.5 * ridge
                h *= 0.6 + 0.4 * _fbm(grid, u * frequency, v * frequency, 3)
            elif kind == "crater":
                d = math.hypot(u - 0.5, v - 0.5) * 2.0
                rim = math.exp(-((d - 0.55) ** 2) / 0.02)
                bowl = -math.exp(-(d ** 2) / 0.08)
                h = 0.5 + 0.5 * (rim + bowl) + 0.15 * _fbm(grid, u * 8, v * 8, 3)
            elif kind == "slope":
                # A linear ramp along +x. The field is normalised below, so the real
                # grade comes from ground.height_scale / ground.size; `slope` only
                # controls how much noise rides on top.
                h = u + (0.05 if slope_deg == 0 else 0.02) * _fbm(
                    grid, u * frequency, v * frequency, 2)
            elif kind == "steps":
                h = math.floor(u * step_count) / max(1, step_count - 1)
            else:
                raise ValueError(f"unknown terrain kind {kind!r}")
            field[j][i] = h

    lo = min(min(r) for r in field)
    hi = max(max(r) for r in field)
    span = (hi - lo) or 1.0
    for j in range(res):
        for i in range(res):
            field[j][i] = (field[j][i] - lo) / span

    # Flatten a disc in the middle so a robot can be spawned on level ground.
    if flat_radius_frac > 0:
        cx = cy = 0.5
        inner = flat_radius_frac
        outer = min(0.5, inner * 1.8 + 0.05)
        base = field[res // 2][res // 2]
        for j in range(res):
            for i in range(res):
                d = math.hypot(i / (res - 1) - cx, j / (res - 1) - cy)
                if d <= inner:
                    field[j][i] = base
                elif d < outer:
                    t = _smooth((d - inner) / (outer - inner))
                    field[j][i] = base * (1 - t) + field[j][i] * t
    return field


write_gray_png = write_gray   # Compatibility alias for the former name.


def write_heightfield(path, kind: str, res: int, **kwargs) -> dict:
    """Generate a terrain PNG. Returns metadata for the viewer sidecar."""
    field = generate_field(kind, res, **kwargs)
    rows = [[v * 255.0 for v in row] for row in field]
    write_gray(path, rows)
    return {"kind": kind, "resolution": res, "seed": kwargs.get("seed", 0),
            "min": 0.0, "max": 1.0}
