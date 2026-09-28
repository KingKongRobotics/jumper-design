"""Environment presets: skyboxes and lighting rigs (data only).

`SKY` entries carry the MJCF skybox gradient plus the haze/fog colour the web
viewer uses. `LIGHTING` entries are lists of light dicts in exactly the shape a
user may author by hand.
"""

from __future__ import annotations

__all__ = ["SKY", "LIGHTING"]


# --------------------------------------------------------------------------
# Sky presets -> MJCF skybox texture + haze/fog colour used by the web viewer.
# --------------------------------------------------------------------------
SKY: dict[str, dict] = {
    "day": {"top": [0.33, 0.52, 0.74], "bottom": [0.86, 0.9, 0.94], "haze": [0.72, 0.79, 0.86],
            "fog": [12, 55]},
    "clear_noon": {"top": [0.18, 0.42, 0.78], "bottom": [0.78, 0.88, 0.96], "haze": [0.7, 0.82, 0.92],
                   "fog": [20, 80]},
    "overcast": {"top": [0.62, 0.65, 0.68], "bottom": [0.82, 0.83, 0.85], "haze": [0.78, 0.8, 0.82],
                 "fog": [8, 35]},
    "dusk": {"top": [0.12, 0.14, 0.28], "bottom": [0.85, 0.52, 0.32], "haze": [0.55, 0.42, 0.4],
             "fog": [10, 45]},
    "night": {"top": [0.02, 0.03, 0.07], "bottom": [0.1, 0.12, 0.2], "haze": [0.08, 0.09, 0.14],
              "fog": [6, 30]},
    "indoor": {"top": [0.2, 0.2, 0.22], "bottom": [0.35, 0.35, 0.37], "haze": [0.3, 0.3, 0.32],
               "fog": [10, 40]},
    "studio": {"top": [0.55, 0.55, 0.58], "bottom": [0.88, 0.88, 0.9], "haze": [0.8, 0.8, 0.82],
               "fog": [20, 90]},
    "mars": {"top": [0.5, 0.33, 0.24], "bottom": [0.82, 0.6, 0.42], "haze": [0.72, 0.52, 0.38],
             "fog": [15, 70]},
    "space": {"top": [0.0, 0.0, 0.0], "bottom": [0.03, 0.03, 0.06], "haze": [0.0, 0.0, 0.0],
              "fog": [50, 400]},
}

# --------------------------------------------------------------------------
# Lighting rigs. `lights` entries are the same shape as user-authored lights.
# --------------------------------------------------------------------------
LIGHTING: dict[str, dict] = {
    "noon": {"ambient": [0.25, 0.25, 0.28], "lights": [
        {"name": "sun", "type": "directional", "pos": [2, -2, 8], "dir": [-0.2, 0.2, -1],
         "diffuse": [0.8, 0.78, 0.74], "specular": [0.3, 0.3, 0.3], "castshadow": True},
        {"name": "sky_fill", "type": "directional", "pos": [-4, 4, 6], "dir": [0.4, -0.4, -1],
         "diffuse": [0.18, 0.2, 0.26], "specular": [0.0, 0.0, 0.0], "castshadow": False},
    ]},
    "afternoon": {"ambient": [0.22, 0.22, 0.24], "lights": [
        {"name": "sun", "type": "directional", "pos": [6, -3, 4], "dir": [-0.8, 0.4, -0.7],
         "diffuse": [0.9, 0.82, 0.68], "specular": [0.35, 0.33, 0.3], "castshadow": True},
        {"name": "sky_fill", "type": "directional", "pos": [-5, 3, 5], "dir": [0.5, -0.3, -1],
         "diffuse": [0.15, 0.18, 0.24], "castshadow": False},
    ]},
    "sunset": {"ambient": [0.14, 0.12, 0.16], "lights": [
        {"name": "sun", "type": "directional", "pos": [9, 0, 1.5], "dir": [-1, 0, -0.2],
         "diffuse": [1.0, 0.6, 0.35], "specular": [0.4, 0.28, 0.2], "castshadow": True},
        {"name": "sky_fill", "type": "directional", "pos": [-6, 2, 6], "dir": [0.5, -0.2, -1],
         "diffuse": [0.12, 0.14, 0.24], "castshadow": False},
    ]},
    "night_moon": {"ambient": [0.05, 0.06, 0.1], "lights": [
        {"name": "moon", "type": "directional", "pos": [-4, -4, 7], "dir": [0.4, 0.4, -1],
         "diffuse": [0.2, 0.24, 0.35], "specular": [0.1, 0.1, 0.15], "castshadow": True},
    ]},
    "warehouse": {"ambient": [0.2, 0.2, 0.22], "lights": [
        {"name": "bay_1", "type": "spot", "pos": [-3, -3, 5], "dir": [0.2, 0.2, -1], "cutoff": 55,
         "exponent": 8, "diffuse": [0.55, 0.55, 0.5], "castshadow": True},
        {"name": "bay_2", "type": "spot", "pos": [3, 3, 5], "dir": [-0.2, -0.2, -1], "cutoff": 55,
         "exponent": 8, "diffuse": [0.55, 0.55, 0.5], "castshadow": True},
        {"name": "top_fill", "type": "directional", "pos": [0, 0, 6], "dir": [0, 0, -1],
         "diffuse": [0.25, 0.25, 0.28], "castshadow": False},
    ]},
    "indoor_office": {"ambient": [0.3, 0.3, 0.32], "lights": [
        {"name": "ceiling", "type": "directional", "pos": [0, 0, 3], "dir": [0, 0, -1],
         "diffuse": [0.55, 0.55, 0.52], "castshadow": True},
        {"name": "window", "type": "directional", "pos": [-4, 0, 2], "dir": [1, 0, -0.4],
         "diffuse": [0.3, 0.33, 0.4], "castshadow": False},
    ]},
    "studio_3point": {"ambient": [0.18, 0.18, 0.2], "lights": [
        {"name": "key", "type": "spot", "pos": [2.5, -2.5, 3], "dir": [-0.6, 0.6, -0.8], "cutoff": 50,
         "exponent": 10, "diffuse": [0.8, 0.8, 0.78], "specular": [0.4, 0.4, 0.4], "castshadow": True},
        {"name": "fill", "type": "spot", "pos": [-2.5, -1.5, 2.2], "dir": [0.7, 0.4, -0.6], "cutoff": 60,
         "exponent": 5, "diffuse": [0.3, 0.32, 0.38], "castshadow": False},
        {"name": "rim", "type": "spot", "pos": [0, 3, 2.5], "dir": [0, -1, -0.7], "cutoff": 45,
         "exponent": 12, "diffuse": [0.45, 0.45, 0.5], "castshadow": False},
    ]},
    "flat": {"ambient": [0.45, 0.45, 0.47], "lights": [
        {"name": "top", "type": "directional", "pos": [0, 0, 5], "dir": [0, 0, -1],
         "diffuse": [0.45, 0.45, 0.45], "castshadow": False},
    ]},
}

# Terrain generators available to `ground.terrain.kind`.
