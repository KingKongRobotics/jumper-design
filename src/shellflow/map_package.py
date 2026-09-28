"""Build and validate versioned scene archives with a .map filename.

The archive extension is a transport convention. The manifest and MJCF layout
remain the format shared by scene-design, kk-rl-mjlab, and BE UNLIMITED.
"""

from __future__ import annotations

import json
import hashlib
import math
import posixpath
import re
import shutil
import uuid
from pathlib import PurePosixPath
from contextlib import contextmanager
from pathlib import Path

from .package_io import (Limits, PackageError, file_records, json_object, parse_xml,
                         read_archive, safe_path, validate_files, write_archive)
from .package_preview import add_preview, validate_preview

MANIFEST = "scene-package.json"
SCHEMA_V1 = "kk-scene-package/1"
SCHEMA = "kk-scene-package/2"
ROBOT_ROOT = "robot"
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*\Z")
_PREFIX = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_FORBIDDEN = {"option", "include", "plugin", "extension"}
MAP_LIMITS = Limits(archive_bytes=64 * 1024 * 1024,
                    expanded_bytes=192 * 1024 * 1024,
                    file_bytes=192 * 1024 * 1024, files=256)


@contextmanager
def _working_directory(parent: Path):
    # tempfile.mkdtemp uses mode 0700, which some managed Windows workspaces
    # cannot traverse even when their parent is writable. Use the parent's
    # normal inherited ACL and still publish only the final archive.
    parent = parent.resolve()
    path = parent / f".shellflow-map-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        if path.parent.resolve() == parent and path.name.startswith(".shellflow-map-"):
            shutil.rmtree(path)


def _object(value: object, name: str) -> dict:
    if not isinstance(value, dict):
        raise PackageError(f"{name} must be an object")
    return value


def _list(value: object, name: str) -> list:
    if not isinstance(value, list):
        raise PackageError(f"{name} must be an array")
    return value


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise PackageError(f"{name} must be a finite number")
    return float(value)


def _vector(value: object, name: str, count: int) -> None:
    for i, item in enumerate(_list(value, name)):
        _finite(item, f"{name}[{i}]")
    if len(value) != count:
        raise PackageError(f"{name} needs {count} numbers")


def _xml(files: dict[str, bytes], path: str):
    if path not in files:
        raise PackageError(f"missing MJCF file: {path}")
    root = parse_xml(files[path])
    if root.tag != "mujoco":
        raise PackageError(f"{path} is not a MuJoCo model")
    for element in root.iter():
        if element.tag in _FORBIDDEN:
            raise PackageError(f"{path} contains forbidden <{element.tag}>")
    return root


def _resolve(base: str, directory: str, reference: str) -> str:
    # All references are archive-local. A path that normalizes away '..' is
    # still rejected, since another consumer may resolve it differently.
    if directory:
        safe_path(directory)
    safe_path(reference)
    return safe_path(posixpath.join(posixpath.dirname(base), directory, reference))


def _resource_refs(files: dict[str, bytes], xml_path: str, root) -> set[str]:
    compiler = root.find("compiler")
    if compiler is not None and compiler.get("strippath", "false").lower() == "true":
        raise PackageError(f"{xml_path} uses compiler strippath, which changes resource paths")
    dirs = {key: (compiler.get(key) or "") if compiler is not None else ""
            for key in ("assetdir", "meshdir", "texturedir")}
    for directory in dirs.values():
        if directory:
            safe_path(directory)
    child_models = set()
    for element in root.iter():
        for attribute, reference in element.attrib.items():
            if attribute != "file" and not (element.tag == "texture" and
                                           attribute in {"filefront", "fileback", "fileleft",
                                                         "fileright", "fileup", "filedown"}):
                continue
            if element.tag == "model":
                directory = ""
            elif element.tag == "mesh":
                directory = dirs["meshdir"] or dirs["assetdir"]
            elif element.tag == "texture":
                directory = dirs["texturedir"] or dirs["assetdir"]
            else:
                directory = dirs["assetdir"]
            target = _resolve(xml_path, directory, reference)
            if target not in files:
                raise PackageError(f"{xml_path} references missing resource {target}")
            if element.tag == "model":
                child_models.add(target)
    return child_models


def _required_capabilities(manifest: dict, roots: dict[str, object]) -> set[str]:
    declared = manifest.get("requiredCapabilities", [])
    if not isinstance(declared, list) or any(not isinstance(x, str) or not x for x in declared):
        raise PackageError("requiredCapabilities must be an array of names")
    required = set(declared)
    if len(required) != len(declared):
        raise PackageError("duplicate requiredCapabilities")
    if manifest.get("flex") or any(e.tag in ("flex", "flexcomp") for r in roots.values() for e in r.iter()):
        required.add("flex")
    if any(e.tag == "hfield" for r in roots.values() for e in r.iter()):
        required.add("hfield")
    return required


def validate(files: dict[str, bytes], *, capabilities: set[str] | None = None,
             platform_profile: Path | None = None) -> dict:
    """Validate archive bytes and return its manifest; fail closed on contract drift.

    ``capabilities=None`` inspects a package without choosing a consumer.
    Supplying a set enforces every required capability, including flex/hfield.
    """
    if MANIFEST not in files:
        raise PackageError(f"missing {MANIFEST}")
    manifest = json_object(files[MANIFEST], MANIFEST)
    if len(files) > MAP_LIMITS.files or sum(map(len, files.values())) > MAP_LIMITS.expanded_bytes:
        raise PackageError("scene package exceeds resource budget")
    schema = manifest.get("schema")
    if schema not in (SCHEMA_V1, SCHEMA):
        raise PackageError("unsupported scene package schema")
    ident = manifest.get("id")
    if not isinstance(ident, str) or not _ID.fullmatch(ident):
        raise PackageError("invalid scene package id")
    if manifest.get("use") == "training":
        raise PackageError("training-only scenes cannot be used as a watch scene")
    if manifest.get("use") not in ("watching", "both"):
        raise PackageError("invalid scene package use")

    from .web_appearance import validate_appearance
    validate_appearance(files)
    inventory = _object(manifest.get("files"), "files")
    validate_files(manifest, files, MANIFEST, optional=("README.md", "LICENSE"))
    if schema == SCHEMA:
        validate_preview(manifest, files)
    all_names = [safe_path(name) for name in files]
    if len(all_names) != len(set(all_names)):
        raise PackageError("duplicate archive paths")
    # The robot is a separate, fully validated package namespace. MuJoCo
    # receives each model's own relative VFS, so its filenames may repeat
    # names in the environment without becoming ambiguous.
    scene_names = [name for name in all_names if not name.startswith(ROBOT_ROOT + "/")]
    basenames: dict[str, str] = {}
    for name in scene_names:
        base = posixpath.basename(name).casefold()
        if base in basenames:
            raise PackageError(f"duplicate basename: {basenames[base]}, {name}")
        basenames[base] = name
    unhashed_optional = {name for name in ("README.md", "LICENSE")
                         if name in files and name not in inventory}
    if set(inventory) != set(files) - {MANIFEST} - unhashed_optional:
        raise PackageError("file inventory does not match archive")

    world = _object(manifest.get("world"), "world")
    world_file = safe_path(world.get("file"))
    if world_file not in inventory or not world_file.endswith(".xml"):
        raise PackageError("world.file must name a declared MJCF file")
    attach = _object(world.get("attach"), "world.attach")
    prefix = attach.get("prefix")
    if not isinstance(prefix, str) or not _PREFIX.fullmatch(prefix):
        raise PackageError("world.attach.prefix is invalid")
    roots = {world_file: _xml(files, world_file)}
    world_root = roots[world_file]
    compiler = world_root.find("compiler")
    asset_dir = compiler.get("assetdir", "") if compiler is not None else ""
    if "assetDir" in world and world["assetDir"] != asset_dir:
        raise PackageError("world.assetDir disagrees with scene compiler assetdir")
    counts = world.get("counts")
    if counts is not None:
        counts = _object(counts, "world.counts")
        worldbodies = world_root.findall("worldbody")
        asset = world_root.find("asset")
        actual = {
            "geoms": sum(1 for w in worldbodies for _ in w.iter("geom")),
            "bodies": sum(1 for w in worldbodies for _ in w.iter("body")),
            "lights": sum(1 for w in worldbodies for _ in w.iter("light")),
            "textures": sum(1 for _ in asset.iter("texture")) if asset is not None else 0,
            "materials": sum(1 for _ in asset.iter("material")) if asset is not None else 0,
            "meshes": sum(1 for _ in asset.iter("mesh")) if asset is not None else 0,
        }
        for kind, observed in actual.items():
            if kind in counts and (type(counts[kind]) is not int or counts[kind] != observed):
                raise PackageError(f"world.counts.{kind} disagrees with scene.xml")
    props = _list(manifest.get("props"), "props")
    bodies = {b.get("name"): b for b in world_root.iter("body") if b.get("name")}
    world_geoms = {g.get("name") for g in world_root.iter("geom") if g.get("name")}
    ground = _object(world.get("ground", {}), "world.ground")
    if ground.get("geom") and ground["geom"] not in world_geoms:
        raise PackageError("world.ground.geom does not exist")
    for geom in _list(world.get("decorativeGeoms", []), "world.decorativeGeoms"):
        if geom not in world_geoms:
            raise PackageError(f"world.decorativeGeoms references missing geom {geom}")
    for item in _list(world.get("collidingGeoms", []), "world.collidingGeoms"):
        geom = _object(item, "world.collidingGeoms entry").get("geom")
        if geom not in world_geoms:
            raise PackageError(f"world.collidingGeoms references missing geom {geom}")
    for index, item in enumerate(props):
        prop = _object(item, f"props[{index}]")
        name = prop.get("name")
        if not isinstance(name, str) or not name:
            raise PackageError(f"props[{index}].name is invalid")
        if "file" in prop:
            prop_file = safe_path(prop["file"])
            if prop_file not in inventory or not prop_file.endswith(".xml"):
                raise PackageError(f"props[{index}].file is not a declared MJCF file")
            roots[prop_file] = _xml(files, prop_file)
            prop_root = roots[prop_file]
            if "position" in prop:
                raise PackageError("independent prop cannot use world position")
            if "initPositionRelativeToRobot" in prop:
                _vector(prop["initPositionRelativeToRobot"],
                        f"props[{index}].initPositionRelativeToRobot", 3)
        else:
            body_name = prop.get("body")
            body = bodies.get(body_name)
            if body is None or body.find("freejoint") is None:
                raise PackageError(f"props[{index}].body is not a free world body")
            if prop.get("freeJoint") is not True:
                raise PackageError(f"props[{index}] must declare freeJoint")
            if "initPositionRelativeToRobot" in prop:
                raise PackageError("world prop cannot have a robot-relative position")
            if "position" in prop:
                _vector(prop["position"], f"props[{index}].position", 3)
            geom_names = {e.get("name") for e in body.iter("geom")}
            prop_root = body
            free_name = prop.get("freeJointName")
            if free_name and body.find("freejoint").get("name") != free_name:
                raise PackageError(f"props[{index}].freeJointName does not exist")
            for geom in _list(prop.get("geoms", []), f"props[{index}].geoms"):
                if geom not in geom_names:
                    raise PackageError(f"props[{index}] references missing geom {geom}")
        prop_geoms = {g.get("name") for g in prop_root.iter("geom") if g.get("name")}
        for contact in _list(prop.get("contact", []), f"props[{index}].contact"):
            geom = _object(contact, f"props[{index}].contact entry").get("geom")
            if geom not in prop_geoms:
                raise PackageError(f"props[{index}].contact references missing geom {geom}")
    world_names = {
        "lights": {e.get("name") for e in world_root.iter("light")},
        "cameras": {e.get("name") for e in world_root.iter("camera")},
        "flex": {e.get("name") for tag in ("flex", "flexcomp") for e in world_root.iter(tag)},
    }
    for entry in _list(manifest.get("lights", []), "lights"):
        name = _object(entry, "lights entry").get("name")
        if name not in world_names["lights"]:
            raise PackageError(f"lights references missing light {name}")
    for name in _list(manifest.get("cameras", []), "cameras"):
        if name not in world_names["cameras"]:
            raise PackageError(f"cameras references missing camera {name}")
    for entry in _list(manifest.get("flex", []), "flex"):
        name = _object(entry, "flex entry").get("id")
        if name not in world_names["flex"]:
            raise PackageError(f"flex references missing flex {name}")
    # Follow child-model references regardless of extension, then inspect any
    # other declared MJCF. Every model in the package gets the same checks.
    pending = list(roots) + [name for name in scene_names if name.endswith((".xml", ".mjcf"))]
    checked = set()
    while pending:
        name = pending.pop()
        if name in checked:
            continue
        if name not in roots:
            roots[name] = _xml(files, name)
        pending.extend(_resource_refs({key: value for key, value in files.items()
                                      if not key.startswith(ROBOT_ROOT + "/")},
                                     name, roots[name]) - checked)
        checked.add(name)

    spawn = manifest.get("spawn")
    if schema == SCHEMA and spawn is None:
        raise PackageError("kk-scene-package/2 requires spawn")
    if spawn is not None:
        spawn = _object(spawn, "spawn")
        _vector(spawn.get("position"), "spawn.position", 3)
        _finite(spawn.get("yaw"), "spawn.yaw")  # degrees per kk-scene-package/1
        if "clearance" in spawn:
            if _finite(spawn["clearance"], "spawn.clearance") < 0:
                raise PackageError("spawn.clearance must be nonnegative")
        if "bounds" in spawn:
            _vector(spawn["bounds"], "spawn.bounds", 6)
        if "site" in spawn:
            sites = {s.get("name") for s in roots[world_file].iter("site")}
            if spawn["site"] not in sites:
                raise PackageError("spawn.site does not exist in world")
    required = _required_capabilities(manifest, roots)
    if capabilities is not None:
        unsupported = required - capabilities
        if unsupported:
            raise PackageError(f"unsupported scene capabilities: {', '.join(sorted(unsupported))}")
    if schema == SCHEMA:
        from .skin_package import validate as validate_skin

        robot = _object(manifest.get("robot"), "robot")
        if set(robot) != {"skinRoot", "skinId", "platformId", "profileSha256"}:
            raise PackageError("robot binding has unknown or missing fields")
        if robot["skinRoot"] != ROBOT_ROOT:
            raise PackageError("robot.skinRoot must be robot")
        robot_prefix = ROBOT_ROOT + "/"
        robot_files = {name[len(robot_prefix):]: data for name, data in files.items()
                       if name.startswith(robot_prefix)}
        if not robot_files:
            raise PackageError("map has no bundled robot")
        # Reuse the full .skin checks, including whole-robot URDF/MJCF,
        # profile provenance, baselines, model resources and banned scripts.
        skin = json_object(robot_files.get("skin-package.json", b""), "bundled skin manifest")
        if skin.get("schema") != "kk-skin-package/3":
            raise PackageError("map default robot requires display-only .skin/3")
        skin_result = validate_skin(robot_files, platform_profile=platform_profile)
        platform = skin["platform"]
        if (robot["skinId"] != skin_result["id"]
                or robot["platformId"] != skin_result["platform_id"]
                or robot["profileSha256"] != platform["profile_sha256"]):
            raise PackageError("robot binding differs from bundled skin")
        if capabilities is not None and robot["platformId"] not in capabilities:
            raise PackageError("unsupported robot platform capability: " + robot["platformId"])
    elif "robot" in manifest:
        raise PackageError("kk-scene-package/1 cannot declare a bundled robot")
    return manifest


def export_environment(environment_files: dict[str, bytes], output: Path,
                       default_skin: Path, profile: Path,
                       preview: Path | None = None) -> dict:
    """Upgrade a validated /1 environment to /2 with a complete default robot."""
    from .english_metadata import require_english_text
    from .skin_package import validate as validate_skin

    output = Path(output)
    if output.suffix.lower() != ".map":
        raise PackageError("map output must end in .map")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    environment = validate(environment_files)
    require_english_text(environment['title'], 'map title')
    require_english_text(environment.get('description', ''), 'map description', allow_empty=True)
    if environment["schema"] != SCHEMA_V1:
        raise PackageError("export_environment requires a /1 scene package")
    skin_files = read_archive(Path(default_skin))
    skin_result = validate_skin(skin_files, platform_profile=Path(profile))
    if skin_result["schema"] != "kk-skin-package/3":
        raise PackageError("default robot must be a display-only .skin/3")
    skin = json_object(skin_files["skin-package.json"], "default skin")
    files = dict(environment_files)
    files.update({f"{ROBOT_ROOT}/{name}": data for name, data in skin_files.items()})
    manifest = dict(environment)
    manifest["schema"] = SCHEMA
    manifest.setdefault("spawn", {"position": [0, 0, 0], "yaw": 0})
    manifest["robot"] = {
        "skinRoot": ROBOT_ROOT, "skinId": skin_result["id"],
        "platformId": skin_result["platform_id"],
        "profileSha256": skin["platform"]["profile_sha256"],
    }
    if preview is not None:
        if Path(preview).suffix.lower() != ".png":
            raise PackageError("Preview must be PNG")
        add_preview(manifest, files, Path(preview))
    files[MANIFEST] = b""
    manifest["files"] = file_records({name: data for name, data in files.items()
                                      if name not in (MANIFEST, "README.md", "LICENSE")})
    files[MANIFEST] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")) + "\n").encode("utf-8")
    validate(files, platform_profile=Path(profile))
    write_archive(output, files, limits=MAP_LIMITS)
    return {"ok": True, "schema": SCHEMA, "id": manifest["id"],
            "output": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "file_count": len(files), "robot": manifest["robot"]}


def compose_default(files: dict[str, bytes], *, profile: Path | None = None):
    """Attach a /2 environment to its bundled robot and apply a display spawn.

    Returns ``(MjModel, MjData, report)`` for preview/consumer integration.
    A display pose is not a controller home or dynamics/fit certification.
    """
    try:
        import mujoco
    except ImportError as exc:
        raise PackageError("Native composition requires MuJoCo") from exc

    manifest = validate(files, platform_profile=profile)
    if manifest["schema"] != SCHEMA:
        raise PackageError("default robot composition requires .map/2")
    robot_root = ROBOT_ROOT + "/"
    platform = manifest["robot"]["platformId"]
    assembly_root = f"{robot_root}assembled/{platform}/"
    robot_xml = assembly_root + "robot.xml"
    if robot_xml not in files:
        raise PackageError("bundled robot has no native MJCF")
    robot_assets = {name[len(assembly_root):]: data for name, data in files.items()
                    if name.startswith(assembly_root + "meshes/")}
    world_xml = manifest["world"]["file"]
    world_parent = str(PurePosixPath(world_xml).parent)
    world_prefix = "" if world_parent == "." else world_parent + "/"
    world_assets = {name[len(world_prefix):]: data for name, data in files.items()
                    if name.startswith(world_prefix)
                    and not name.startswith(robot_root)
                    and name != world_xml and PurePosixPath(name).suffix.lower()
                    not in {".json", ".md"}}
    if any("file" in prop for prop in manifest["props"]):
        raise PackageError("default composer does not yet attach independent prop models")
    try:
        robot_spec = mujoco.MjSpec.from_string(files[robot_xml].decode("utf-8-sig"),
                                                assets=robot_assets)
        world_spec = mujoco.MjSpec.from_string(files[world_xml].decode("utf-8-sig"),
                                                assets=world_assets)
        robot_model = robot_spec.compile()
        prefix = manifest["world"]["attach"]["prefix"]
        robot_spec.attach(world_spec, prefix=prefix,
                          frame=robot_spec.worldbody.add_frame(name="package_map_frame"))
        # Attached heightfields still resolve their files through the parent VFS.
        # Keep both packages' assets available and reject ambiguous paths.
        for name, content in world_assets.items():
            if name in robot_assets and robot_assets[name] != content:
                raise PackageError(f"Robot and environment asset paths collide: {name}")
            robot_spec.assets[name] = content
        model = robot_spec.compile()
        import numpy as np
        for kind, count in ((mujoco.mjtObj.mjOBJ_BODY, robot_model.nbody),
                            (mujoco.mjtObj.mjOBJ_JOINT, robot_model.njnt),
                            (mujoco.mjtObj.mjOBJ_SENSOR, robot_model.nsensor),
                            (mujoco.mjtObj.mjOBJ_ACTUATOR, robot_model.nu)):
            before_names = [mujoco.mj_id2name(robot_model, kind, index)
                            for index in range(count)]
            after_names = [mujoco.mj_id2name(model, kind, index)
                           for index in range(count)]
            if before_names != after_names:
                raise PackageError("attach changed default robot identities")
        for field, count in (("jnt_type", robot_model.njnt),
                             ("jnt_axis", robot_model.njnt),
                             ("jnt_range", robot_model.njnt),
                             ("jnt_limited", robot_model.njnt),
                             ("jnt_stiffness", robot_model.njnt),
                             ("body_mass", robot_model.nbody),
                             ("body_inertia", robot_model.nbody)):
            if not np.array_equal(getattr(robot_model, field), getattr(model, field)[:count]):
                raise PackageError("attach changed default robot " + field)
        for key in dir(robot_model.opt):
            if key.startswith("_"):
                continue
            original, attached = getattr(robot_model.opt, key), getattr(model.opt, key)
            if callable(original):
                continue
            if isinstance(original, np.ndarray):
                same = np.array_equal(original, attached)
            else:
                same = original == attached
            if not same:
                raise PackageError("attach changed default robot option " + key)
        data = mujoco.MjData(model)
        # The skin's audited preview pose supplies visual base clearance and
        # legal joint positions. The map supplies the floor point and yaw.
        pose_path = assembly_root + "preview-pose.json"
        pose = json_object(files[pose_path], "robot preview pose") if pose_path in files else {}
        spawn = manifest["spawn"]
        position = list(spawn["position"])
        if "site" in spawn:
            mujoco.mj_forward(model, data)
            site = model.site(prefix + spawn["site"])
            position = list(data.site_xpos[site.id])
        free = model.joint("floating_base")
        if free.type != mujoco.mjtJoint.mjJNT_FREE:
            raise PackageError("default robot floating_base is not a free joint")
        address = int(free.qposadr[0])
        data.qpos[address:address + 3] = [position[0], position[1],
                                           position[2] + float(pose.get("base_height_m", 0))]
        yaw = math.radians(spawn["yaw"]) / 2
        data.qpos[address + 3:address + 7] = [math.cos(yaw), 0, 0, math.sin(yaw)]
        for name, value in pose.get("joints", {}).items():
            joint = model.joint(name)
            data.qpos[int(joint.qposadr[0])] = value
        mujoco.mj_forward(model, data)
        # A map can be structurally valid while its spawn buries the robot in
        # a counter or wall. Flag deep non-ground interpenetration at reset.
        ground = manifest["world"].get("ground", {}).get("geom")
        ground_name = prefix + ground if ground else None
        scene_geoms = {index for index in range(model.ngeom)
                       if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, index)
                           or "").startswith(prefix)}
        severe = []
        contact_distances = []
        for contact in data.contact:
            first, second = int(contact.geom1), int(contact.geom2)
            if (first in scene_geoms) == (second in scene_geoms):
                continue
            environment_geom = first if first in scene_geoms else second
            env_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM,
                                          environment_geom)
            if env_name == ground_name or model.geom_type[environment_geom] == mujoco.mjtGeom.mjGEOM_PLANE:
                continue
            contact_distances.append(float(contact.dist))
            if contact.dist < -0.03:
                severe.append({"environment_geom": env_name,
                               "penetration_m": round(-float(contact.dist), 6)})
        if severe:
            raise PackageError("default robot spawn penetrates environment: "
                               + json.dumps(severe[:5], ensure_ascii=False))
    except (ValueError, KeyError, RuntimeError, TypeError) as exc:
        raise PackageError(f"Native default robot composition failed: {exc}") from exc
    report = {"passed": True, "schema": SCHEMA, "map_id": manifest["id"],
              "robot_skin_id": manifest["robot"]["skinId"],
              "platform_id": platform, "robot_joints": robot_model.njnt,
              "combined_joints": model.njnt, "combined_geoms": model.ngeom,
              "spawn_applied": True, "spawn": spawn,
              "preview_pose_applied": bool(pose),
              "severe_spawn_contacts": 0,
              "minimum_non_ground_contact_distance_m": (
                  min(contact_distances) if contact_distances else None),
              "physical_dynamics_validated": False, "physical_fit_tested": False}
    return model, data, report


def export_map(spec: Path, output: Path, *, package_id: str | None = None,
               title: str | None = None, default_skin: Path,
               profile: Path, preview: Path | None = None) -> dict:
    """Compile a scene JSON and bundle a validated complete default robot."""
    from .english_metadata import require_english_text
    from mjscene import build, spec as spec_api
    from mjscene.export import scene_package

    spec = Path(spec)
    output = Path(output)
    if output.suffix.lower() != ".map":
        raise PackageError("map output must end in .map")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    try:
        data = json_object(spec.read_bytes(), "scene spec")
    except OSError as exc:
        raise PackageError(f"cannot read scene spec: {exc}") from exc
    data = dict(data)
    if package_id is not None:
        data["name"] = package_id
    if title is not None:
        data["title"] = title
    elif not data.get("title") and isinstance(data.get("name"), str):
        data["title"] = data["name"]
    require_english_text(data.get("title"), 'map title')
    require_english_text(data.get("description", ""), 'map description', allow_empty=True)
    result = spec_api.validate(data)
    if not result.ok:
        raise PackageError("invalid scene spec: " + "; ".join(str(i) for i in result.errors))
    if not _ID.fullmatch(data["name"]):
        raise PackageError("invalid scene package id")
    output.parent.mkdir(parents=True, exist_ok=True)
    with _working_directory(output.parent) as temp:
        scene_dir = temp / data["name"]
        build.compile_scene(data, scene_dir / "build", spec.parent)
        exported = scene_package.export(scene_dir, scene_dir / "export")
        files = read_archive(exported.archive, limits=MAP_LIMITS)
        return export_environment(files, output, default_skin, profile, preview=preview)
