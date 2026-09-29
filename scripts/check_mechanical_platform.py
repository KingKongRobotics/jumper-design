#!/usr/bin/env python3
"""Read-only identity and mesh-readability checks; not manufacturing acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import platform_pack


def check(root, directory):
    import numpy as np
    import trimesh

    manifest_path = directory / "platform.json"
    manifest = platform_pack.validate_manifest(platform_pack.load_json(manifest_path.read_bytes()))
    catalog = json.loads((root / "platforms/catalog/original-robot-v1.json").read_text())
    profile = json.loads((root / "robots/jumper/profile.json").read_text())
    if manifest["id"] != profile["mechanical_platform"]:
        raise ValueError("Mechanical platform identity differs from robot profile")
    if platform_pack.sha256(manifest_path) != catalog["platform_manifest_sha256"]:
        raise ValueError("Installed manifest differs from pinned catalog")
    meshes = []
    step_hash = None
    for item in manifest["files"]:
        path = directory.joinpath(*platform_pack.safe_relative(item["path"]).parts)
        if not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError("Asset escapes platform directory")
        if path.stat().st_size != item["bytes"] or platform_pack.sha256(path) != item["sha256"]:
            raise ValueError("Asset hash or size mismatch: " + item["path"])
        if item["role"] == "source_step":
            step_hash = platform_pack.sha256(path)
        if item["role"] == "interface_module" and path.suffix == ".stl":
            mesh = trimesh.load_mesh(path, process=False)
            if not len(mesh.faces) or not np.isfinite(mesh.vertices).all():
                raise ValueError("Empty or nonfinite interface mesh: " + item["path"])
            meshes.append({"path": item["path"], "faces": len(mesh.faces),
                           "bounds_mm": mesh.bounds.tolist()})
    if step_hash != profile["source_step_sha256"] or step_hash != manifest["source_step_sha256"]:
        raise ValueError("Source STEP differs from current robot reference")
    if len(meshes) != 7:
        raise ValueError("Expected ring plus six post STL modules")
    return {"ok": True, "scope": "identity_integrity_and_mesh_readability_only",
            "assets_checked": len(manifest["files"]), "source_step_sha256": step_hash,
            "profile_sha256": hashlib.sha256((root / "robots/jumper/profile.json").read_bytes()).hexdigest(),
            "meshes": meshes, "six_hole_interface_validated": False,
            "internal_keepouts_validated": False, "physical_fit_tested": False,
            "redistribution_status": manifest.get("redistribution_status", "unconfirmed")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--platform-dir", type=Path, default=root / ".local/platforms/original-robot-v1")
    args = parser.parse_args()
    try:
        result = check(root, args.platform_dir)
    except (ValueError, OSError, KeyError, TypeError, ImportError) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
