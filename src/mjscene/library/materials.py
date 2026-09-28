"""Material presets (data only).

`texture` uses MuJoCo builtin procedural textures so that a scene needs zero
external asset files.
"""

from __future__ import annotations

__all__ = ["MATERIALS"]


# --------------------------------------------------------------------------
# Materials. `texture` uses MuJoCo builtin procedural textures so that a
# scene needs zero external asset files.
# --------------------------------------------------------------------------
MATERIALS: dict[str, dict] = {
    "grid": {"rgba": [1, 1, 1, 1], "reflectance": 0.12, "shininess": 0.2, "specular": 0.3,
             "texrepeat": [12, 12], "texuniform": True,
             "texture": {"builtin": "checker", "mark": "edge", "rgb1": [0.22, 0.24, 0.27],
                         "rgb2": [0.29, 0.31, 0.35], "markrgb": [0.8, 0.8, 0.8],
                         "width": 512, "height": 512}},
    "checker_light": {"rgba": [1, 1, 1, 1], "reflectance": 0.1, "shininess": 0.2, "specular": 0.3,
                      "texrepeat": [8, 8], "texuniform": True,
                      "texture": {"builtin": "checker", "rgb1": [0.8, 0.8, 0.82],
                                  "rgb2": [0.6, 0.62, 0.66], "width": 512, "height": 512}},
    "concrete": {"rgba": [0.62, 0.62, 0.6, 1], "reflectance": 0.05, "shininess": 0.1, "specular": 0.2,
                 "texrepeat": [6, 6], "texuniform": True,
                 "texture": {"builtin": "checker", "rgb1": [0.58, 0.58, 0.56],
                             "rgb2": [0.64, 0.64, 0.62], "width": 512, "height": 512}},
    "asphalt": {"rgba": [0.25, 0.25, 0.27, 1], "reflectance": 0.04, "shininess": 0.1, "specular": 0.15},
    "wood": {"rgba": [0.72, 0.52, 0.3, 1], "reflectance": 0.06, "shininess": 0.25, "specular": 0.25},
    "wood_dark": {"rgba": [0.42, 0.28, 0.16, 1], "reflectance": 0.06, "shininess": 0.3, "specular": 0.3},
    "cardboard": {"rgba": [0.76, 0.63, 0.44, 1], "reflectance": 0.0, "shininess": 0.05, "specular": 0.1},
    "metal": {"rgba": [0.7, 0.73, 0.78, 1], "reflectance": 0.35, "shininess": 0.85, "specular": 0.8,
              "metallic": 0.9, "roughness": 0.25},
    "steel_dark": {"rgba": [0.38, 0.4, 0.44, 1], "reflectance": 0.25, "shininess": 0.7, "specular": 0.6,
                   "metallic": 0.85, "roughness": 0.4},
    "aluminium": {"rgba": [0.82, 0.84, 0.87, 1], "reflectance": 0.45, "shininess": 0.9, "specular": 0.9,
                  "metallic": 1.0, "roughness": 0.18},
    "rubber": {"rgba": [0.14, 0.15, 0.17, 1], "reflectance": 0.0, "shininess": 0.05, "specular": 0.1,
               "roughness": 0.95},
    "foam": {"rgba": [0.9, 0.86, 0.72, 1], "reflectance": 0.0, "shininess": 0.02, "specular": 0.05},
    "glass": {"rgba": [0.55, 0.78, 0.85, 0.45], "reflectance": 0.3, "shininess": 0.9, "specular": 0.9,
              "roughness": 0.05},
    "plastic_red": {"rgba": [0.85, 0.22, 0.2, 1], "shininess": 0.5, "specular": 0.45, "roughness": 0.4},
    "plastic_green": {"rgba": [0.25, 0.7, 0.35, 1], "shininess": 0.5, "specular": 0.45, "roughness": 0.4},
    "plastic_blue": {"rgba": [0.2, 0.42, 0.85, 1], "shininess": 0.5, "specular": 0.45, "roughness": 0.4},
    "plastic_yellow": {"rgba": [0.95, 0.78, 0.15, 1], "shininess": 0.5, "specular": 0.45, "roughness": 0.4},
    "plastic_white": {"rgba": [0.92, 0.92, 0.9, 1], "shininess": 0.5, "specular": 0.4, "roughness": 0.35},
    "safety_orange": {"rgba": [0.95, 0.45, 0.05, 1], "shininess": 0.35, "specular": 0.3},
    "wall_paint": {"rgba": [0.86, 0.85, 0.82, 1], "reflectance": 0.02, "shininess": 0.1, "specular": 0.1},
    "brick": {"rgba": [0.62, 0.32, 0.26, 1], "reflectance": 0.0, "shininess": 0.05, "specular": 0.1,
              "texrepeat": [4, 4], "texuniform": True,
              "texture": {"builtin": "checker", "rgb1": [0.58, 0.29, 0.24],
                          "rgb2": [0.66, 0.36, 0.3], "width": 256, "height": 256}},
    "grass": {"rgba": [0.32, 0.5, 0.26, 1], "reflectance": 0.0, "shininess": 0.05, "specular": 0.1,
              "texrepeat": [20, 20], "texuniform": True,
              "texture": {"builtin": "checker", "rgb1": [0.28, 0.45, 0.22],
                          "rgb2": [0.34, 0.53, 0.28], "width": 256, "height": 256}},
    "sand": {"rgba": [0.83, 0.74, 0.55, 1], "reflectance": 0.0, "shininess": 0.05, "specular": 0.1},
    "mars_soil": {"rgba": [0.65, 0.35, 0.22, 1], "reflectance": 0.0, "shininess": 0.05, "specular": 0.1},
    "snow": {"rgba": [0.95, 0.96, 0.98, 1], "reflectance": 0.2, "shininess": 0.2, "specular": 0.3},
    "target_marker": {"rgba": [0.1, 0.85, 0.5, 0.6], "emission": 0.35, "shininess": 0.1, "specular": 0.1},
}
