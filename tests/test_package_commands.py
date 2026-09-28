"""Public interchange path, including legacy scene archive compatibility."""
import contextlib
import io
import json
from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from shellflow import cli
from shellflow.map_package import export_map
from shellflow.package_io import PackageError, read_archive, write_archive
from shellflow.packages import import_package, repack_package, verify_package
from test_package_preview import png

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKIN = ROOT / "library/skins/jumper-original.skin"
PROFILE = ROOT / "robots/jumper/profile.json"


def test_export_map_cli_embeds_preview(tmp_path):
    preview = tmp_path / "thumbnail.png"
    preview.write_bytes(png())
    archive = tmp_path / "thumbnail.map"
    code, result = invoke("export-map", ROOT / "examples/maps/minimal.scene.json",
                          "--output", archive, "--default-skin", DEFAULT_SKIN,
                          "--profile", PROFILE, "--preview", preview)
    assert code == 0, result
    files = read_archive(archive)
    manifest = json.loads(files["scene-package.json"])
    assert "preview" not in manifest
    assert files["preview/preview.png"] == png()
    assert manifest["files"]["preview/preview.png"]["bytes"] == len(png())
    assert verify_package(archive, platform_profile=PROFILE)["schema"] == "kk-scene-package/2"


def invoke(*args):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = cli.main([str(a) for a in args])
    return code, json.loads(output.getvalue())


def test_public_map_generation_import_and_repack(tmp_path):
    archive = tmp_path / "obstacles.map"
    code, result = invoke("export-map", ROOT / "examples/maps/obstacle-course.scene.json", "--output", archive)
    assert code == 0, result
    assert result["ok"] is True
    assert result["robot"]["platformId"] == "jumper"
    code, result = invoke("verify-package", archive)
    assert code == 0 and result["kind"] == "map"
    original = read_archive(archive)
    assert verify_package(archive, platform_profile=PROFILE)["schema"] == "kk-scene-package/2"
    from mjscene import build
    from mjscene.export import scene_package
    scene_dir = tmp_path / "legacy-scene"
    scene_spec = json.loads((ROOT / "examples/maps/obstacle-course.scene.json").read_text(encoding="utf-8"))
    build.compile_scene(scene_spec, scene_dir / "build", ROOT / "examples/maps")
    source = scene_package.export(scene_dir, scene_dir / "export", legacy_zip=True)
    legacy = tmp_path / "old.scene.zip"
    legacy.write_bytes(source.archive.read_bytes())
    assert verify_package(legacy)["id"] == "obstacle-course"
    legacy_files = read_archive(legacy)
    imported = tmp_path / "imported"
    import_package(legacy, imported, capabilities=set())
    assert {p.relative_to(imported).as_posix(): p.read_bytes()
            for p in imported.rglob("*") if p.is_file()} == legacy_files
    repacked = tmp_path / "returned.map"
    repack_package(legacy, repacked, capabilities=set())
    assert read_archive(repacked) == legacy_files
    before = (imported / "scene.xml").read_bytes()
    with pytest.raises(FileExistsError):
        import_package(archive, imported)
    assert (imported / "scene.xml").read_bytes() == before


def test_public_import_refuses_mismatched_extension_and_corruption(tmp_path):
    archive = tmp_path / "flat.map"
    export_map(ROOT / "examples/maps/minimal.scene.json", archive,
               default_skin=DEFAULT_SKIN, profile=PROFILE)
    wrong = tmp_path / "flat.skin"
    wrong.write_bytes(archive.read_bytes())
    with pytest.raises(PackageError, match="Extension"):
        verify_package(wrong)
    files = read_archive(archive)
    files["scene.xml"] += b"tamper"
    invalid = tmp_path / "corrupted.map"
    write_archive(invalid, files)
    destination = tmp_path / "not-created"
    code, result = invoke("import-package", invalid, "--destination", destination)
    assert code != 0 and result["ok"] is False
    assert not destination.exists()


def test_map_manifest_matches_published_schema(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    archive = tmp_path / "map.map"
    export_map(ROOT / "examples/maps/obstacle-course.scene.json", archive,
               default_skin=DEFAULT_SKIN, profile=PROFILE)
    manifest = json.loads(read_archive(archive)["scene-package.json"])
    schema = json.loads((ROOT / "schemas/map-package-v2.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(manifest, schema)


def test_native_map_attach_preserves_host_settings(tmp_path):
    mujoco = pytest.importorskip("mujoco")
    archive = tmp_path / "course.map"
    export_map(ROOT / "examples/maps/obstacle-course.scene.json", archive,
               default_skin=DEFAULT_SKIN, profile=PROFILE)
    result = verify_package(archive, platform_profile=PROFILE, mujoco=True)
    assert result["native_mujoco"]["passed"] is True
    files = read_archive(archive)
    host = '<mujoco><compiler angle="radian"/><option timestep="0.007"/><worldbody><body name="robot"><joint name="hinge" range="-1.1 1.1"/><geom type="sphere" size="0.1" mass="2"/></body></worldbody></mujoco>'
    base = mujoco.MjModel.from_xml_string(host)
    attached = host.replace('</mujoco>', '<asset><model name="map" file="scene.xml"/></asset><worldbody><attach model="map" prefix="scn_"/></worldbody></mujoco>')
    model = mujoco.MjModel.from_xml_string(
        attached, assets={name: data for name, data in files.items()
                          if not name.startswith("robot/")})
    assert model.opt.timestep == base.opt.timestep
    assert model.jnt_range[0].tolist() == base.jnt_range[0].tolist()
    assert model.body_mass[1] == base.body_mass[1]
    assert model.ngeom > base.ngeom
