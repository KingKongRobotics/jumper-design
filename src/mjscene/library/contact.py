"""Friction models and contact stiffness presets (data only).

Friction values follow MuJoCo's ``friction="sliding torsional rolling"`` triple.
Sliding numbers are ordinary dry-contact coefficients; torsional/rolling are
MuJoCo-specific and only take effect when condim >= 4 / 6.
"""

from __future__ import annotations

__all__ = ["FRICTION", "CONTACT_PROFILES", "friction_triple"]


# --------------------------------------------------------------------------
# Friction profiles: name -> sliding, torsional, rolling, and the minimum
# condim that makes the profile meaningful.
# --------------------------------------------------------------------------
FRICTION: dict[str, dict] = {
    "frictionless": {"sliding": 0.0, "torsional": 0.0, "rolling": 0.0, "condim": 1,
                     "note": "air-hockey puck / idealised slider"},
    "ice": {"sliding": 0.03, "torsional": 0.001, "rolling": 0.0, "condim": 3,
            "note": "ice on steel"},
    "greased_metal": {"sliding": 0.08, "torsional": 0.002, "rolling": 0.0001, "condim": 3},
    "polished_floor": {"sliding": 0.2, "torsional": 0.004, "rolling": 0.0001, "condim": 3,
                       "note": "waxed hall floor, wheels slip easily"},
    "glass": {"sliding": 0.35, "torsional": 0.005, "rolling": 0.0001, "condim": 3},
    "wood": {"sliding": 0.5, "torsional": 0.01, "rolling": 0.0005, "condim": 3},
    "steel_on_steel": {"sliding": 0.6, "torsional": 0.01, "rolling": 0.0002, "condim": 3},
    "cardboard": {"sliding": 0.7, "torsional": 0.02, "rolling": 0.001, "condim": 4},
    "plastic": {"sliding": 0.75, "torsional": 0.015, "rolling": 0.0005, "condim": 3},
    "concrete": {"sliding": 1.0, "torsional": 0.02, "rolling": 0.001, "condim": 3,
                 "note": "default indoor/outdoor hard ground"},
    "asphalt": {"sliding": 1.1, "torsional": 0.03, "rolling": 0.002, "condim": 4},
    "carpet": {"sliding": 1.1, "torsional": 0.05, "rolling": 0.01, "condim": 4,
               "note": "high rolling resistance, wheels sink"},
    "rubber": {"sliding": 1.3, "torsional": 0.05, "rolling": 0.005, "condim": 4,
               "note": "tyres, grippers, feet"},
    "grippy_rubber": {"sliding": 1.8, "torsional": 0.1, "rolling": 0.01, "condim": 6,
                      "note": "silicone gripper pads; needs condim 6 to resist twisting"},
    "grass": {"sliding": 0.9, "torsional": 0.06, "rolling": 0.02, "condim": 4},
    "sand": {"sliding": 0.8, "torsional": 0.1, "rolling": 0.05, "condim": 4,
             "note": "approximates granular drag, not a real granular model"},
    "gravel": {"sliding": 1.0, "torsional": 0.08, "rolling": 0.03, "condim": 4},
}

# --------------------------------------------------------------------------
# Contact softness profiles -> solref (time-const, damping-ratio) + solimp.
# --------------------------------------------------------------------------
CONTACT_PROFILES: dict[str, dict] = {
    "rigid": {"solref": [0.005, 1.0], "solimp": [0.95, 0.99, 0.0005, 0.5, 2.0],
              "note": "very stiff; requires timestep <= 0.002"},
    "default": {"solref": [0.02, 1.0], "solimp": [0.9, 0.95, 0.001, 0.5, 2.0]},
    "soft": {"solref": [0.04, 1.0], "solimp": [0.8, 0.9, 0.005, 0.5, 2.0],
             "note": "forgiving, good for contact-rich manipulation"},
    "squishy": {"solref": [0.08, 0.8], "solimp": [0.6, 0.85, 0.02, 0.5, 2.0],
                "note": "foam / soft padding feel"},
    "bouncy": {"solref": [0.015, 0.2], "solimp": [0.9, 0.95, 0.001, 0.5, 2.0],
               "note": "low damping ratio -> restitution"},
}


def friction_triple(name_or_list) -> list[float]:
    """Resolve a friction profile name (or explicit triple) to [s, t, r]."""
    if isinstance(name_or_list, (list, tuple)):
        vals = [float(v) for v in name_or_list]
        return (vals + [0.005, 0.0001])[:3]
    prof = FRICTION[name_or_list]
    return [prof["sliding"], prof["torsional"], prof["rolling"]]
