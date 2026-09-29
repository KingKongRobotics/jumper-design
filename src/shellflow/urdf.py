"""Explicit, dependency-free MJCF subset to portable URDF conversion.

This exports kinematics, authored inertials and geometry. It is not a general
MuJoCo dynamics converter: actuator, solver and contact settings stay in MJCF.
Unsupported transforms fail rather than silently changing the robot.
"""
from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET


class UrdfConversionError(ValueError):
    """The MJCF contains a feature outside the verified conversion subset."""


def _numbers(value: str, count: int | None = None) -> list[float]:
    try:
        result = [float(v) for v in value.split()]
    except (ValueError, AttributeError) as exc:
        raise UrdfConversionError(f"Invalid numeric vector: {value!r}") from exc
    if (count is not None and len(result) != count) or not all(map(math.isfinite, result)):
        raise UrdfConversionError(f"Invalid finite vector of length {count}: {value!r}")
    return result


def _fmt(values) -> str:
    return " ".join(format(float(v), ".17g") for v in values)


def _multiply(a, b):
    w, x, y, z = a
    W, X, Y, Z = b
    return (w*W-x*X-y*Y-z*Z, w*X+x*W+y*Z-z*Y,
            w*Y-x*Z+y*W+z*X, w*Z+x*Y-y*X+z*W)


def _rpy(attributes: dict, angle_scale: float, eulerseq: str) -> list[float]:
    unsupported = set(attributes) & {"axisangle", "xyaxes", "zaxis"}
    if unsupported:
        raise UrdfConversionError(f"Unsupported orientation: {sorted(unsupported)}")
    if "quat" in attributes and "euler" in attributes:
        raise UrdfConversionError("Ambiguous quat and euler orientation")
    q = _numbers(attributes.get("quat", "1 0 0 0"), 4)
    if "euler" in attributes:
        q = (1.0, 0.0, 0.0, 0.0)
        for axis, angle in zip(eulerseq, _numbers(attributes["euler"], 3)):
            half = angle * angle_scale / 2
            rotation = [math.cos(half), 0.0, 0.0, 0.0]
            rotation["xyz".index(axis.lower())+1] = math.sin(half)
            q = _multiply(q, rotation) if axis.islower() else _multiply(rotation, q)
    norm = math.sqrt(sum(v*v for v in q))
    if norm < 1e-15:
        raise UrdfConversionError("Zero quaternion")
    w, x, y, z = (v/norm for v in q)
    # URDF fixed-axis XYZ (Rz(yaw) Ry(pitch) Rx(roll)).
    m00, m10 = 1-2*(y*y+z*z), 2*(x*y+w*z)
    m20, m21, m22 = 2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)
    pitch = math.asin(max(-1.0, min(1.0, -m20)))
    if abs(math.cos(pitch)) > 1e-10:
        return [math.atan2(m21, m22), pitch, math.atan2(m10, m00)]
    # At gimbal lock use yaw=0 and a roll with the same rotation matrix.
    m01, m11 = 2*(x*y-w*z), 1-2*(x*x+z*z)
    return [math.atan2(m01 if pitch > 0 else -m01, m11), pitch, 0.0]


def _origin(parent, attributes, angle_scale, eulerseq):
    ET.SubElement(parent, "origin", xyz=_fmt(_numbers(attributes.get("pos", "0 0 0"), 3)),
                  rpy=_fmt(_rpy(attributes, angle_scale, eulerseq)))


def _relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value.replace("\\", "/"))
    if not value or path.is_absolute() or ".." in path.parts or ":" in value:
        raise UrdfConversionError(f"Mesh path must be relative without traversal: {value!r}")
    return path


def export_urdf(mjcf_path: Path, output_path: Path, *,
                default_velocity_limit: float = 100.0,
                default_effort_limit: float | None = None,
                joint_metadata: dict | None = None,
                joint_order: list[str] | None = None,
                source_revision_comment: str | None = None) -> dict:
    """Export the supported MJCF body tree, returning explicit conversion limits.

    Mesh files must already exist beside the MJCF in its relative meshdir. The
    caller packages these same files beside the returned URDF. Joint metadata
    preserves source URDF velocity limits; without it, velocity is an explicit
    configurable import ceiling (rad/s or m/s), not a measured motor limit.
    Missing effort is rejected unless the caller explicitly provides a default.
    """
    mjcf_path, output_path = Path(mjcf_path), Path(output_path)
    if output_path.exists():
        raise FileExistsError(output_path)
    if not math.isfinite(default_velocity_limit) or default_velocity_limit <= 0:
        raise UrdfConversionError("default_velocity_limit must be finite and positive")
    if default_effort_limit is not None and (
            not math.isfinite(default_effort_limit) or default_effort_limit <= 0):
        raise UrdfConversionError("default_effort_limit must be finite and positive")
    if joint_metadata is not None and not isinstance(joint_metadata, dict):
        raise UrdfConversionError("joint_metadata must map child links to source joint data")
    if source_revision_comment is not None:
        match = re.fullmatch(r"<!--([\s\S]*?)-->", source_revision_comment.strip())
        if match is None or "--" in match.group(1):
            raise UrdfConversionError("Invalid source revision XML comment")
    root = ET.parse(mjcf_path).getroot()
    if root.tag != "mujoco":
        raise UrdfConversionError("Input must be MJCF")
    if root.findall(".//include"):
        raise UrdfConversionError("Resolve MJCF includes before exporting")
    compiler = root.find("compiler")
    compiler = {} if compiler is None else compiler.attrib
    if compiler.get("coordinate", "local") != "local":
        raise UrdfConversionError("Only local coordinates are supported")
    if compiler.get("angle", "degree") not in {"radian", "degree"}:
        raise UrdfConversionError("Unknown angle unit")
    angle_scale = 1.0 if compiler.get("angle", "degree") == "radian" else math.pi/180
    eulerseq = compiler.get("eulerseq", "xyz")
    if len(eulerseq) != 3 or any(c not in "xyzXYZ" for c in eulerseq):
        raise UrdfConversionError("Invalid Euler sequence")
    meshdir = _relative(compiler.get("meshdir", "."))
    defaults: dict[str, dict[str, dict]] = {"": {}}

    def read_defaults(node, inherited):
        current = {tag: dict(attributes) for tag, attributes in inherited.items()}
        for child in node:
            if child.tag != "default":
                current.setdefault(child.tag, {}).update(child.attrib)
        name = node.get("class", "")
        if name in defaults and name:
            raise UrdfConversionError(f"Duplicate default class {name}")
        defaults[name] = current
        for child in node.findall("default"):
            read_defaults(child, current)

    for node in root.findall("default"):
        read_defaults(node, defaults[""])

    def resolved(element, inherited_class=""):
        selected = element.get("class", inherited_class)
        if selected not in defaults:
            raise UrdfConversionError(f"Unknown default class {selected}")
        return {**defaults[selected].get(element.tag, {}), **element.attrib}

    meshes = {}
    for mesh in root.findall("asset/mesh"):
        attrs = resolved(mesh)
        name = attrs.get("name")
        if not name or name in meshes:
            raise UrdfConversionError("Missing or duplicate mesh name")
        if set(attrs) & {"vertex", "face", "refpos", "refquat"}:
            raise UrdfConversionError("Inline or reference-transformed meshes must be baked first")
        if "file" not in attrs:
            raise UrdfConversionError("Mesh file is required")
        meshes[name] = (str(meshdir / _relative(attrs["file"])),
                        _numbers(attrs.get("scale", "1 1 1"), 3))
        if min(meshes[name][1]) <= 0:
            raise UrdfConversionError("Mesh scale must be positive; bake reflected meshes first")
    materials = {n.get("name"): n.attrib for n in root.findall("asset/material")}
    robot = ET.Element("robot", name=root.get("model", "shellflow_robot"))
    robot.append(ET.Comment("Kinematics and geometry export. Native MJCF retains actuator and contact semantics."))
    extension = ET.SubElement(robot, "mujoco")
    # Keep paths in each URDF mesh filename; adding meshdir again doubles paths.
    output_compiler = ET.SubElement(extension, "compiler", discardvisual="false", fusestatic="false", strippath="false")
    if "balanceinertia" in compiler:
        output_compiler.set("balanceinertia", compiler["balanceinertia"])
    warnings = [
        "URDF has no native MJCF actuator/controller, sensor/site, solver or contact-filter equivalence; use the companion MJCF for simulation behavior.",
        "Joint velocity limits below are configurable URDF import ceilings, not measured motor limits.",
        "Joint armature and MJCF contact friction/solref/solimp are not represented by this URDF.",
    ]
    if joint_metadata is not None:
        warnings[1] = "Joint names, effort and velocity limits are retained from the hash-bound source URDF metadata."
    if root.findall("asset/texture") or any("texture" in m for m in materials.values()):
        warnings.append("MJCF textures are omitted; only diffuse RGBA colors are exported.")
    if any(root.find(tag) is not None for tag in ("equality", "tendon", "contact")):
        raise UrdfConversionError("Explicit equality, tendon or contact constraints require a dedicated converter")
    worldbody = root.find("worldbody")
    if worldbody is None or len(worldbody.findall("body")) != 1:
        raise UrdfConversionError("Exactly one root body is required")
    if any(child.tag != "body" for child in worldbody):
        raise UrdfConversionError("World-level geometry/sites are not part of a robot URDF")
    body_names, joint_names = set(), set()
    material_names: dict[tuple, str] = {}
    assumptions, effort_sources, exported_joints = [], [], []
    counts = {"body_links": 0, "fixed_joints": 0, "movable_joints": 0,
              "floating_joints": 0, "visuals": 0, "collisions": 0}
    # MuJoCo recognizes this reserved URDF root as its world, making the free
    # joint top-level. A differently named dummy parent makes loading fail.
    world_name = "world"
    if root.find(".//body[@name='world']") is not None:
        raise UrdfConversionError("Source body name 'world' is reserved by the URDF importer")
    ET.SubElement(robot, "link", name=world_name)

    def inertial(link, node):
        if node is None:
            raise UrdfConversionError(f"Explicit inertial required for body {link.get('name')}")
        attrs = node.attrib
        mass = _numbers(attrs.get("mass", ""), 1)[0]
        if mass <= 0:
            raise UrdfConversionError("Body mass must be positive")
        output = ET.SubElement(link, "inertial")
        _origin(output, attrs, angle_scale, eulerseq)
        ET.SubElement(output, "mass", value=_fmt([mass]))
        if "diaginertia" in attrs and "fullinertia" not in attrs:
            xx, yy, zz = _numbers(attrs["diaginertia"], 3)
            roll, pitch, yaw = _rpy(attrs, angle_scale, eulerseq)
            cr, sr = math.cos(roll), math.sin(roll)
            cp, sp = math.cos(pitch), math.sin(pitch)
            cy, sy = math.cos(yaw), math.sin(yaw)
            rotation = [[cy*cp, cy*sp*sr-sy*cr, cy*sp*cr+sy*sr],
                        [sy*cp, sy*sp*sr+cy*cr, sy*sp*cr-cy*sr],
                        [-sp, cp*sr, cp*cr]]
            diagonal = [xx, yy, zz]
            tensor = [[sum(rotation[i][k]*diagonal[k]*rotation[j][k]
                           for k in range(3)) for j in range(3)] for i in range(3)]
            xx, yy, zz = (tensor[i][i] for i in range(3))
            xy, xz, yz = tensor[0][1], tensor[0][2], tensor[1][2]
            # MuJoCo 3.10's URDF importer drops inertial-origin rotation when
            # reconstructing principal inertia. Bake it into a link-aligned
            # symmetric tensor, valid in URDF and preserving MuJoCo dynamics.
            output.find("origin").set("rpy", "0 0 0")
        elif "fullinertia" in attrs and "diaginertia" not in attrs:
            if any(v in attrs for v in ("quat", "euler")):
                raise UrdfConversionError("fullinertia with orientation is ambiguous")
            xx, yy, zz, xy, xz, yz = _numbers(attrs["fullinertia"], 6)
        else:
            raise UrdfConversionError("Exactly one explicit inertia representation is required")
        if min(xx, yy, zz) <= 0:
            raise UrdfConversionError("Inertia diagonal must be positive")
        ET.SubElement(output, "inertia", **dict(zip(
            ("ixx", "iyy", "izz", "ixy", "ixz", "iyz"),
            (format(v, ".17g") for v in (xx, yy, zz, xy, xz, yz)))))

    def add_geom(link, node, inherited_class):
        attrs = resolved(node, inherited_class)
        if "fromto" in attrs:
            raise UrdfConversionError("Bake geom fromto into pos/quat before export")
        kind = attrs.get("type", "mesh" if "mesh" in attrs else "sphere")
        if kind not in {"mesh", "box", "sphere", "cylinder"}:
            raise UrdfConversionError(f"Unsupported geom type {kind}")
        if node.get("class") in {"visual", "structure"} or (
                attrs.get("contype", "1") == "0" and attrs.get("conaffinity", "1") == "0"):
            roles = ("visual",)
        elif node.get("class") == "collision":
            roles = ("collision",)
        else:
            roles = ("visual", "collision")
        for role in roles:
            geom_name = node.get("name", f"{link.get('name')}_{role}_{counts[role+'s']}")
            if len(roles) == 2:
                geom_name += f"_{role}"
            element = ET.SubElement(link, role, name=geom_name)
            _origin(element, attrs, angle_scale, eulerseq)
            geometry = ET.SubElement(element, "geometry")
            if kind == "mesh":
                if attrs.get("mesh") not in meshes:
                    raise UrdfConversionError(f"Unknown mesh {attrs.get('mesh')}")
                filename, scale = meshes[attrs["mesh"]]
                ET.SubElement(geometry, "mesh", filename=filename, scale=_fmt(scale))
            else:
                size = _numbers(attrs.get("size", ""))
                needed = {"box": 3, "sphere": 1, "cylinder": 2}[kind]
                if len(size) < needed or any(v <= 0 for v in size[:needed]):
                    raise UrdfConversionError(f"Invalid {kind} dimensions")
                if kind == "box":
                    ET.SubElement(geometry, "box", size=_fmt([2*v for v in size[:3]]))
                elif kind == "sphere":
                    ET.SubElement(geometry, "sphere", radius=_fmt(size[:1]))
                else:
                    ET.SubElement(geometry, "cylinder", radius=_fmt(size[:1]), length=_fmt([2*size[1]]))
            if role == "visual":
                material = materials.get(attrs.get("material"), {})
                rgba = tuple(_numbers(attrs.get("rgba", material.get("rgba", "0.5 0.5 0.5 1")), 4))
                if rgba not in material_names:
                    name = f"shellflow_material_{len(material_names):03d}"
                    material_names[rgba] = name
                    global_material = ET.SubElement(robot, "material", name=name)
                    ET.SubElement(global_material, "color", rgba=_fmt(rgba))
                ET.SubElement(element, "material", name=material_names[rgba])
            counts[role+"s"] += 1

    def add_body(body, parent_name, inherited_class=""):
        name = body.get("name")
        if not name or name in body_names or name == world_name:
            raise UrdfConversionError("Missing or duplicate body name")
        if any(child.tag not in {"body", "inertial", "joint", "freejoint", "geom", "site", "camera", "light"}
               for child in body):
            raise UrdfConversionError(f"Unsupported element in body {name}")
        body_names.add(name)
        counts["body_links"] += 1
        childclass = body.get("childclass", inherited_class)
        if childclass not in defaults:
            raise UrdfConversionError(f"Unknown childclass {childclass}")
        link = ET.SubElement(robot, "link", name=name)
        inertial(link, body.find("inertial"))
        for geom in body.findall("geom"):
            add_geom(link, geom, childclass)
        joints = body.findall("joint") + body.findall("freejoint")
        if len(joints) > 1:
            raise UrdfConversionError(f"Multiple joints in body {name} require virtual links")
        attrs = resolved(joints[0], childclass) if joints else {}
        kind = ("free" if joints[0].tag == "freejoint" else attrs.get("type", "hinge")) if joints else "fixed"
        metadata = joint_metadata.get(name) if joint_metadata is not None else None
        if joint_metadata is not None and parent_name != world_name and not isinstance(metadata, dict):
            raise UrdfConversionError(f"Missing source joint metadata for {name}")
        if kind not in {"fixed", "free", "hinge", "slide"}:
            raise UrdfConversionError(f"Unsupported joint type {kind}")
        if any(abs(v) > 1e-12 for v in _numbers(attrs.get("pos", "0 0 0"), 3)):
            raise UrdfConversionError(f"Nonzero joint pos in {name} requires frame conversion")
        if float(attrs.get("ref", "0")) != 0:
            raise UrdfConversionError("Nonzero joint ref is not supported")
        if float(attrs.get("stiffness", "0")) != 0:
            raise UrdfConversionError("Joint springs are not represented in URDF")
        joint_name = attrs.get("name", f"{name}_fixed_joint")
        if metadata is not None:
            source_name = metadata.get("name")
            if not isinstance(source_name, str) or not source_name or source_name.strip() != source_name:
                raise UrdfConversionError(f"Invalid source joint name for {name}")
            if kind != "fixed" and source_name != joint_name:
                raise UrdfConversionError(f"Source joint name differs from native joint: {name}")
            joint_name = source_name
        if joint_name in joint_names:
            raise UrdfConversionError(f"Duplicate joint name {joint_name}")
        joint_names.add(joint_name)
        if kind == "free" and parent_name != world_name:
            raise UrdfConversionError("Only the root may have a free joint")
        limited = attrs.get("limited", "auto") != "false" and "range" in attrs
        urdf_type = {"fixed": "fixed", "free": "floating", "slide": "prismatic",
                     "hinge": "revolute" if limited else "continuous"}[kind]
        if metadata is not None and metadata.get("type") != urdf_type:
            raise UrdfConversionError(f"Source joint type differs from native joint: {joint_name}")
        joint = ET.SubElement(robot, "joint", name=joint_name, type=urdf_type)
        ET.SubElement(joint, "parent", link=parent_name)
        ET.SubElement(joint, "child", link=name)
        _origin(joint, body.attrib, angle_scale, eulerseq)
        if kind in {"hinge", "slide"}:
            axis = _numbers(attrs.get("axis", "0 0 1"), 3)
            norm = math.sqrt(sum(v*v for v in axis))
            if norm < 1e-15:
                raise UrdfConversionError("Joint axis must be nonzero")
            ET.SubElement(joint, "axis", xyz=_fmt([v/norm for v in axis]))
            if "actuatorfrcrange" in attrs:
                effort = max(abs(v) for v in _numbers(attrs["actuatorfrcrange"], 2))
                effort_source = "joint.actuatorfrcrange"
            else:
                candidates = [a for a in root.findall("actuator/*") if a.get("joint") == joint_name]
                if len(candidates) == 1 and "forcerange" in candidates[0].attrib:
                    effort = max(abs(v) for v in _numbers(candidates[0].get("forcerange"), 2))
                    gear = _numbers(candidates[0].get("gear", "1"))
                    if len(gear) != 1:
                        raise UrdfConversionError("Unsupported actuator transmission gear")
                    effort *= abs(gear[0])
                    effort_source = "actuator.forcerange*gear"
                elif default_effort_limit is not None:
                    effort, effort_source = default_effort_limit, "caller_placeholder"
                else:
                    raise UrdfConversionError(f"No effort limit for {joint_name}; provide an explicit default")
            if effort <= 0:
                raise UrdfConversionError("Effort limit must be positive")
            velocity = default_velocity_limit
            if metadata is not None:
                velocity = _numbers(str(metadata.get("velocity", "")), 1)[0]
                source_effort = _numbers(str(metadata.get("effort", "")), 1)[0]
                if velocity <= 0 or not math.isclose(source_effort, effort, rel_tol=1e-12, abs_tol=1e-12):
                    raise UrdfConversionError(f"Source/native effort or velocity mismatch: {joint_name}")
                effort_source = "source_urdf_and_native_joint"
            limit = {"effort": _fmt([effort]), "velocity": _fmt([velocity])}
            if limited:
                bounds = _numbers(attrs["range"], 2)
                scale = angle_scale if kind == "hinge" else 1.0
                if bounds[0] >= bounds[1]:
                    raise UrdfConversionError("Joint range is reversed or empty")
                limit.update(lower=_fmt([bounds[0]*scale]), upper=_fmt([bounds[1]*scale]))
            elif kind == "slide":
                raise UrdfConversionError("Prismatic joint requires finite limits")
            ET.SubElement(joint, "limit", **limit)
            ET.SubElement(joint, "dynamics", damping=attrs.get("damping", "0"), friction=attrs.get("frictionloss", "0"))
            assumptions.append({"joint": joint_name, "velocity": velocity,
                                "unit": "rad/s" if kind == "hinge" else "m/s",
                                "basis": "source_urdf" if metadata is not None else "configurable_import_ceiling_not_measured"})
            effort_sources.append({"joint": joint_name, "effort": effort, "basis": effort_source})
            counts["movable_joints"] += 1
        else:
            counts["floating_joints" if kind == "free" else "fixed_joints"] += 1
        exported_joints.append({"name": joint_name, "parent": parent_name, "child": name, "type": urdf_type})
        for child in body.findall("body"):
            add_body(child, name, childclass)

    add_body(worldbody.find("body"), world_name)
    if joint_metadata is not None and set(joint_metadata) != body_names - {worldbody.find("body").get("name")}:
        raise UrdfConversionError("Source joint metadata differs from the robot tree")
    if joint_order is not None:
        source_joints = {j.get("name"): j for j in robot.findall("joint") if j.get("type") != "floating"}
        if len(joint_order) != len(set(joint_order)) or set(joint_order) != set(source_joints):
            raise UrdfConversionError("Source joint order differs from the exported robot")
        for joint in source_joints.values():
            robot.remove(joint)
        for name in joint_order:
            robot.append(source_joints[name])
    ET.indent(robot, space="  ")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(robot).write(output_path, encoding="utf-8", xml_declaration=True)
    if source_revision_comment is not None:
        serialized = output_path.read_bytes()
        declaration, body = serialized.split(b"\n", 1)
        output_path.write_bytes(declaration + b"\n" + source_revision_comment.strip().encode("utf-8") + b"\n" + body)
    return {"schema_version": 1, "source_sha256": hashlib.sha256(mjcf_path.read_bytes()).hexdigest(),
            "urdf_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
            "counts": counts, "world_link": world_name, "joints": exported_joints,
            "velocity_assumptions": assumptions, "effort_sources": effort_sources,
            "warnings": warnings, "actuators_in_source": len(root.findall("actuator/*")),
            "sites_in_source": len(root.findall(".//site")),
            "inertia_frame": "link_aligned_full_tensor_with_preserved_center_of_mass",
            "physics_equivalent": False, "physical_fit_tested": False}


def verify_urdf(mjcf_path: Path, urdf_path: Path, *, poses: int = 10) -> dict:
    """Compile both actual files and compare named-body kinematics and inertia.

    MuJoCo and NumPy are optional runtime dependencies, imported only here.
    Returns a machine-readable failure report instead of declaring conversion
    success from XML parsing alone. This does not certify contact or controls.
    """
    try:
        import mujoco
        import numpy as np
    except ImportError as exc:
        raise UrdfConversionError("Actual URDF verification requires MuJoCo and NumPy") from exc
    if not isinstance(poses, int) or poses < 1:
        raise UrdfConversionError("poses must be a positive integer")

    def load(path):
        path = Path(path).resolve()
        xml = path.read_text(encoding="utf-8-sig")
        root = ET.fromstring(xml)
        files = set()
        if root.tag == "mujoco":
            compiler = root.find("compiler")
            meshdir = "." if compiler is None else compiler.get("meshdir", ".")
            files.update(str(_relative(meshdir) / _relative(e.get("file")))
                         for e in root.findall("asset/mesh") if e.get("file"))
        elif root.tag == "robot":
            files.update(str(_relative(e.get("filename")))
                         for e in root.findall(".//geometry/mesh"))
        else:
            raise UrdfConversionError("Verification requires MJCF and URDF roots")
        assets = {}
        for filename in files:
            source = (path.parent / filename).resolve()
            if not source.is_relative_to(path.parent):
                raise UrdfConversionError("Mesh symlink leaves the exported package")
            assets[filename] = source.read_bytes()
        # Python's file reader handles non-ASCII Windows paths; the native
        # MuJoCo path loader does not on some versions. VFS also tests relpaths.
        return mujoco.MjModel.from_xml_string(xml, assets)

    a, b = load(mjcf_path), load(urdf_path)
    body_type, joint_type = mujoco.mjtObj.mjOBJ_BODY, mujoco.mjtObj.mjOBJ_JOINT

    def named(model, object_type, count):
        names = {mujoco.mj_id2name(model, object_type, i): i for i in range(count)}
        if None in names or len(names) != count:
            raise UrdfConversionError("Verification requires unique names")
        return names

    ba, bb = named(a, body_type, a.nbody), named(b, body_type, b.nbody)
    ja, jb = named(a, joint_type, a.njnt), named(b, joint_type, b.njnt)
    failures = []
    for kind, left, right in (("body", ba, bb), ("joint", ja, jb)):
        if left.keys() != right.keys():
            failures.append({"check": f"{kind}_names", "missing": sorted(left.keys()-right.keys()),
                             "extra": sorted(right.keys()-left.keys())})
    report = {"schema_version": 1, "mujoco_version": mujoco.__version__,
              "source_sha256": hashlib.sha256(Path(mjcf_path).read_bytes()).hexdigest(),
              "urdf_sha256": hashlib.sha256(Path(urdf_path).read_bytes()).hexdigest(),
              "source": {"bodies_with_world": a.nbody, "joints": a.njnt, "nq": a.nq, "nv": a.nv, "actuators": a.nu},
              "urdf": {"bodies_with_world": b.nbody, "joints": b.njnt, "nq": b.nq, "nv": b.nv, "actuators": b.nu},
              "fk_poses": poses, "failures": failures, "max_absolute_errors": {},
              "scope": "Named-body FK, mass, COM, inertial tensor and joint type/axis/ranges. Actuators, armature and contact behavior remain native-MJCF-only.",
              "physics_equivalent": False, "physical_fit_tested": False}
    if failures:
        report.update(passed=False, status="failed")
        return report
    body_order = sorted(ba)
    joint_order = sorted(ja)
    ia, ib = [ba[n] for n in body_order], [bb[n] for n in body_order]
    ka, kb = [ja[n] for n in joint_order], [jb[n] for n in joint_order]
    errors = report["max_absolute_errors"]
    for name in body_order:
        pa = mujoco.mj_id2name(a, body_type, int(a.body_parentid[ba[name]]))
        pb = mujoco.mj_id2name(b, body_type, int(b.body_parentid[bb[name]]))
        if pa != pb:
            failures.append({"check": "body_parent", "body": name, "source_parent": pa, "urdf_parent": pb})

    def compare(label, left, right, atol, rtol=0.0):
        left, right = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
        maximum = float(np.max(np.abs(left-right))) if left.size else 0.0
        errors[label] = max(errors.get(label, 0.0), maximum)
        if not np.allclose(left, right, atol=atol, rtol=rtol):
            if not any(item["check"] == label for item in failures):
                failures.append({"check": label, "max_absolute_error": maximum, "atol": atol, "rtol": rtol})

    compare("generalized_position_dof_counts", [a.nq, a.nv], [b.nq, b.nv], 0.0)
    for attr in ("body_mass", "body_ipos"):
        compare(attr, getattr(a, attr)[ia], getattr(b, attr)[ib], 1e-10)
    for attr in ("jnt_type", "jnt_axis", "jnt_range", "jnt_limited"):
        compare(attr, getattr(a, attr)[ka], getattr(b, attr)[kb], 1e-10)

    def tensors(model, indices):
        result = []
        for i in indices:
            rotation = np.empty(9)
            mujoco.mju_quat2Mat(rotation, model.body_iquat[i])
            rotation = rotation.reshape(3, 3)
            result.append(rotation @ np.diag(model.body_inertia[i]) @ rotation.T)
        return result

    # MuJoCo's eigensolver can perturb reconstructed tensors by ~1e-10 kg m²
    # on the source robot. Compare physical tensors, not quaternion signs.
    compare("body_inertia_tensor_kg_m2", tensors(a, ia), tensors(b, ib), 1e-9, 1e-7)
    if failures:
        report.update(passed=False, status="failed")
        return report
    data_a, data_b = mujoco.MjData(a), mujoco.MjData(b)
    rng = np.random.default_rng(22922)
    for pose in range(poses):
        for name in joint_order:
            j, k = ja[name], jb[name]
            qa, qb = a.jnt_qposadr[j], b.jnt_qposadr[k]
            # Compare integer IDs: NumPy scalar / pybind enum equality varies by build.
            joint = int(a.jnt_type[j])
            if joint == int(mujoco.mjtJoint.mjJNT_FREE):
                values = np.r_[rng.uniform(-.1, .1, 3), rng.normal(size=4)]
                values[2] += .4
                values[3:] /= np.linalg.norm(values[3:])
                data_a.qpos[qa:qa+7] = data_b.qpos[qb:qb+7] = values
            elif joint in (int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE)):
                limits = a.jnt_range[j] if a.jnt_limited[j] else [-.5, .5]
                value = float(np.clip(0, *limits)) if pose == 0 else rng.uniform(*limits)
                data_a.qpos[qa] = data_b.qpos[qb] = value
            else:
                raise UrdfConversionError("Unexpected unsupported joint in verification")
        mujoco.mj_forward(a, data_a)
        mujoco.mj_forward(b, data_b)
        compare("fk_body_position_m", data_a.xpos[ia], data_b.xpos[ib], 1e-10)
        compare("fk_body_rotation_matrix", data_a.xmat[ia], data_b.xmat[ib], 1e-10)
    report.update(passed=not failures, status="passed" if not failures else "failed")
    return report

