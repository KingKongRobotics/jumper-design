"""Native MuJoCo .skin + .map consumer: validate, attach, compile, forward.

Run from the repository root (or an installed shellflow environment). This is
a structural loading check; an application must implement spawn/reset itself.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path, PurePosixPath

import mujoco

try:
    from shellflow.map_package import MAP_LIMITS
    from shellflow.package_io import json_object, read_archive
    from shellflow.packages import verify_package
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from shellflow.map_package import MAP_LIMITS
    from shellflow.package_io import json_object, read_archive
    from shellflow.packages import verify_package


def runtime_files(files: dict[str, bytes], root: str, entry: str) -> dict[str, bytes]:
    """Keep only the entry XML and resources below its runtime directory."""
    prefix = root.rstrip("/") + "/" if root else ""
    return {name[len(prefix):]: data for name, data in files.items()
            if name.startswith(prefix) and
            (name == entry or PurePosixPath(name).suffix.lower() not in
             {".json", ".md", ".3mf"})}


def make_spec(files: dict[str, bytes], entry: str, root: str) -> tuple[mujoco.MjSpec, dict[str, bytes]]:
    subset = runtime_files(files, root, entry)
    xml_name = entry[len(root.rstrip("/") + "/"):] if root else entry
    if root.startswith("assembled/"):
        subset = {name: data for name, data in subset.items()
                  if name == xml_name or name.startswith("meshes/")}
    assets = {name: data for name, data in subset.items() if name != xml_name}
    # STL is a runtime mesh when referenced by robot.xml. Retain all mesh files
    # under the assembly directory, but never print/ or provenance/ blobs.
    if root:
        prefix = root.rstrip("/") + "/"
        assets.update({name[len(prefix):]: data for name, data in files.items()
                       if name.startswith(prefix + "meshes/")})
    return mujoco.MjSpec.from_string(files[entry].decode("utf-8-sig"), assets=assets), assets


def counts(model: mujoco.MjModel) -> dict[str, int]:
    return {"bodies": model.nbody, "joints": model.njnt, "geoms": model.ngeom,
            "sensors": model.nsensor, "actuators": model.nu}


def names(model: mujoco.MjModel, kind: mujoco.mjtObj, count: int) -> list[str | None]:
    return [mujoco.mj_id2name(model, kind, i) for i in range(count)]


def options(model: mujoco.MjModel) -> dict[str, str]:
    return {key: repr(value) for key in dir(model.opt) if not key.startswith("_")
            and not callable(value := getattr(model.opt, key))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skin", type=Path, required=True)
    parser.add_argument("--map", dest="map_path", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True, help="Trusted local platform profile")
    parser.add_argument("--capability", action="append", default=None,
                        help="Actual consumer capability (repeatable; default: rigid)")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    capabilities = set(args.capability) if args.capability is not None else {"rigid"}
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    platform = profile["id"]
    skin_report = verify_package(args.skin, platform_profile=args.profile,
                                 capabilities=capabilities | {platform})
    map_report = verify_package(args.map_path, capabilities=capabilities | {platform},
                                platform_profile=args.profile)
    if skin_report["kind"] != "skin" or map_report["kind"] != "map":
        raise ValueError("Expected one .skin and one .map")
    skin_files = read_archive(args.skin)
    map_files = read_archive(args.map_path, limits=MAP_LIMITS)
    map_manifest = json_object(map_files["scene-package.json"])
    robot_xml = f"assembled/{platform}/robot.xml"
    map_xml = map_manifest["world"]["file"]
    if any("file" in prop for prop in map_manifest.get("props", [])):
        raise ValueError("This example does not attach independent props[].file models")
    robot_spec, robot_assets = make_spec(skin_files, robot_xml, f"assembled/{platform}")
    map_parent = PurePosixPath(map_xml).parent
    environment_files = {name: data for name, data in map_files.items()
                         if not name.startswith("robot/")}
    map_spec, map_assets = make_spec(environment_files, map_xml,
                                     "" if map_parent == PurePosixPath(".") else str(map_parent))
    # MuJoCo's VFS can fall back to basename; reject ambiguous cross-package
    # resources before native parsing or attach.
    robot_names = {PurePosixPath(name).name.casefold() for name in robot_assets}
    map_names = {PurePosixPath(name).name.casefold() for name in map_assets}
    collisions = sorted(robot_names & map_names)
    if collisions:
        raise ValueError(f"Cross-package resource basename collision: {collisions}")
    robot_model = robot_spec.compile()
    map_model = map_spec.compile()
    before = counts(robot_model)
    before_timestep = robot_model.opt.timestep
    before_options = options(robot_model)
    prefix = map_manifest["world"]["attach"]["prefix"]
    robot_spec.attach(map_spec, prefix=prefix,
                      frame=robot_spec.worldbody.add_frame(name="package_map_frame"))
    combined = robot_spec.compile()
    data = mujoco.MjData(combined)
    mujoco.mj_forward(combined, data)
    after = counts(combined)
    map_counts = counts(map_model)
    if any(after[key] != before[key] + map_counts[key] for key in ("joints", "sensors", "actuators")):
        raise ValueError("Attach lost or added unexpected joints, sensors, or actuators")
    for kind, count in ((mujoco.mjtObj.mjOBJ_JOINT, "joints"),
                        (mujoco.mjtObj.mjOBJ_SENSOR, "sensors"),
                        (mujoco.mjtObj.mjOBJ_ACTUATOR, "actuators")):
        if names(robot_model, kind, before[count]) != names(combined, kind, before[count]):
            raise ValueError(f"Attach changed robot {count} names")
    for field in ("jnt_type", "jnt_axis", "jnt_range", "jnt_limited", "jnt_stiffness"):
        if not (getattr(robot_model, field) == getattr(combined, field)[:before["joints"]]).all():
            raise ValueError(f"Attach changed robot {field}")
    if options(combined) != before_options:
        raise ValueError("Attach changed robot options")
    if not math.isclose(combined.opt.timestep, before_timestep, rel_tol=0, abs_tol=1e-12):
        raise ValueError("Attach changed robot timestep")
    report = {
        "ok": True, "scope": "validate_attach_compile_forward_only",
        "mujoco_version": mujoco.__version__, "capabilities": sorted(capabilities),
        "skin": {"id": skin_report["id"], "sha256": skin_report["sha256"],
                 "trusted_platform_profile": True},
        "map": {"id": map_report["id"], "sha256": map_report["sha256"]},
        "counts": {"robot": before, "map": counts(map_model), "combined": after},
        "robot_timestep": before_timestep, "combined_timestep": combined.opt.timestep,
        "robot_joints_sensors_actuators_and_options_preserved": True,
        "spawn": map_manifest.get("spawn"), "spawn_applied": False,
        "physical_dynamics_validated": False, "physical_fit_tested": False,
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
