"""Catalog of shapes, assemblies, terrain generators, and physics defaults."""

from __future__ import annotations

__all__ = ["SHAPES", "ASSEMBLIES", "TERRAIN_KINDS", "DEFAULT_PHYSICS",
           "TEXTURE_GENERATORS", "MESH_GENERATORS"]

# Procedural asset generators are implemented in build/procedural.py. Register
# names here so the spec layer can use them as enums without importing build.
TEXTURE_GENERATORS = ["wood_planks", "fabric_weave"]
MESH_GENERATORS = ["rounded_box"]


TERRAIN_KINDS = ["hills", "rough", "bumps", "dunes", "crater", "slope", "steps", "flat"]

# Assembly (prefab) types understood by the compiler.
ASSEMBLIES = ["room", "walls", "table", "shelf", "stairs", "ramp", "platform",
              "pillars", "fence", "bin", "conveyor", "scatter", "grid_of_boxes",
              "obstacle_course", "target_pad"]

# "none" = a body with no geom, used as a transform frame for children.
SHAPES = ["box", "sphere", "capsule", "cylinder", "ellipsoid", "mesh", "plane", "none"]

# Sensible starting point for a brand-new scene.
DEFAULT_PHYSICS = {
    "timestep": 0.002,
    "gravity": [0.0, 0.0, -9.81],
    "integrator": "implicitfast",
    "solver": "Newton",
    "iterations": 100,
    "ls_iterations": 50,
    "cone": "pyramidal",
    "impratio": 1.0,
}
