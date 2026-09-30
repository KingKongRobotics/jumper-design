from __future__ import annotations

import copy
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from shellflow.map_package import MAP_LIMITS, compose_default, export_map, validate
from shellflow.package_io import PackageError, file_records, read_archive


EXAMPLE = Path(__file__).resolve().parents[1] / "examples/maps/minimal.scene.json"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKIN = ROOT / "library/skins/jumper-original.skin"
PROFILE = ROOT / "robots/jumper/profile.json"


@pytest.fixture
def package(tmp_path):
    output = tmp_path / "minimal.map"
    summary = export_map(EXAMPLE, output, default_skin=DEFAULT_SKIN, profile=PROFILE)
    assert summary["ok"] is True and summary["schema"] == "kk-scene-package/2"
    files = read_archive(output, limits=MAP_LIMITS)
    return output, files, validate(files)


def _with_manifest(files: dict[str, bytes], manifest: dict) -> dict[str, bytes]:
    changed = dict(files)
    changed["scene-package.json"] = (json.dumps(manifest, ensure_ascii=False) + "\n").encode()
    return changed


def test_generates_real_map_with_world_and_repeatable_bytes(tmp_path, package):
    output, files, manifest = package
    assert output.suffix == ".map"
    assert manifest["schema"] == "kk-scene-package/2"
    assert manifest["robot"]["platformId"] == "jumper"
    assert "robot/assembled/jumper/robot.xml" in files
    assert "robot/assembled/jumper/robot.urdf" in files
    assert manifest["world"]["file"] == "scene.xml"
    assert manifest["world"]["attach"]["prefix"] == "scn_"
    assert "scene.xml" in files
    assert ET.fromstring(files["scene.xml"]).tag == "mujoco"
    second = export_map(EXAMPLE, tmp_path / "second.map",
                        default_skin=DEFAULT_SKIN, profile=PROFILE)
    assert second["id"] == manifest["id"]
    assert output.read_bytes() == (tmp_path / "second.map").read_bytes()


def test_generated_texture_is_packaged_and_loadable(tmp_path):
    spec = {"name": "textured", "ground": {"type": "plane", "size": [4, 4]},
            "materials": [{"name": "wood", "texture": {"generator": "wood_planks"}}],
            "objects": [{"name": "table", "shape": "box", "size": [0.4, 0.4, 0.1],
                         "pos": [0, 0, 0.4], "material": "wood"}]}
    source = tmp_path / "scene.json"
    source.write_text(json.dumps(spec), encoding="utf-8")
    output = tmp_path / "textured.map"
    export_map(source, output, default_skin=DEFAULT_SKIN, profile=PROFILE)
    files = read_archive(output, limits=MAP_LIMITS)
    manifest = validate(files)
    assert any(name.startswith("assets/") and name.endswith(".png")
               for name in manifest["files"])
    mujoco = pytest.importorskip("mujoco")
    model = mujoco.MjModel.from_xml_string(
        files["scene.xml"].decode(),
        {k: v for k, v in files.items() if not k.startswith("robot/")
         and k not in ("scene-package.json", "README.md")})
    assert model.ntex > 0
    combined, _, report = compose_default(files, profile=PROFILE)
    assert report["spawn_applied"] and combined.ntex >= model.ntex


def test_attached_heightfield_keeps_packaged_asset(package, tmp_path):
    mujoco = pytest.importorskip("mujoco")
    from mjscene.build.png import write_gray
    _, files, manifest = package
    terrain = tmp_path / "terrain.png"
    write_gray(terrain, [[0, 255], [255, 0]])
    root = ET.fromstring(files["scene.xml"])
    ET.SubElement(root.find("asset"), "hfield", name="terrain",
                  file="terrain.png", size="1 1 .1 .1")
    ET.SubElement(root.find("worldbody"), "geom", name="terrain_geom",
                  type="hfield", hfield="terrain", pos="10 10 0")
    changed = dict(files)
    changed["assets/terrain.png"] = terrain.read_bytes()
    changed["scene.xml"] = ET.tostring(root)
    updated = copy.deepcopy(manifest)
    updated["world"]["counts"]["geoms"] += 1
    updated["requiredCapabilities"] = list(set(updated.get("requiredCapabilities", [])) | {"hfield"})
    for name in ("scene.xml", "assets/terrain.png"):
        updated["files"][name] = file_records({name: changed[name]})[name]
    model, _, report = compose_default(_with_manifest(changed, updated), profile=PROFILE)
    assert model.nhfield == 1
    assert model.hfield_data.max() == pytest.approx(1)
    assert report["severe_spawn_contacts"] == 0


def test_tampered_or_missing_assets_are_rejected(package):
    _, files, manifest = package
    changed = dict(files)
    changed["scene.xml"] += b" "
    with pytest.raises(PackageError, match="SHA256"):
        validate(changed)

    xml = ET.fromstring(files["scene.xml"])
    asset = xml.find("asset")
    ET.SubElement(asset, "mesh", name="missing", file="absent.obj")
    changed = dict(files)
    changed["scene.xml"] = ET.tostring(xml)
    new_manifest = copy.deepcopy(manifest)
    new_manifest["files"] = file_records({k: v for k, v in changed.items()
                                           if k not in ("scene-package.json", "README.md")})
    new_manifest["world"]["counts"]["meshes"] += 1
    with pytest.raises(PackageError, match="missing resource"):
        validate(_with_manifest(changed, new_manifest))


def test_rejects_forbidden_mjcf_even_with_valid_hashes(package):
    _, files, manifest = package
    root = ET.fromstring(files["scene.xml"])
    ET.SubElement(root, "include", file="other.xml")
    changed = dict(files)
    changed["scene.xml"] = ET.tostring(root)
    new_manifest = copy.deepcopy(manifest)
    new_manifest["files"]["scene.xml"] = file_records({"scene.xml": changed["scene.xml"]})["scene.xml"]
    with pytest.raises(PackageError, match="forbidden <include>"):
        validate(_with_manifest(changed, new_manifest))

    child = b'<mujoco model="child"><option timestep="0.001"/><worldbody/></mujoco>'
    root = ET.fromstring(files["scene.xml"])
    ET.SubElement(root.find("asset"), "model", name="child", file="assets/child.mjcf")
    changed = dict(files)
    changed["scene.xml"] = ET.tostring(root)
    changed["assets/child.mjcf"] = child
    new_manifest = copy.deepcopy(manifest)
    new_manifest["files"] = file_records({k: v for k, v in changed.items()
                                           if k not in ("scene-package.json", "README.md")})
    with pytest.raises(PackageError, match="forbidden <option>"):
        validate(_with_manifest(changed, new_manifest))


def test_consumer_capabilities_reject_flex_and_hfield(package):
    _, files, manifest = package
    flex = copy.deepcopy(manifest)
    flex["flex"] = [{"id": "cloth"}]
    root = ET.fromstring(files["scene.xml"])
    ET.SubElement(root.find("worldbody"), "flexcomp", name="cloth")
    flex_files = dict(files)
    flex_files["scene.xml"] = ET.tostring(root)
    flex["files"]["scene.xml"] = file_records({"scene.xml": flex_files["scene.xml"]})["scene.xml"]
    with pytest.raises(PackageError, match="flex"):
        validate(_with_manifest(flex_files, flex), capabilities={"hfield", "jumper"})
    assert validate(_with_manifest(flex_files, flex), capabilities={"flex", "jumper"})["flex"]

    root = ET.fromstring(files["scene.xml"])
    ET.SubElement(root.find("asset"), "hfield", name="terrain", nrow="2", ncol="2", size="1 1 1 0.1")
    changed = dict(files)
    changed["scene.xml"] = ET.tostring(root)
    hfield = copy.deepcopy(manifest)
    hfield["files"]["scene.xml"] = file_records({"scene.xml": changed["scene.xml"]})["scene.xml"]
    with pytest.raises(PackageError, match="hfield"):
        validate(_with_manifest(changed, hfield), capabilities={"jumper"})


def test_independent_prop_model_and_legacy_archive_bytes(package, tmp_path):
    _, files, manifest = package
    prop_xml = b'<mujoco model="tool"><worldbody><body name="tool"><freejoint/><geom name="tool_geom" type="box" size="0.1 0.1 0.1"/></body></worldbody></mujoco>'
    changed = dict(files)
    changed["props/tool.xml"] = prop_xml
    independent = copy.deepcopy(manifest)
    independent["props"].append({"name": "tool", "file": "props/tool.xml",
                                 "initPositionRelativeToRobot": [0.1, 0.0, 0.0]})
    independent["files"]["props/tool.xml"] = file_records({"props/tool.xml": prop_xml})["props/tool.xml"]
    assert len(validate(_with_manifest(changed, independent))["props"]) >= 1

    from mjscene import build
    from mjscene.export import scene_package
    scene = tmp_path / "legacy"
    spec = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    build.compile_scene(spec, scene / "build", EXAMPLE.parent)
    legacy = scene_package.export(scene, scene / "export", legacy_zip=True)
    assert legacy.archive.name.endswith(".scene.zip")
    assert validate(read_archive(legacy.archive, limits=MAP_LIMITS))["schema"] == "kk-scene-package/1"


def test_rejects_nonfinite_spawn_and_unknown_required_feature(package):
    _, files, manifest = package
    bad = copy.deepcopy(manifest)
    bad["spawn"] = {"position": [0, 0, 0], "yaw": float("inf")}
    with pytest.raises(PackageError, match="Non-finite|finite"):
        validate(_with_manifest(files, bad))
    feature = copy.deepcopy(manifest)
    feature["requiredCapabilities"] = ["future-feature"]
    with pytest.raises(PackageError, match="future-feature"):
        validate(_with_manifest(files, feature), capabilities=set())


def test_v2_rejects_missing_or_substituted_robot(package):
    _, files, manifest = package
    without = {name: data for name, data in files.items() if not name.startswith("robot/")}
    stripped = copy.deepcopy(manifest)
    stripped["files"] = {name: rec for name, rec in stripped["files"].items()
                         if not name.startswith("robot/")}
    with pytest.raises(PackageError, match="no bundled robot"):
        validate(_with_manifest(without, stripped))

    mismatched = copy.deepcopy(manifest)
    mismatched["robot"]["profileSha256"] = "0" * 64
    with pytest.raises(PackageError, match="binding differs"):
        validate(_with_manifest(files, mismatched))

    with pytest.raises(PackageError, match="robot platform"):
        validate(files, capabilities={"rigid"})


def test_v2_default_robot_compiles_with_spawn_and_pose(package):
    pytest.importorskip("mujoco")
    _, files, manifest = package
    model, data, report = compose_default(files, profile=PROFILE)
    assert report["passed"] and report["spawn_applied"]
    assert report["robot_joints"] >= 23
    assert model.ngeom > 1
    free = model.joint("floating_base")
    assert data.qpos[int(free.qposadr[0]) + 2] >= manifest["spawn"]["position"][2]


def test_v2_rejects_robot_buried_in_static_obstacle(package):
    pytest.importorskip("mujoco")
    _, files, manifest = package
    scene = ET.fromstring(files["scene.xml"])
    ET.SubElement(scene.find("worldbody"), "geom", name="blocking_counter",
                  type="box", size="0.3 0.3 0.3", pos="0 0 0.15")
    changed = dict(files)
    changed["scene.xml"] = ET.tostring(scene)
    bad = copy.deepcopy(manifest)
    bad["world"]["counts"]["geoms"] += 1
    bad["files"]["scene.xml"] = file_records({"scene.xml": changed["scene.xml"]})["scene.xml"]
    with pytest.raises(PackageError, match="spawn penetrates environment"):
        compose_default(_with_manifest(changed, bad), profile=PROFILE)


def test_map_world_attaches_without_changing_host_joint_limits(package):
    mujoco = pytest.importorskip("mujoco")
    _, files, manifest = package
    host = '''<mujoco model="host"><compiler angle="radian" autolimits="true"/>
    <option timestep="0.005"/><default><geom condim="3"/></default>
    <asset><model name="scene" file="scene.xml"/></asset><worldbody>
    <body name="robot"><joint name="hip" type="hinge" range="-1.57 1.57"/>
    <geom name="robot_geom" type="box" size=".1 .1 .1" density="1000"/></body>
    <attach model="scene" prefix="scn_"/></worldbody></mujoco>'''
    model = mujoco.MjModel.from_xml_string(
        host, {k: v for k, v in files.items() if not k.startswith("robot/")
               and k not in ("scene-package.json", "README.md")})
    assert model.ngeom > 1
    assert list(model.jnt_range[0]) == pytest.approx([-1.57, 1.57])
    assert model.opt.timestep == 0.005
    assert manifest["world"]["attach"]["prefix"] == "scn_"


def test_direct_mjscene_export_validates_before_writing_map(tmp_path):
    from mjscene import build
    from mjscene.export import scene_package

    spec = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    spec["raw_mjcf"] = '<include file="missing.xml"/>'
    scene = tmp_path / "unsafe"
    build.compile_scene(spec, scene / "build", EXAMPLE.parent)
    with pytest.raises(PackageError, match="forbidden <include>"):
        scene_package.export(scene, scene / "export")
    assert not list(scene.rglob("*.map"))


def test_mjscene_cli_package_target_writes_map(tmp_path, capsys):
    from mjscene import build
    from mjscene.cli.app import main

    scene = tmp_path / "cli_scene"
    scene.mkdir()
    spec = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    (scene / "scene.json").write_text(json.dumps(spec), encoding="utf-8")
    build.compile_scene(spec, scene / "build", scene)
    assert main(["export", str(scene), "--target", "package"]) == 0
    capsys.readouterr()
    output = scene / "export" / "package" / "minimal.map"
    assert validate(read_archive(output, limits=MAP_LIMITS))["id"] == "minimal"


def test_export_rejects_visual_road_without_matching_support(tmp_path, package):
    from shellflow.map_package import export_environment
    _, files, manifest = package
    environment = {n: b for n, b in files.items() if not n.startswith("robot/")}
    scene = ET.fromstring(environment["scene.xml"])
    ET.SubElement(scene.find("worldbody"), "geom", name="raised_visual_road",
                  type="box", size="1 1 .01", pos="0 0 .1018",
                  contype="0", conaffinity="0")
    environment["scene.xml"] = ET.tostring(scene)
    legacy = copy.deepcopy(manifest)
    legacy["schema"] = "kk-scene-package/1"
    legacy.pop("robot")
    legacy["world"]["counts"]["geoms"] += 1
    legacy["world"].setdefault("decorativeGeoms", []).append("raised_visual_road")
    legacy["files"] = file_records({n: b for n,b in environment.items()
                                   if n not in ("scene-package.json", "README.md", "LICENSE")})
    environment = _with_manifest(environment, legacy)
    output = tmp_path / "must-not-exist.map"
    with pytest.raises(PackageError, match="visual/collision surface mismatch"):
        export_environment(environment, output, DEFAULT_SKIN, PROFILE)
    assert not output.exists()
