"""Starter scenes. These double as few-shot examples for the AI layer, so they
are written to be *readable* rather than exhaustive: each one shows a different
combination of ground / lighting / friction / assembly features.
"""

from __future__ import annotations

SCHEMA_REF = "../schemas/scene.schema.json"


def _base(name: str, title: str, description: str) -> dict:
    return {"$schema": SCHEMA_REF, "name": name, "title": title, "description": description}


TEMPLATES: dict[str, dict] = {}

# --------------------------------------------------------------------------- #
TEMPLATES["minimal"] = {
    **_base("minimal", "Minimal scene", "A flat ground plane and a falling box for validating the toolchain."),
    "objects": [
        {"name": "box_1", "shape": "box", "size": [0.15, 0.15, 0.15], "pos": [0, 0, 0.8],
         "material": "plastic_red", "friction": "plastic", "mass": 1.0},
    ],
}

# --------------------------------------------------------------------------- #
TEMPLATES["warehouse"] = {
    **_base("warehouse", "Warehouse sorting",
            "Indoor warehouse with concrete floor, shelves, conveyor, bins, and scattered cartons. Suitable for AMR and sorting robots."),
    "tags": ["indoor", "mobile-robot", "manipulation"],
    "physics": {"timestep": 0.002, "integrator": "implicitfast", "cone": "pyramidal",
                "impratio": 10},
    "sky": {"preset": "indoor"},
    "lighting": {"preset": "warehouse", "shadow_quality": "high"},
    "ground": {"type": "plane", "size": [15, 12], "material": "concrete",
               "friction": "concrete", "condim": 3},
    "defaults": {"condim": 4, "friction": "cardboard", "contact": "default"},
    "assemblies": [
        {"type": "room", "name": "hall", "size": [24, 18, 5], "thickness": 0.2,
         "material": "wall_paint", "openings": ["south"]},
        {"type": "shelf", "name": "rack_a", "pos": [-4, 3, 0], "size": [3.0, 0.8, 2.4],
         "levels": 4, "material": "steel_dark", "material_2": "wood"},
        {"type": "shelf", "name": "rack_b", "pos": [-4, -3, 0], "size": [3.0, 0.8, 2.4],
         "levels": 4, "material": "steel_dark", "material_2": "wood"},
        {"type": "conveyor", "name": "belt", "pos": [3, 0, 0], "size": [6.0, 0.9, 0.7],
         "euler": [0, 0, 90]},
        {"type": "bin", "name": "tote", "pos": [1.2, -2.4, 0], "size": [0.6, 0.4, 0.3],
         "material": "plastic_blue"},
        {"type": "grid_of_boxes", "name": "carton", "pos": [3, 2.0, 0], "count": 6,
         "size": [0.18, 0.14, 0.12], "spacing": [0.5, 0.45, 0], "z": 0.85,
         "material": "cardboard"},
        {"type": "scatter", "name": "debris", "region": [-1.5, -1.5, 1.5, 1.5],
         "pos": [0, 4.0, 0], "count": 10, "seed": 11, "z": 0.3,
         "shapes": ["box", "cylinder"], "materials": ["cardboard", "wood"],
         "size_range": [0.05, 0.05, 0.04, 0.16, 0.16, 0.12], "mass_range": [0.3, 2.5]},
        {"type": "target_pad", "name": "dropoff", "pos": [0, -5.0, 0], "size": [0.5]},
    ],
    "objects": [
        {"name": "pallet", "shape": "box", "size": [0.6, 0.5, 0.06], "pos": [0, 1.2, 0.06],
         "kind": "static", "material": "wood", "friction": "wood"},
        {"name": "payload", "shape": "box", "size": [0.25, 0.25, 0.25], "pos": [0, 1.2, 0.4],
         "material": "cardboard", "friction": "cardboard", "mass": 4.0, "condim": 4},
    ],
    "cameras": [
        {"name": "cam_overview", "pos": [7, -9, 5], "target": [0, 0, 0.8], "fovy": 55},
        {"name": "cam_belt", "pos": [3, -3.2, 1.6], "target": [3, 0, 0.8], "fovy": 45},
    ],
    "viewer": {"camera_pos": [8, -10, 5.5], "camera_target": [0, 0, 0.8]},
}

# --------------------------------------------------------------------------- #
TEMPLATES["rough_terrain"] = {
    **_base("rough_terrain", "Rough terrain",
            "Outdoor heightfield and obstacle course for legged or wheeled robot locomotion tests."),
    "tags": ["outdoor", "legged", "locomotion"],
    "physics": {"timestep": 0.002, "integrator": "implicitfast", "cone": "elliptic",
                "impratio": 20, "iterations": 150},
    # Heightfield contacts are prism-based and tolerate less overlap than a plane,
    # so keep them stiff: rocks rolling on soft hfield contacts sink visibly.
    "defaults": {"condim": 4, "friction": "gravel", "contact": "rigid"},
    "sky": {"preset": "clear_noon"},
    "lighting": {"preset": "afternoon"},
    "ground": {
        "type": "heightfield", "size": [12, 12], "material": "grass", "friction": "gravel",
        "condim": 4, "height_scale": 0.35, "base_depth": 0.6,
        "terrain": {"kind": "hills", "seed": 42, "frequency": 4.0, "octaves": 5,
                    "resolution": 192, "flat_radius": 1.5},
    },
    "assemblies": [
        {"type": "obstacle_course", "name": "course", "pos": [2.5, -6.0, 0],
         "size": [14, 2.4], "material": "concrete", "friction": "concrete", "seed": 5},
        {"type": "scatter", "name": "rocks", "region": [-6, -6, 6, 6], "count": 18,
         "seed": 3, "z": 0.45, "shapes": ["box", "ellipsoid"],
         "materials": ["concrete", "steel_dark"], "friction": "gravel",
         "size_range": [0.08, 0.08, 0.06, 0.22, 0.22, 0.16], "mass_range": [2, 14]},
    ],
    "cameras": [
        {"name": "cam_chase", "pos": [-3, -3, 1.6], "target": [0, 0, 0.5], "fovy": 60},
    ],
    "viewer": {"camera_pos": [9, -9, 6], "camera_target": [0, 0, 0.3], "realtime": 1.0},
}

# --------------------------------------------------------------------------- #
TEMPLATES["manipulation_table"] = {
    **_base("manipulation_table", "Tabletop manipulation",
            "Studio-lit tabletop grasping scene with small objects of varied friction and a target bin."),
    "tags": ["tabletop", "manipulation", "grasping"],
    "physics": {"timestep": 0.001, "integrator": "implicitfast", "cone": "elliptic",
                "impratio": 50, "iterations": 150, "noslip_iterations": 10},
    "sky": {"preset": "studio", "fog": False},
    "lighting": {"preset": "studio_3point", "shadow_quality": "ultra"},
    "ground": {"type": "plane", "size": [6, 6], "material": "checker_light",
               "friction": "polished_floor"},
    "defaults": {"condim": 6, "friction": "rubber", "contact": "soft", "density": 600},
    "materials": [
        {"name": "target_red", "base": "plastic_red", "roughness": 0.35},
        {"name": "soft_pad", "base": "foam", "rgba": [0.85, 0.82, 0.7, 1]},
    ],
    "friction_profiles": [
        {"name": "silicone_pad", "sliding": 1.6, "torsional": 0.12, "rolling": 0.02,
         "condim": 6, "note": "Silicone gripper pad"},
    ],
    "assemblies": [
        {"type": "table", "name": "bench", "pos": [0, 0, 0], "size": [1.4, 0.9, 0.75],
         "material": "steel_dark", "material_2": "wood", "friction": "wood"},
        {"type": "bin", "name": "output_bin", "pos": [0.45, -0.25, 0.75],
         "size": [0.35, 0.25, 0.12], "material": "plastic_blue"},
        {"type": "target_pad", "name": "goal", "pos": [-0.45, 0.2, 0.75], "size": [0.09]},
    ],
    "objects": [
        {"name": "cube_a", "shape": "box", "size": [0.03, 0.03, 0.03], "pos": [-0.2, 0.1, 0.83],
         "material": "target_red", "friction": "silicone_pad", "mass": 0.12, "condim": 6},
        {"name": "cube_b", "shape": "box", "size": [0.035, 0.035, 0.035], "pos": [-0.1, -0.05, 0.83],
         "euler": [0, 0, 25], "material": "plastic_blue", "friction": "plastic", "mass": 0.15},
        {"name": "ball", "shape": "sphere", "size": [0.033], "pos": [0.05, 0.12, 0.84],
         "material": "rubber", "friction": "grippy_rubber", "mass": 0.1, "condim": 6},
        {"name": "can", "shape": "cylinder", "size": [0.033, 0.06], "pos": [0.15, -0.1, 0.86],
         "material": "aluminium", "friction": "greased_metal", "mass": 0.35, "condim": 4},
        {"name": "pad", "shape": "box", "size": [0.08, 0.06, 0.012], "pos": [-0.35, -0.15, 0.77],
         "material": "soft_pad", "contact": "squishy", "mass": 0.05},
        {"name": "peg", "shape": "capsule", "size": [0.012, 0.05], "pos": [0.28, 0.18, 0.84],
         "euler": [90, 0, 0], "material": "wood", "friction": "wood", "mass": 0.04},
    ],
    "cameras": [
        {"name": "cam_wrist", "pos": [0, -0.55, 1.35], "target": [0, 0, 0.78], "fovy": 45},
        {"name": "cam_side", "pos": [0.9, -0.5, 1.0], "target": [0, 0, 0.8], "fovy": 40},
    ],
    "viewer": {"camera_pos": [1.1, -1.2, 1.35], "camera_target": [0, 0, 0.8],
               "show_contacts": True, "exposure": 1.1},
}

# --------------------------------------------------------------------------- #
TEMPLATES["night_street"] = {
    **_base("night_street", "Night street",
            "Outdoor night scene with streetlights, asphalt, guardrails, and obstacles for perception and navigation tests."),
    "tags": ["outdoor", "night", "navigation"],
    "sky": {"preset": "night"},
    "lighting": {
        "preset": "night_moon",
        "extra_lights": [
            {"name": "lamp_1", "type": "spot", "pos": [-4, 2, 4], "target": [-4, 0, 0],
             "cutoff": 50, "exponent": 6, "diffuse": [0.9, 0.75, 0.45], "castshadow": True},
            {"name": "lamp_2", "type": "spot", "pos": [4, -2, 4], "target": [4, 0, 0],
             "cutoff": 50, "exponent": 6, "diffuse": [0.9, 0.75, 0.45], "castshadow": False},
        ],
    },
    "ground": {"type": "plane", "size": [25, 25], "material": "asphalt", "friction": "asphalt",
               "condim": 4},
    "assemblies": [
        {"type": "fence", "name": "rail_n", "pos": [0, 4, 0], "size": [16], "height": 1.0},
        {"type": "fence", "name": "rail_s", "pos": [0, -4, 0], "size": [16], "height": 1.0},
        {"type": "pillars", "name": "cones", "pos": [0, 0, 0], "count": 6, "size": [0.15],
         "height": 0.6, "spacing": [2.5, 2.0], "material": "safety_orange", "seed": 2},
        {"type": "platform", "name": "kerb", "pos": [-8, 0, 0], "size": [2.0, 8.0, 0.12],
         "material": "concrete"},
    ],
    "objects": [
        {"name": "barrel", "shape": "cylinder", "size": [0.28, 0.45], "pos": [2.0, 1.2, 0.45],
         "material": "safety_orange", "friction": "plastic", "mass": 8,
         "repeat": {"count": [3, 1, 1], "spacing": [1.2, 0, 0]}},
    ],
    "cameras": [{"name": "cam_front", "pos": [-9, 0, 1.2], "target": [4, 0, 0.8], "fovy": 60}],
    "viewer": {"camera_pos": [-10, -8, 5], "camera_target": [0, 0, 0.5], "exposure": 1.3},
}


def get(name: str) -> dict:
    if name not in TEMPLATES:
        raise KeyError(f"unknown template {name!r}; available: {sorted(TEMPLATES)}")
    import copy
    return copy.deepcopy(TEMPLATES[name])
