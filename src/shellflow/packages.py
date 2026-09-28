"""Public producer/consumer dispatch for .skin and .map files."""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

from .package_io import PackageError, extract_files, json_object, read_archive, write_archive


def validate_content(files, *, platform_profile=None, capabilities=None):
    manifests = {"skin-package.json", "scene-package.json"} & files.keys()
    if len(manifests) != 1:
        raise PackageError("Exactly one skin-package.json or scene-package.json is required at ZIP root")
    name = next(iter(manifests))
    manifest = json_object(files[name], name)
    if name == "skin-package.json":
        from .skin_package import validate
        result = validate(files, platform_profile=platform_profile, capabilities=capabilities)
        kind, schema = "skin", result["schema"]
    else:
        from .map_package import validate
        validate(files, capabilities=capabilities, platform_profile=platform_profile)
        result = {"title": manifest.get("title"), "validation_scope": "structure_and_hashes"}
        kind, schema = "map", manifest.get("schema")
    if manifest.get("schema") != schema:
        raise PackageError(f"Unsupported schema: {manifest.get('schema')!r}")
    return {**result, "ok": True, "kind": kind, "schema": schema, "id": manifest.get("id"),
            "file_count": len(files), "expanded_bytes": sum(map(len, files.values())),
            "capability_check": "checked" if capabilities is not None else "not_requested"}


def _load(path, *, platform_profile=None, capabilities=None):
    path = Path(path)
    if path.name.lower().endswith((".map", ".scene.zip")):
        from .map_package import MAP_LIMITS
        files = read_archive(path, limits=MAP_LIMITS)
    else:
        files = read_archive(path)
    result = validate_content(files, platform_profile=platform_profile, capabilities=capabilities)
    suffixes = (".skin",) if result["kind"] == "skin" else (".map", ".scene.zip")
    if not path.name.lower().endswith(suffixes):
        raise PackageError(f"Extension does not match {result['kind']} content; expected {suffixes}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    result.update(archive=str(path), sha256=digest.hexdigest(), archive_bytes=path.stat().st_size)
    return files, result


def verify_package(path, *, platform_profile=None, capabilities=None, mujoco=False):
    files, result = _load(path, platform_profile=platform_profile, capabilities=capabilities)
    if mujoco:
        result["native_mujoco"] = compile_native(files, result["kind"])
    return result


def import_package(path, destination, *, platform_profile=None, capabilities=None, mujoco=False):
    files, result = _load(path, platform_profile=platform_profile, capabilities=capabilities)
    if mujoco:
        result["native_mujoco"] = compile_native(files, result["kind"])
    result["destination"] = str(extract_files(files, Path(destination)))
    return result


def repack_package(path, output, *, platform_profile=None, capabilities=None):
    files, result = _load(path, platform_profile=platform_profile, capabilities=capabilities)
    expected = ".skin" if result["kind"] == "skin" else ".map"
    if Path(output).suffix.lower() != expected:
        raise PackageError(f"Output must use {expected}")
    write_archive(Path(output), files)
    return verify_package(output, platform_profile=platform_profile, capabilities=capabilities)


def compile_native(files, kind):
    """Compile from in-memory VFS. This is a loading check, not physical validation."""
    try:
        import mujoco
    except ImportError as error:
        raise PackageError("Native loading check needs the optional sim dependencies: pip install -e '.[sim]'") from error
    if kind == "map":
        manifest = json_object(files["scene-package.json"])
        if manifest["schema"] == "kk-scene-package/2":
            from .map_package import compose_default
            model, data, composition = compose_default(files)
            return {"passed": True, "version": mujoco.__version__,
                    "models": [{"entry": "robot+" + manifest["world"]["file"],
                                "bodies": model.nbody, "joints": model.njnt,
                                "actuators": model.nu, "geoms": model.ngeom}],
                    "composition": composition, "scope": "compile_and_forward_only",
                    "physical_dynamics_validated": False}
        paths = [manifest["world"]["file"]]
        paths.extend(prop["file"] for prop in manifest.get("props", []) if "file" in prop)
    else:
        paths = sorted(name for name in files if name.startswith("assembled/")
                       and PurePosixPath(name).name in ("robot.xml", "scene.xml", "robot.urdf"))
    models = []
    for name in paths:
        # Root each independent model at its own directory, preserving relative resources.
        parent = str(PurePosixPath(name).parent)
        prefix = "" if parent == "." else parent + "/"
        assets = {key[len(prefix):]: value for key, value in files.items() if key.startswith(prefix)}
        try:
            model = mujoco.MjModel.from_xml_string(files[name].decode("utf-8-sig"), assets=assets)
            data = mujoco.MjData(model)
            mujoco.mj_forward(model, data)
        except Exception as error:
            raise PackageError(f"Native MuJoCo could not load {name}: {error}") from error
        models.append({"entry": name, "bodies": model.nbody, "joints": model.njnt,
                       "actuators": model.nu, "geoms": model.ngeom})
    if not models:
        raise PackageError("No runtime model entry found")
    return {"passed": True, "version": mujoco.__version__, "models": models,
            "scope": "compile_and_forward_only", "physical_dynamics_validated": False}
