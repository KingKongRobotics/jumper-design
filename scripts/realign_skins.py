"""Reassemble inventoried .skin archives against a new trusted robot profile.

Example: python scripts/realign_skins.py --inventory outputs/jumper-update-20260925/skin-inventory.json
    --profile robots/jumper/profile.json --output outputs/jumper-update-20260925/realigned --version 2.0.0
The source manufacturing STL/3MF bytes are retained; physical fit is unverified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shellflow.package_io import json_object, read_archive
from shellflow.packages import verify_package
from shellflow.simulation import assemble
from shellflow.skin_package import IDENT, export_skin


REPO = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_records(inventory: Path) -> list[dict]:
    document = json.loads(inventory.read_text(encoding="utf-8"))
    records = document["skin_archives"]
    if not isinstance(records, list) or not records:
        raise ValueError("Inventory has no skin_archives")
    seen_names = set()
    for record in records:
        source = Path(record["source_path"])
        if not source.is_file() or source.suffix.lower() != ".skin":
            raise ValueError(f"Missing .skin source: {source}")
        if not isinstance(record.get("sha256"), str) or sha(source) != record["sha256"]:
            raise ValueError(f"Inventory SHA256 mismatch: {source}")
        key = source.name.casefold()
        if key in seen_names:
            raise ValueError(f"Duplicate source basename: {source.name}")
        seen_names.add(key)
    return records


def migrate(inventory: Path, profile: Path, output: Path, version: str,
            *, faces: int = 100000, render_preview: bool = False) -> dict:
    inventory, profile, output = Path(inventory).resolve(), Path(profile).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    if faces < 1000:
        raise ValueError("--faces must be at least 1000")
    records = source_records(inventory)
    target_profile = json_object(profile.read_bytes(), "new trusted profile")
    target_id = target_profile["id"]
    if not isinstance(target_id, str) or not IDENT.fullmatch(target_id):
        raise ValueError("Invalid new platform ID")
    target_sha = sha(profile)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = output.parent / f".realign-{uuid.uuid4().hex}"
    stage.mkdir()
    completed: dict[str, Path] = {}
    migrations = []
    try:
        (stage / "skins").mkdir()
        (stage / "work").mkdir()
        for record in records:
            source = Path(record["source_path"]).resolve()
            old_sha = record["sha256"]
            new_path = stage / "skins" / source.name
            if old_sha not in completed:
                old_files = read_archive(source)
                old_manifest = json_object(old_files["skin-package.json"], "skin-package.json")
                old_id = old_manifest["platform"]["id"]
                if not isinstance(old_id, str) or not IDENT.fullmatch(old_id):
                    raise ValueError("Invalid old platform ID")
                old_profile = REPO / "robots" / old_id / "profile.json"
                if not old_profile.is_file():
                    raise ValueError(f"Trusted old platform profile is missing: {old_profile}")
                verify_package(source, platform_profile=old_profile, mujoco=True)
                work = stage / "work" / old_sha
                (work / "source" / "print").mkdir(parents=True)
                shell = work / "source" / "print" / "shell.stl"
                shell.write_bytes(old_files["print/shell.stl"])
                ams = None
                if "print/ams.3mf" in old_files:
                    ams = work / "source" / "print" / "ams.3mf"
                    ams.write_bytes(old_files["print/ams.3mf"])
                assembled = work / "assembled"
                assemble(shell, assembled, profile, ams3mf=ams, faces=faces)
                preview = None
                if render_preview:
                    preview = work / "preview.png"
                    subprocess.run([sys.executable, str(REPO / "scripts" / "preview_simulation.py"),
                                    str(assembled), "--render", str(preview)], check=True)
                    if not preview.is_file():
                        raise ValueError("Preview renderer did not produce a PNG")
                export_skin(assembled, profile, shell, new_path,
                            package_id=old_manifest["id"], title=old_manifest["title"],
                            version=version, author=old_manifest["author"],
                            license_id=old_manifest["license_id"], ams=ams, preview=preview)
                verify_package(new_path, platform_profile=profile, mujoco=True)
                new_files = read_archive(new_path)
                for name in ("print/shell.stl", "print/ams.3mf"):
                    if old_files.get(name) != new_files.get(name):
                        raise ValueError(f"Manufacturing source changed: {name}")
                completed[old_sha] = new_path
            else:
                shutil.copyfile(completed[old_sha], new_path)
            if sha(source) != old_sha:
                raise ValueError(f"Original archive changed during migration: {source}")
            migrations.append({"source_path": str(source), "source_sha256": old_sha,
                               "new_path": str(output / "skins" / source.name),
                               "new_sha256": sha(new_path), "new_profile_sha256": target_sha,
                               "assembled_path": str(output / "work" / old_sha / "assembled"),
                               "deduplicated": completed[old_sha] != new_path})
        report = {"ok": True, "target_platform": target_id, "target_version": version,
                  "new_profile_sha256": target_sha,
                  "distinct_source_contents": len(completed), "sources": migrations,
                  "manufacturing_source_bytes_preserved": True,
                  "original_archives_unchanged": True,
                  "new_preview_rendered": render_preview,
                  "physical_fit_tested": False,
                  "mechanical_interface_physically_verified": False,
                  "physical_dynamics_validated": False}
        (stage / "migration-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if sha(profile) != target_sha:
            raise ValueError("New trusted profile changed during migration")
        if output.exists():
            raise FileExistsError(f"Output appeared during migration: {output}")
        stage.rename(output)
        return report
    except BaseException:
        if (stage.exists() and stage.resolve().parent == output.parent.resolve()
                and stage.name.startswith(".realign-")):
            shutil.rmtree(stage)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--faces", type=int, default=100000)
    parser.add_argument("--render-preview", action="store_true")
    args = parser.parse_args()
    report = migrate(args.inventory, args.profile, args.output, args.version,
                     faces=args.faces, render_preview=args.render_preview)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
