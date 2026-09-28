"""Build review-only .skin/.map candidates for the corrected Jumper LM_J0 limit.

Skin thumbnails are rerendered from the corrected robot. Map environment
images and all mesh bytes remain unchanged. Library indexes are not published.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import uuid
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from shellflow.map_package import MAP_LIMITS, validate as validate_map
from shellflow.package_io import file_records, json_object, read_archive, write_archive
from shellflow.packages import verify_package
from shellflow.simulation import compare_compiled, load_mujoco, verify_whole_robot, write_xml
from shellflow.urdf import export_urdf, verify_urdf
from shellflow.defaults import default_skin_path
from export_skin_collection import render_views


REPO = Path(__file__).resolve().parents[1]
PLATFORM = 'jumper'
MODEL = f'assembled/{PLATFORM}/'
LM = 'LM_J0_joint'
OLD_LIMIT = (0.75, 1.0)
NEW_LIMIT = (-0.75, 1.0)
RAW_POSE = 0.0012


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    return sha(path.read_bytes())


def encoded(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(',', ':')) + '\n').encode('utf-8')


def next_patch(version: str) -> str:
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', version)
    require(match is not None, 'Expected a three-part package version')
    return f'{match[1]}.{match[2]}.{int(match[3]) + 1}'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def joint_limit(root: ET.Element) -> tuple[float, float]:
    joints = [joint for joint in root.findall('.//joint') if joint.get('name') == LM]
    require(len(joints) == 1, f'Expected one {LM} in robot model')
    return tuple(map(float, joints[0].get('range', '').split()))


def validate_profile(profile_path: Path) -> tuple[dict, bytes, bytes, dict]:
    profile_bytes = profile_path.read_bytes()
    profile = json_object(profile_bytes, 'trusted Jumper profile')
    require(profile.get('id') == PLATFORM, 'The target profile must be Jumper')
    baseline = (profile_path.parent / profile['baseline_mjcf']).read_bytes()
    require(joint_limit(ET.fromstring(baseline)) == NEW_LIMIT,
            'Target profile still has the old LM_J0 limit')
    pose = json_object((profile_path.parent / profile['preview_pose']).read_bytes(),
                       'target raw preview pose')
    require(pose['joints'][LM] == RAW_POSE and LM not in pose['corrections'],
            'Target preview must retain the raw LM_J0 value without a correction')
    return profile, profile_bytes, baseline, pose


def unpack_model(files: dict[str, bytes], directory: Path) -> None:
    directory.mkdir()
    for name, data in files.items():
        if name.startswith(MODEL):
            path = directory.joinpath(*name[len(MODEL):].split('/'))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)


def migrate_skin(source: Path, output: Path, profile_path: Path,
                 target: tuple[dict, bytes, bytes, dict], work: Path,
                 preview_dir: Path) -> dict:
    profile, profile_bytes, baseline_bytes, target_pose = target
    source_hash = file_sha(source)
    files = read_archive(source)
    manifest = json_object(files['skin-package.json'], 'source skin manifest')
    require(manifest['schema'] == 'kk-skin-package/3' and
            manifest['platform']['id'] == PLATFORM, 'Expected a Jumper .skin/3')
    # The source is self-authenticating; its old profile is no longer trusted
    # after robots/jumper has been rebuilt against the corrected source.
    verify_package(source, mujoco=True)
    old_profile = json_object(files['provenance/profile.json'], 'old skin profile')
    old_baseline = ET.fromstring(files['provenance/baseline.xml'])
    require(joint_limit(old_baseline) == OLD_LIMIT, 'Source skin is not the old mechanical revision')
    require(old_profile['source_step_sha256'] == profile['source_step_sha256'] and
            old_profile['parent_link'] == profile['parent_link'] and
            old_profile['visual_replacement'] == profile['visual_replacement'],
            'Mechanical interface or replacement slot changed')
    old_metadata = copy.deepcopy(old_profile['urdf_joint_metadata'])
    lm_metadata = [entry for entry in old_metadata.values() if entry['name'] == LM]
    require(len(lm_metadata) == 1 and float(lm_metadata[0]['lower']) == OLD_LIMIT[0],
            'Old profile does not carry the known LM_J0 typo')
    lm_metadata[0]['lower'] = profile['urdf_joint_metadata'][
        next(link for link, entry in profile['urdf_joint_metadata'].items()
             if entry['name'] == LM)]['lower']
    require(old_metadata == profile['urdf_joint_metadata'],
            'Target profile changes another source joint parameter')
    repaired_baseline = copy.deepcopy(old_baseline)
    next(j for j in repaired_baseline.findall('.//joint') if j.get('name') == LM).set(
        'range', '-0.75 1')
    require(ET.canonicalize(ET.tostring(repaired_baseline, encoding='unicode'), strip_text=True)
            == ET.canonicalize(baseline_bytes.decode('utf-8'), strip_text=True),
            'Target baseline changes more than LM_J0 range')
    old_pose = json_object(files[MODEL + 'preview-pose.json'], 'old preview pose')
    require(old_pose['joints'][LM] == OLD_LIMIT[0] and
            old_pose['corrections'][LM]['source_position_rad'] == RAW_POSE,
            'Source skin lacks the audited raw LM_J0 pose')
    require({name: value for name, value in old_pose['joints'].items() if name != LM} ==
            {name: value for name, value in target_pose['joints'].items() if name != LM},
            'Target preview changes another joint')
    require(old_pose['source_legacy_pose_sha256'] == target_pose['source_legacy_pose_sha256'],
            'Target preview does not descend from the same legacy pose')

    robot_root = ET.fromstring(files[MODEL + 'robot.xml'])
    require(joint_limit(robot_root) == OLD_LIMIT, 'Source robot.xml lacks the old LM_J0 limit')
    robot_joint = next(j for j in robot_root.findall('.//joint') if j.get('name') == LM)
    robot_joint.set('range', '-0.75 1')
    model_dir = work / 'model'
    unpack_model(files, model_dir)
    write_xml(model_dir / 'robot.xml', robot_root)
    files[MODEL + 'robot.xml'] = (model_dir / 'robot.xml').read_bytes()
    files[MODEL + 'preview-pose.json'] = encoded(target_pose)

    urdf_path = model_dir / 'robot.urdf'
    urdf_path.unlink()
    conversion = export_urdf(
        model_dir / 'robot.xml', urdf_path,
        default_velocity_limit=profile.get('robot_velocity_limit_fallback_rad_s', 100.0),
        joint_metadata=profile.get('urdf_joint_metadata'),
        joint_order=profile.get('source_joint_order'),
        source_revision_comment=profile.get('source_revision_comment'))
    verification = verify_urdf(model_dir / 'robot.xml', urdf_path)
    require(verification['passed'], 'URDF verification failed: ' +
            json.dumps(verification['failures']))
    whole = verify_whole_robot(profile_path.parent / profile['baseline_mjcf'],
                               urdf_path, profile['parent_link'])
    native = compare_compiled(profile_path.parent / profile['baseline_mjcf'],
                              model_dir / 'robot.xml')
    imported = load_mujoco(urdf_path)
    files[MODEL + 'robot.urdf'] = urdf_path.read_bytes()

    scene = ET.fromstring(files[MODEL + 'scene.xml'])
    keys = scene.findall("keyframe/key[@name='display_home']")
    require(len(keys) == 1, 'Expected one display_home keyframe')
    qpos = [float(v) for v in keys[0].get('qpos', '').split()]
    robot_model = load_mujoco(model_dir / 'robot.xml')
    address = int(robot_model.joint(LM).qposadr[0])
    require(len(qpos) == robot_model.nq and qpos[address] == OLD_LIMIT[0],
            'Source display_home does not use the old LM_J0 value')
    qpos[address] = RAW_POSE
    keys[0].set('qpos', ' '.join(map(str, qpos)))
    write_xml(model_dir / 'scene.xml', scene)
    load_mujoco(model_dir / 'scene.xml')
    files[MODEL + 'scene.xml'] = (model_dir / 'scene.xml').read_bytes()
    render_views(model_dir, preview_dir)
    thumbnail = (preview_dir / 'three-quarter.png').read_bytes()
    files['preview/preview.png'] = thumbnail
    if MODEL + 'preview.png' in files:
        files[MODEL + 'preview.png'] = thumbnail

    report_name = MODEL + 'simulation-report.json'
    report = json_object(files[report_name], 'source simulation report')
    require(report['preview_pose']['joints'][LM] == OLD_LIMIT[0],
            'Source report does not match the old preview pose')
    report['robot_profile_sha256'] = sha(profile_bytes)
    report['robot_profile_id'] = profile['id']
    report['robot_source'] = profile.get('source')
    report['source_baseline_mjcf_sha256'] = sha(baseline_bytes)
    report['transform'] = profile.get('cad_mm_to_parent_m') or profile.get('cad_mm_to_base_m')
    report['urdf_conversion'] = conversion
    report['urdf_verification'] = verification
    report['whole_robot'] = whole
    report['native_mujoco'] = native
    report['urdf_load'] = {'passed': True, 'nq': imported.nq,
                           'nv': imported.nv, 'joints': imported.njnt}
    report['preview_pose'] = target_pose
    report['joint_limit_migration'] = {
        'source_package_sha256': source_hash,
        'source_profile_sha256': manifest['platform']['profile_sha256'],
        'target_profile_sha256': sha(profile_bytes),
        'joint': LM, 'old_limit_rad': list(OLD_LIMIT),
        'new_limit_rad': list(NEW_LIMIT),
        'legacy_source_pose_rad': RAW_POSE,
        'corrected_display_pose_rad': RAW_POSE,
        'scope': 'joint limit and static display pose; all mesh bytes retained',
        'physical_fit_tested': False, 'physical_dynamics_validated': False}
    report['producer_code_sha256'] = {
        **report['producer_code_sha256'], Path(__file__).name: file_sha(Path(__file__))}
    records = {item['path']: item for item in report['files']}
    for name in ('robot.xml', 'robot.urdf', 'scene.xml', 'preview-pose.json', 'preview.png'):
        if MODEL + name not in files:
            continue
        data = files[MODEL + name]
        require(name in records, 'Simulation report omits ' + name)
        records[name].update(bytes=len(data), sha256=sha(data))
    files[report_name] = encoded(report)
    files['provenance/profile.json'] = profile_bytes
    files['provenance/baseline.xml'] = baseline_bytes
    manifest['platform']['profile_sha256'] = sha(profile_bytes)
    manifest['platform']['baseline_sha256'] = sha(baseline_bytes)
    manifest['version'] = next_patch(manifest['version'])
    manifest['source']['report_sha256'] = sha(files[report_name])
    manifest['source']['producer_code_sha256'] = report['producer_code_sha256']
    manifest['files'] = file_records({name: data for name, data in files.items()
                                      if name != 'skin-package.json'})
    files['skin-package.json'] = encoded(manifest)

    original_meshes = {name: data for name, data in read_archive(source).items()
                       if '/meshes/' in name}
    require(all(files[name] == data for name, data in original_meshes.items()),
            'Migration changed a source mesh byte')
    write_archive(output, files)
    verify_package(output, platform_profile=profile_path, mujoco=True)
    require(file_sha(source) == source_hash, 'Source skin changed during migration')
    return {'name': source.name, 'source_sha256': source_hash,
            'candidate_sha256': file_sha(output), 'mesh_files_preserved': len(original_meshes),
            'preview': 'previews/' + source.stem + '/three-quarter.png'}


def migrate_map(source: Path, output: Path, default_skin: dict[str, bytes],
                default_manifest: dict, profile_path: Path) -> dict:
    source_hash = file_sha(source)
    files = read_archive(source, limits=MAP_LIMITS)
    manifest = validate_map(files)
    require(manifest['schema'] == 'kk-scene-package/2', 'Expected a .map/2')
    environment = {name: data for name, data in files.items()
                   if not name.startswith('robot/') and name != 'scene-package.json'}
    files = dict(environment)
    files.update({'robot/' + name: data for name, data in default_skin.items()})
    manifest = copy.deepcopy(manifest)
    manifest['robot'] = {
        'skinRoot': 'robot', 'skinId': default_manifest['id'],
        'platformId': PLATFORM,
        'profileSha256': default_manifest['platform']['profile_sha256']}
    manifest['version'] = next_patch(manifest['version'])
    manifest['files'] = file_records({name: data for name, data in files.items()
                                      if name not in ('README.md', 'LICENSE') or
                                      name in manifest['files']})
    files['scene-package.json'] = encoded(manifest)
    validate_map(files, platform_profile=profile_path)
    write_archive(output, files, limits=MAP_LIMITS)
    verify_package(output, platform_profile=profile_path, mujoco=True)
    roundtrip = read_archive(output, limits=MAP_LIMITS)
    require(all(roundtrip[name] == data for name, data in environment.items()),
            'Map environment bytes changed')
    require(file_sha(source) == source_hash, 'Source map changed during migration')
    return {'name': source.name, 'source_sha256': source_hash,
            'candidate_sha256': file_sha(output),
            'environment_files_preserved': len(environment)}


def migrate(skins_dir: Path, maps_dir: Path, profile_path: Path,
            default_skin_name: str, output: Path) -> dict:
    skins_dir, maps_dir, profile_path, output = map(
        lambda p: Path(p).resolve(), (skins_dir, maps_dir, profile_path, output))
    require(not output.exists(), 'Candidate output already exists')
    skin_sources = sorted(skins_dir.glob('*.skin'))
    map_sources = sorted(maps_dir.glob('*.map'))
    require(len(skin_sources) == 15 and len(map_sources) == 12,
            'Expected exactly 15 formal skins and 12 formal maps')
    require(default_skin_name in {p.name for p in skin_sources},
            'The selected default skin is missing from the formal library')
    target = validate_profile(profile_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = output.parent / ('.joint-limit-candidates-' + uuid.uuid4().hex)
    stage.mkdir()
    try:
        for name in ('skins', 'maps', 'work', 'previews'):
            (stage / name).mkdir()
        skin_results = []
        for index, source in enumerate(skin_sources):
            work = stage / 'work' / str(index)
            work.mkdir()
            skin_results.append(migrate_skin(source, stage / 'skins' / source.name,
                                             profile_path, target, work,
                                             stage / 'previews' / source.stem))
            shutil.rmtree(work)
        (stage / 'work').rmdir()
        default_files = read_archive(stage / 'skins' / default_skin_name)
        default_manifest = json_object(default_files['skin-package.json'],
                                       'candidate default skin')
        map_results = [migrate_map(source, stage / 'maps' / source.name,
                                   default_files, default_manifest, profile_path)
                       for source in map_sources]
        report = {'schema': 'joint-limit-candidate-migration/1',
                  'target_profile_sha256': file_sha(profile_path),
                  'default_skin': default_skin_name,
                  'skins': skin_results, 'maps': map_results,
                  'skin_thumbnails_refreshed': True,
                  'map_environment_thumbnails_preserved': True,
                  'library_indexes_updated': False,
                  'physical_fit_tested': False, 'physical_dynamics_validated': False}
        (stage / 'migration-report.json').write_bytes(encoded(report))
        require(not output.exists(), 'Candidate output appeared during migration')
        stage.rename(output)
        return report
    except BaseException:
        if stage.exists() and stage.parent.resolve() == output.parent and stage.name.startswith('.joint-limit-candidates-'):
            shutil.rmtree(stage)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skins-dir', type=Path, default=REPO / 'library/skins')
    parser.add_argument('--maps-dir', type=Path, default=REPO / 'library/maps')
    parser.add_argument('--profile', type=Path, default=REPO / 'robots/jumper/profile.json')
    parser.add_argument('--default-skin-name', default=default_skin_path(REPO).name,
                        help='Filename of the silver-armor skin in --skins-dir')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(migrate(args.skins_dir, args.maps_dir, args.profile,
                             args.default_skin_name, args.output), ensure_ascii=False,
                     indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
