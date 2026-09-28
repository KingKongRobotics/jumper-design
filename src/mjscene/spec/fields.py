"""Field table: the single source of truth for the scene spec.

One table drives three outputs so they stay in sync:

  * `mjscene.spec.validate(spec)` —— errors for authors and LLMs, including spelling suggestions
  * `mjscene.spec.json_schema()`  —— schemas/scene.schema.json
  * `mjscene list fields`         —— field documentation printed for authors

Field kinds (`F.kind`)::

    number integer string bool any        scalar
    vec2 vec3 vec4 vec5 vec6              fixed-length array
    numlist strlist                       variable-length array
    enum                                  value must be in `enum`
    node / nodelist                       nested object or object array (specified by `node`)
    ref                                   preset name or name defined in this spec (category set by `ref`)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .. import library

__all__ = ["F", "NODES", "VEC_LEN"]


@dataclass
class F:
    kind: str
    default: Any = None
    doc: str = ""
    required: bool = False
    enum: list[Any] | None = None
    node: str | None = None
    ref: str | None = None          # "material" | "friction" | "mesh" | "object"
    min: float | None = None
    max: float | None = None


VEC_LEN = {"vec2": 2, "vec3": 3, "vec4": 4, "vec5": 5, "vec6": 6}
# --------------------------------------------------------------------------- #
# Node tables
# --------------------------------------------------------------------------- #

NODES: dict[str, dict[str, F]] = {}

NODES["SCENE"] = {
    "name": F("string", required=True, doc="Identifier used for the output directory ([a-z0-9_-])"),
    "title": F("string", doc="Human-readable title shown in the web scene picker"),
    "description": F("string", doc="Scene purpose, also supplied to AI tools"),
    "tags": F("strlist", doc="Free-form tags, such as ['mobile-robot','indoor']"),
    "physics": F("node", node="PHYSICS", doc="Solver and integrator settings"),
    "sky": F("node", node="SKY", doc="Skybox and fog"),
    "lighting": F("node", node="LIGHTING", doc="Lighting"),
    "ground": F("node", node="GROUND", doc="Ground plane or height-field terrain"),
    "materials": F("nodelist", node="MATERIAL", doc="Custom materials outside the preset library"),
    "meshes": F("nodelist", node="MESH", doc="External mesh assets (OBJ/STL)"),
    "friction_profiles": F("nodelist", node="FRICTION_PROFILE", doc="Custom friction models"),
    "defaults": F("node", node="DEFAULTS", doc="Default contact parameters for all geoms"),
    "objects": F("nodelist", node="OBJECT", doc="3D objects, static or dynamic"),
    "assemblies": F("nodelist", node="ASSEMBLY", doc="Prefabricated assemblies: rooms, tables, stairs, scattered objects, and more"),
    "robots": F("nodelist", node="ROBOT", doc="Import external robot MJCF"),
    "contacts": F("node", node="CONTACTS", doc="Explicit collision pairs and exclusions for precise contact control"),
    "cameras": F("nodelist", node="CAMERA", doc="Fixed or tracking cameras"),
    "spawn": F("node", node="SPAWN",
               doc="Robot spawn and activity bounds; this framework compiles a site and leaves interpretation to export targets"),
    "viewer": F("node", node="VIEWER", doc="Web viewer hints that do not affect physics"),
    "raw_mjcf": F("string", doc="Escape hatch: MJCF fragment inserted verbatim inside <mujoco>"),
}

NODES["PHYSICS"] = {
    "timestep": F("number", 0.002, "Integration timestep (s); <= 0.002 is recommended for rigid contact", min=1e-5, max=0.05),
    "gravity": F("vec3", [0.0, 0.0, -9.81], "Gravity (m/s^2)"),
    "integrator": F("enum", "implicitfast", "Integrator", enum=["Euler", "RK4", "implicit", "implicitfast"]),
    "solver": F("enum", "Newton", "Constraint solver", enum=["PGS", "CG", "Newton"]),
    "iterations": F("integer", 100, "Main solver iterations", min=1, max=1000),
    "ls_iterations": F("integer", 50, "Line-search iterations", min=1, max=200),
    "cone": F("enum", "pyramidal", "Friction cone; elliptic is more accurate but slower", enum=["pyramidal", "elliptic"]),
    "jacobian": F("enum", "auto", "Jacobian sparsity", enum=["dense", "sparse", "auto"]),
    "impratio": F("number", 1.0, "Normal-to-tangential impedance ratio; use 10-100 for slipping", min=0.01, max=1000),
    "wind": F("vec3", [0.0, 0.0, 0.0], "Wind speed (m/s); requires density or viscosity"),
    "density": F("number", 0.0, "Fluid density (kg/m^3); air=1.2, water=1000"),
    "viscosity": F("number", 0.0, "Fluid viscosity; air=2e-5"),
    "noslip_iterations": F("integer", 0, "Additional no-slip iterations (5-20 for grasping tasks)", min=0, max=100),
}

NODES["SKY"] = {
    "preset": F("enum", "day", "Sky preset", enum=sorted(library.SKY)),
    "top": F("vec3", None, "Override zenith color, 0-1"),
    "bottom": F("vec3", None, "Override horizon color, 0-1"),
    "haze": F("vec3", None, "Override fog or haze color"),
    "fog": F("bool", True, "Enable fog"),
    "fog_range": F("vec2", None, "Override fog start and end distances (m)"),
}

NODES["LIGHT"] = {
    "name": F("string", doc="Name (generated when omitted)"),
    "type": F("enum", "directional", "Light type", enum=["directional", "spot", "point"]),
    "pos": F("vec3", [0.0, 0.0, 3.0], "Position (m); directional lights use only direction"),
    "dir": F("vec3", None, "Light direction (alternative to target)"),
    "target": F("vec3", None, "Light target point; dir is computed automatically"),
    "diffuse": F("vec3", [0.6, 0.6, 0.6], "Diffuse intensity and color"),
    "specular": F("vec3", [0.2, 0.2, 0.2], "Specular highlight intensity"),
    "ambient": F("vec3", [0.0, 0.0, 0.0], "Ambient contribution of this light"),
    "castshadow": F("bool", True, "Cast shadows (at most two shadow lights recommended)"),
    "cutoff": F("number", 45.0, "Spotlight cone half-angle (deg)", min=1, max=90),
    "exponent": F("number", 10.0, "Spotlight falloff exponent", min=0, max=128),
    "attenuation": F("vec3", None, "Point or spot attenuation [constant, linear, quadratic]"),
    "active": F("bool", True, "Initially active"),
}

NODES["LIGHTING"] = {
    "preset": F("enum", "noon", "Lighting preset used when lights is empty", enum=sorted(library.LIGHTING)),
    "ambient": F("vec3", None, "Override global ambient light"),
    "headlight": F("bool", False, "Enable camera-following headlight"),
    "shadows": F("bool", True, "Global shadow switch"),
    "shadow_quality": F("enum", "high", "Shadow-map resolution. The web limit is 4096, so ultra only benefits"
                                        "the native MuJoCo viewer",
                        enum=["low", "medium", "high", "ultra"]),
    "lights": F("nodelist", node="LIGHT", doc="Explicit lights; overrides preset when supplied"),
    "extra_lights": F("nodelist", node="LIGHT", doc="Additional lights layered over the preset"),
}

NODES["TERRAIN"] = {
    "kind": F("enum", "hills", "Terrain generator", enum=library.TERRAIN_KINDS),
    "seed": F("integer", 0, "Random seed for reproducible results"),
    "amplitude": F("number", 0.3, "Maximum height variation (m); ground.height_scale overrides it",
                   min=0.0, max=20.0),
    "frequency": F("number", 3.0, "Noise frequency; higher values produce finer detail", min=0.1, max=64.0),
    "octaves": F("integer", 4, "Fractal noise octaves", min=1, max=8),
    "resolution": F("integer", 128, "Height-field resolution (samples per side)", min=8, max=1024),
    "flat_radius": F("number", 0.0, "Flat radius around the center (m) for robot placement"),
    "slope": F("number", 0.0, "Noise added when kind=slope; height_scale/size determines the actual slope"),
    "step_height": F("number", 0.15, "Height per step when kind=steps (m)"),
    "step_count": F("integer", 6, "Number of steps when kind=steps"),
}

NODES["GROUND"] = {
    "type": F("enum", "plane", "Ground type", enum=["plane", "heightfield", "none"]),
    "size": F("vec2", [20.0, 20.0], "Half-size (m); a plane is infinite, so this only affects rendering extent"),
    "pos": F("vec3", [0.0, 0.0, 0.0], "Ground origin"),
    "material": F("ref", "grid", "Material name, preset or custom", ref="material"),
    "friction": F("ref", "concrete", "Friction model name or [sliding, torsional, rolling]", ref="friction"),
    "condim": F("integer", None, "Contact dimension 1/3/4/6 (defaults to the friction model suggestion)", enum=[1, 3, 4, 6]),
    "contact": F("ref", None, "Contact stiffness preset", ref="contact"),
    "grid_spacing": F("number", 1.0, "Third plane size component: rendered grid spacing"),
    "terrain": F("node", node="TERRAIN", doc="Terrain parameters when type=heightfield"),
    "elevation_file": F("string", doc="Use an existing grayscale PNG height map relative to the spec directory"),
    "height_scale": F("number", None, "Height-field z scale (m), equal to maximum elevation. "
                                      "Defaults to terrain.amplitude (or step_height times step_count for steps)"),
    "base_depth": F("number", 0.5, "Height-field base depth (m)"),
}

NODES["TEXTURE"] = {
    "builtin": F("enum", "checker", "Built-in MuJoCo procedural texture", enum=["checker", "gradient", "flat"]),
    "file": F("string", doc="Use an external image relative to the spec directory"),
    "generator": F("enum", None, "Use the framework's procedural texture generator for wood or fabric",
                   enum=sorted(library.TEXTURE_GENERATORS)),
    "params": F("any", None, "Parameters passed to generator; invalid names report the available options"),
    "rgb1": F("vec3", [0.3, 0.3, 0.3], "Primary color"),
    "rgb2": F("vec3", [0.4, 0.4, 0.4], "Secondary color"),
    "mark": F("enum", "none", "Mark pattern", enum=["none", "edge", "cross", "random"]),
    "markrgb": F("vec3", [0.8, 0.8, 0.8], "Mark color"),
    "width": F("integer", 256, "Texture width", min=2, max=4096),
    "height": F("integer", 256, "Texture height", min=2, max=4096),
    "random": F("number", 0.01, "Dot density when mark=random"),
}

NODES["MATERIAL"] = {
    "name": F("string", required=True, doc="Material name referenced by objects"),
    "base": F("ref", None, "Inherit a preset material and override selected properties", ref="material"),
    "rgba": F("vec4", [0.7, 0.7, 0.7, 1.0], "Color and opacity"),
    "reflectance": F("number", 0.0, "MuJoCo reflectance, 0-1", min=0, max=1),
    "shininess": F("number", 0.3, "Highlight sharpness, 0-1", min=0, max=1),
    "specular": F("number", 0.3, "Specular intensity, 0-1", min=0, max=1),
    "emission": F("number", 0.0, "Emission, 0-1", min=0, max=1),
    "metallic": F("number", None, "PBR metallic value, 0-1 (web rendering)", min=0, max=1),
    "roughness": F("number", None, "PBR roughness, 0-1 (web rendering)", min=0, max=1),
    "texture": F("node", node="TEXTURE", doc="Texture"),
    "texrepeat": F("vec2", [1.0, 1.0], "Texture repeat count"),
    "texuniform": F("bool", False, "Use world-size uniform texturing (true recommended for ground)"),
}

NODES["MESH"] = {
    "name": F("string", required=True, doc="Mesh name"),
    "file": F("string", doc="OBJ/STL path relative to the spec directory; alternative to generator"),
    "generator": F("enum", None, "Use the framework's procedural mesh generator for shapes such as rounded boxes",
                   enum=sorted(library.MESH_GENERATORS)),
    "params": F("any", None, "Parameters passed to generator; invalid names report the available options"),
    "scale": F("vec3", [1.0, 1.0, 1.0], "Scale"),
    "maxhullvert": F("integer", None, "Convex-hull vertex limit to reduce collision cost", min=4, max=1000),
    "convex": F("bool", True, "Use a convex hull for collisions (MuJoCo default)"),
}

NODES["FRICTION_PROFILE"] = {
    "name": F("string", required=True, doc="Friction model name"),
    "sliding": F("number", 1.0, "Sliding friction coefficient", min=0, max=10),
    "torsional": F("number", 0.005, "Torsional friction (requires condim>=4)", min=0, max=10),
    "rolling": F("number", 0.0001, "Rolling friction (requires condim>=6)", min=0, max=10),
    "condim": F("integer", 3, "Suggested contact dimension", enum=[1, 3, 4, 6]),
    "note": F("string", doc="Notes"),
}

NODES["DEFAULTS"] = {
    "condim": F("integer", 3, "Default contact dimension", enum=[1, 3, 4, 6]),
    "friction": F("ref", "concrete", "Default friction model", ref="friction"),
    "contact": F("ref", "default", "Default contact stiffness", ref="contact"),
    "margin": F("number", 0.0, "Contact detection margin (m)"),
    "gap": F("number", 0.0, "Force-free gap inside the contact margin (m). MuJoCo 3.x tests show no effect on resting height; "
                            "do not use it to cancel margin; set margin to 0 for ground contact"),
    "density": F("number", 1000.0, "Density when mass is unspecified (kg/m^3)"),
    "solmix": F("number", 1.0, "Solver mixing weight"),
}

NODES["JOINT"] = {
    "type": F("enum", "hinge", "Joint type", enum=["free", "hinge", "slide", "ball"]),
    "name": F("string", doc="Joint name"),
    "axis": F("vec3", [0.0, 0.0, 1.0], "Rotation or sliding axis"),
    "pos": F("vec3", [0.0, 0.0, 0.0], "Joint origin relative to body"),
    "range": F("vec2", None, "Motion range (deg or m)"),
    "damping": F("number", 0.0, "Damping"),
    "stiffness": F("number", 0.0, "Stiffness restoring toward springref"),
    "armature": F("number", 0.0, "Added armature inertia, which can improve stability"),
    "frictionloss": F("number", 0.0, "Joint dry friction"),
    "limited": F("bool", None, "Whether limited; inferred from range by default"),
}

NODES["OBJECT"] = {
    "name": F("string", doc="Object name (generated when omitted)"),
    "shape": F("enum", "box", "Geometry shape", enum=library.SHAPES),
    "size": F("numlist", None, "Sizes: box=[hx,hy,hz] sphere=[r] capsule/cylinder=[r,half-length] "
                               "ellipsoid=[rx,ry,rz]"),
    "pos": F("vec3", [0.0, 0.0, 0.0], "Position (m)"),
    "euler": F("vec3", None, "Euler angles (deg, XYZ)"),
    "quat": F("vec4", None, "Quaternion [w,x,y,z]"),
    "axisangle": F("vec4", None, "[ax,ay,az,angle(deg)]"),
    "fromto": F("vec6", None, "Endpoints for capsule/cylinder/box (alternative to pos+size)"),
    "kind": F("enum", "dynamic", "dynamic=free motion, static=fixed to world, articulated=jointed",
              enum=["dynamic", "static", "articulated"]),
    "mass": F("number", None, "Mass (kg), alternative to density", min=1e-6),
    "density": F("number", None, "Density (kg/m^3)", min=1e-6),
    "material": F("ref", None, "Material name", ref="material"),
    "rgba": F("vec4", None, "Direct color override of material color"),
    "mesh": F("ref", None, "Mesh name when shape=mesh", ref="mesh"),
    "friction": F("ref", None, "Friction model name or three values", ref="friction"),
    "condim": F("integer", None, "Contact dimension 1/3/4/6", enum=[1, 3, 4, 6]),
    "contact": F("ref", None, "Contact stiffness preset", ref="contact"),
    "solref": F("vec2", None, "Specify [time constant, damping ratio] directly"),
    "solimp": F("numlist", None, "Specify solimp directly"),
    "margin": F("number", None, "Contact margin (m)"),
    "priority": F("integer", None, "Contact parameter priority; higher wins"),
    "collision": F("bool", True, "false means visual only, with no collision"),
    "contype": F("integer", None, "Collision type bit mask"),
    "conaffinity": F("integer", None, "Collision affinity bit mask"),
    "group": F("integer", 0, "Visibility group 0-5, hideable in the viewer", min=0, max=5),
    "joint": F("node", node="JOINT", doc="Joint when kind=articulated"),
    "joints": F("nodelist", node="JOINT", doc="Multi-degree-of-freedom joint chain"),
    "children": F("nodelist", node="OBJECT", doc="Child objects forming a compound body or chain"),
    "repeat": F("node", node="REPEAT", doc="Array repetition"),
    "tags": F("strlist", doc="Tags for viewer or script filtering"),
}

NODES["REPEAT"] = {
    "count": F("numlist", [1, 1, 1], "Copy count on each axis [nx,ny,nz]"),
    "spacing": F("vec3", [1.0, 1.0, 1.0], "Spacing (m)"),
    "jitter": F("number", 0.0, "Random position jitter (m)"),
    "seed": F("integer", 0, "Jitter seed"),
}

NODES["ASSEMBLY"] = {
    "type": F("enum", None, "Assembly type", required=True, enum=library.ASSEMBLIES),
    "name": F("string", doc="Name prefix"),
    "pos": F("vec3", [0.0, 0.0, 0.0], "Placement position"),
    "euler": F("vec3", None, "Orientation (deg)"),
    "size": F("numlist", None, "Primary size, interpreted by type (see mjscene list assemblies)"),
    "material": F("ref", None, "Primary material", ref="material"),
    "material_2": F("ref", None, "Secondary material, such as tabletop or stair tread", ref="material"),
    "friction": F("ref", None, "Friction model", ref="friction"),
    "thickness": F("number", None, "Wall or board thickness (m)"),
    "height": F("number", None, "Height (m)"),
    "width": F("number", None, "Width (m)"),
    "levels": F("integer", None, "Number of shelf levels"),
    "steps": F("integer", None, "Number of stairs"),
    "rise": F("number", None, "Rise per step (m)"),
    "run": F("number", None, "Run per step (m)"),
    "angle": F("number", None, "Slope angle (deg)"),
    "count": F("integer", None, "Count of columns or scattered objects"),
    "region": F("numlist", None, "Scatter region [x_min,y_min,x_max,y_max]"),
    "shapes": F("strlist", None, "Candidate scattered-object shapes"),
    "size_range": F("numlist", None, "Scattered-object size range [min..., max...]"),
    "mass_range": F("vec2", None, "Scattered-object mass range (kg)"),
    "materials": F("strlist", None, "Candidate scattered-object materials"),
    "seed": F("integer", None, "Random seed"),
    "z": F("number", None, "Scatter height or elevation (m)"),
    "spacing": F("numlist", None, "Spacing"),
    "openings": F("strlist", None, "Room opening directions, such as ['north','east']"),
    "ceiling": F("bool", None, "Whether the room has a ceiling"),
    "dynamic": F("bool", None, "Whether the assembly can move (static by default)"),
    "condim": F("integer", None, "Contact dimension 1/3/4/6 (default 4 for scatter and grid_of_boxes)",
                enum=[1, 3, 4, 6]),
    "contact": F("ref", None, "Contact stiffness preset", ref="contact"),
    "group": F("integer", None, "Visibility group", min=0, max=5),
    "tags": F("strlist", doc="Tags"),
}

NODES["CONTACT_PAIR"] = {
    "geom1": F("string", required=True, doc="Geom name (usually '<object_name>_geom')"),
    "geom2": F("string", required=True, doc="Other geom name"),
    "friction": F("ref", None, "Friction for this contact pair (name or five values)", ref="friction"),
    "condim": F("integer", None, "Contact dimension", enum=[1, 3, 4, 6]),
    "solref": F("vec2", None, "[time constant, damping ratio]"),
    "solimp": F("numlist", None, "solimp"),
    "margin": F("number", None, "Contact margin (m)"),
    "gap": F("number", None, "Force-free gap (m); tests show no effect on resting height; see DEFAULTS.gap"),
}

NODES["CONTACT_EXCLUDE"] = {
    "body1": F("string", required=True, doc="Body name 1"),
    "body2": F("string", required=True, doc="Body name 2"),
}

NODES["CONTACTS"] = {
    "pairs": F("nodelist", node="CONTACT_PAIR", doc="Explicit contact pairs; their parameters override geom settings"),
    "excludes": F("nodelist", node="CONTACT_EXCLUDE", doc="Disable contact between these two bodies"),
}

NODES["ROBOT"] = {
    "name": F("string", doc="Name prefix"),
    "file": F("string", required=True, doc="Robot MJCF path relative to the spec directory"),
    "pos": F("vec3", [0.0, 0.0, 0.0], "Placement position"),
    "euler": F("vec3", None, "Orientation (deg)"),
    "quat": F("vec4", None, "Orientation quaternion"),
    "freejoint": F("bool", False, "Add freejoint to root for a mobile robot"),
}

NODES["CAMERA"] = {
    "name": F("string", required=True, doc="Camera name"),
    "pos": F("vec3", required=True, doc="Position (m)"),
    "target": F("vec3", None, "Look-at target; orientation computed automatically"),
    "euler": F("vec3", None, "Specify Euler angles directly (deg)"),
    "fovy": F("number", 50.0, "Vertical field of view (deg)", min=1, max=170),
    "mode": F("enum", "fixed", "fixed / track / trackcom / targetbody",
              enum=["fixed", "track", "trackcom", "targetbody"]),
    "track": F("ref", None, "Tracked object name", ref="object"),
}

NODES["SPAWN"] = {
    "position": F("vec3", [0.0, 0.0, 0.0],
                  "Robot spawn point; z is the **ground height**. Only the host knows the robot's base height"
                  " and must add it for the selected robot"),
    "yaw": F("number", 0.0, "Initial orientation (deg); 0 faces +X"),
    "clearance": F("number", 0.4, "Required clear radius around spawn (m), for downstream checks", min=0.0),
    "bounds": F("vec6", None,
                "Activity bounds [x_min,y_min,z_min,x_max,y_max,z_max]; "
                "downstream consumers may build invisible walls or choose their own defaults"),
}

NODES["VIEWER"] = {
    "camera_pos": F("vec3", None, "Initial free-camera position"),
    "camera_target": F("vec3", None, "Initial view target"),
    "fovy": F("number", 50.0, "Field of view"),
    "realtime": F("number", 1.0, "Initial playback speed multiplier", min=0.05, max=8.0),
    "paused": F("bool", False, "Pause after loading"),
    "show_contacts": F("bool", False, "Show contact points"),
    "shadows": F("bool", None, "Override shadow switch"),
    "exposure": F("number", 1.05, "Exposure", min=0.1, max=4.0),
}
