#!/usr/bin/env python3
"""Create and install hash-verified platform bundles; requires Python 3.10+."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import zipfile

MAX_FILES = 4096
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
METADATA = "pack_metadata/local_audit.json"
ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}\Z")
HASH_PATTERN = re.compile(r"[a-f0-9]{64}\Z")
ABSOLUTE_PATTERN = re.compile(r"(?i)(?:[a-z]:[\\/]|/(?:Users|home)/[^\s/]+)")
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
PUBLIC_FIELDS = (
    "version", "units", "protected_function_face_count", "perimeter_function_faces",
    "pillar_function_faces", "primary_post_count", "auxiliary_post_count",
    "assembly_direction", "interface_xy_envelope_mm", "physical_fit_tested",
)


class PackError(ValueError):
    pass


def safe_relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise PackError("Invalid relative archive path")
    parts = value.split("/")
    if any(not p or p in {".", ".."} or ":" in p or p[-1:] in {".", " "} or
           p.split(".")[0].lower() in RESERVED or any(ord(c) < 32 for c in p) for p in parts):
        raise PackError("Unsafe archive path")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise PackError("Absolute archive path")
    return path


def validate_id(value: str) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value) or value in RESERVED:
        raise PackError("Invalid platform id")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def load_json(data: bytes) -> dict:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise PackError("Duplicate JSON key")
            result[key] = value
        return result
    result = json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique_pairs)
    if not isinstance(result, dict):
        raise PackError("Expected JSON object")
    return result


def validate_manifest(manifest: dict) -> dict:
    if manifest.get("schema_version") != 1:
        raise PackError("Unsupported platform schema")
    validate_id(manifest.get("id"))
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries or len(entries) > MAX_FILES - 2:
        raise PackError("Invalid asset list")
    known = set()
    total = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise PackError("Invalid asset entry")
        name = safe_relative(entry.get("path")).as_posix()
        if name.casefold() in known or name.casefold() in {"platform.json", METADATA.casefold()}:
            raise PackError("Duplicate or reserved asset path")
        known.add(name.casefold())
        size = entry.get("bytes")
        if type(size) is not int or not 0 <= size <= MAX_FILE_BYTES:
            raise PackError("Invalid or excessive asset size")
        total += size
        if not isinstance(entry.get("sha256"), str) or not HASH_PATTERN.fullmatch(entry["sha256"]):
            raise PackError("Invalid asset SHA256")
        if not isinstance(entry.get("role"), str) or not entry["role"]:
            raise PackError("Missing asset role")
    if total > MAX_TOTAL_BYTES:
        raise PackError("Bundle exceeds total size limit")
    # The descriptor is portable. Historical paths may remain only inside immutable assets.
    if ABSOLUTE_PATTERN.search(json.dumps(manifest, ensure_ascii=False)):
        raise PackError("Platform descriptor contains a machine absolute path")
    return manifest


def export_pack(suite: Path, platform_id: str, output: Path) -> dict:
    platform_id = validate_id(platform_id)
    suite = suite.resolve(strict=True)
    source = load_json((suite / "platforms" / (platform_id + ".json")).read_bytes())
    if source.get("id") != platform_id:
        raise PackError("Platform identity mismatch")
    manifest = {"schema_version": 1, "id": platform_id, "redistribution_status": "unconfirmed",
                "files": [], **{k: source[k] for k in PUBLIC_FIELDS if k in source}}
    assets = []
    audit = []
    for entry in source.get("files", []):
        relative = safe_relative(entry["path"])
        original = suite.joinpath(*relative.parts)
        resolved = original.resolve(strict=True)
        if not resolved.is_relative_to(suite) or not resolved.is_file() or original.is_symlink():
            raise PackError("Source asset escapes suite or is not a regular file")
        name = safe_relative(entry["copy_as"]).as_posix()
        size = resolved.stat().st_size
        digest = sha256(resolved)
        if digest != entry["sha256"] or size != entry["bytes"]:
            raise PackError("Source asset SHA256 or size mismatch: " + name)
        manifest["files"].append({"role": entry["role"], "path": name, "bytes": size, "sha256": digest})
        if entry["role"] == "source_step":
            manifest["source_step_sha256"] = digest
        assets.append((resolved, name))
        if resolved.suffix.lower() in {".json", ".txt", ".csv", ".md"} and size < MAX_MANIFEST_BYTES:
            count = len(ABSOLUTE_PATTERN.findall(resolved.read_text(encoding="utf-8-sig", errors="replace")))
            if count:
                audit.append({"asset": name, "machine_absolute_path_occurrences": count})
    validate_manifest(manifest)
    output = output.absolute()
    if output.exists():
        raise PackError("Output archive already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Copy to a temporary archive, then claim output exclusively; never overwrite an archive.
    with tempfile.TemporaryDirectory(prefix="platform-export-", dir=output.parent) as temporary:
        staged = Path(temporary) / "bundle.zip"
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("platform.json", json_bytes(manifest))
            archive.writestr(METADATA, json_bytes({"scope": "local package metadata only",
                "immutable_assets_with_historical_paths": audit,
                "note": "Asset bytes are unchanged. Historical paths are not runtime dependencies; resolve files through platform.json. Redistribution permission is not established."}))
            for path, name in assets:
                archive.write(path, name)
        # Read back before making this archive available to the user.
        inspect_archive(staged)
        with output.open("xb") as target, staged.open("rb") as incoming:
            shutil.copyfileobj(incoming, target)
    return {"status": "exported_and_verified", "id": platform_id, "asset_count": len(assets),
            "asset_bytes": sum(e["bytes"] for e in manifest["files"]), "archive_sha256": sha256(output),
            "redistribution_status": "unconfirmed"}


def inspect_archive(path: Path, extraction: Path | None = None) -> dict:
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_FILES:
            raise PackError("Archive has too many entries")
        names = {}
        total = 0
        for entry in entries:
            if entry.is_dir():
                raw_name = entry.filename[:-1]
            else:
                raw_name = entry.filename
            safe_relative(raw_name)
            mode = entry.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if file_type not in {0, stat.S_IFREG, stat.S_IFDIR} or stat.S_ISLNK(mode):
                raise PackError("Archive links and special files are forbidden")
            key = raw_name.casefold()
            if key in names:
                raise PackError("Duplicate archive entry")
            names[key] = entry
            if entry.flag_bits & 1:
                raise PackError("Encrypted entries are not supported")
            if entry.file_size > MAX_FILE_BYTES:
                raise PackError("Archive member exceeds size limit")
            total += entry.file_size
        if total > MAX_TOTAL_BYTES:
            raise PackError("Archive exceeds total size limit")
        manifest_entry = names.get("platform.json")
        if manifest_entry is None or manifest_entry.filename != "platform.json" or manifest_entry.file_size > MAX_MANIFEST_BYTES:
            raise PackError("Missing or excessive platform manifest")
        manifest = validate_manifest(load_json(archive.read(manifest_entry)))
        allowed = {"platform.json", METADATA, *(e["path"] for e in manifest["files"])}
        members = {e.filename: e for e in entries if not e.is_dir()}
        if set(members) - allowed or not {"platform.json", *(e["path"] for e in manifest["files"])} <= set(members):
            raise PackError("Archive assets differ from manifest")
        for record in manifest["files"]:
            entry = members[record["path"]]
            if entry.file_size != record["bytes"]:
                raise PackError("Asset declared size mismatch")
            digest = hashlib.sha256()
            size = 0
            destination = extraction.joinpath(*safe_relative(record["path"]).parts) if extraction else None
            if destination:
                destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as stream:
                target = destination.open("xb") if destination else None
                try:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        size += len(chunk)
                        if size > record["bytes"]:
                            raise PackError("Asset expanded beyond declared size")
                        digest.update(chunk)
                        if target:
                            target.write(chunk)
                finally:
                    if target:
                        target.close()
            if size != record["bytes"] or digest.hexdigest() != record["sha256"]:
                raise PackError("Asset SHA256 mismatch: " + record["path"])
        if extraction:
            (extraction / "platform.json").write_bytes(json_bytes(manifest))
            if METADATA in members:
                if members[METADATA].file_size > MAX_MANIFEST_BYTES:
                    raise PackError("Metadata exceeds size limit")
                metadata_file = extraction / METADATA
                metadata_file.parent.mkdir(parents=True, exist_ok=True)
                metadata_file.write_bytes(archive.read(METADATA))
        return manifest


def install_pack(archive: Path, destination: Path) -> dict:
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".platform-install-", dir=destination) as temporary:
        staging = Path(temporary) / "payload"
        staging.mkdir()
        manifest = inspect_archive(archive, staging)
        target = destination / manifest["id"]
        if target.exists() or target.is_symlink():
            raise PackError("Installed platform already exists; use a new version or destination")
        # Exclusive mkdir claims the final id without replacing an existing directory.
        target.mkdir()
        try:
            for child in staging.iterdir():
                shutil.move(str(child), str(target / child.name))
            for entry in manifest["files"]:
                installed = target.joinpath(*safe_relative(entry["path"]).parts)
                if installed.stat().st_size != entry["bytes"] or sha256(installed) != entry["sha256"]:
                    raise PackError("Installed asset readback failed")
        except Exception:
            shutil.rmtree(target)
            raise
    return {"status": "installed_and_verified", "id": manifest["id"],
            "asset_count": len(manifest["files"]), "asset_bytes": sum(e["bytes"] for e in manifest["files"]),
            "platform_manifest_sha256": sha256(target / "platform.json"),
            "redistribution_status": manifest.get("redistribution_status", "unconfirmed")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="Export only a platform manifest's verified assets")
    export.add_argument("--suite", type=Path, required=True)
    export.add_argument("--platform", required=True)
    export.add_argument("--output", type=Path, required=True)
    install = commands.add_parser("install", help="Install an archive into destination/platform-id")
    install.add_argument("--archive", type=Path, required=True)
    install.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = export_pack(args.suite, args.platform, args.output) if args.command == "export" else install_pack(args.archive, args.destination)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (PackError, OSError, KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError, zipfile.BadZipFile, RuntimeError) as error:
        # OS exceptions can contain personal paths; show class only for those errors.
        message = str(error) if isinstance(error, PackError) else type(error).__name__
        print(json.dumps({"status": "failed", "error": message}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
