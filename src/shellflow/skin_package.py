"""Portable, hash-bound full-robot skin package (.skin).

Validation is structural and deliberately makes no new manufacturing or
physical-dynamics claim. A trusted local profile additionally authenticates
the packaged baseline and restricts changes to its declared visual slot.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET

from .package_io import PackageError, file_records, json_object, parse_xml, safe_path, validate_files, write_archive
from .package_preview import add_preview, validate_preview
from .urdf import export_urdf


MANIFEST = 'skin-package.json'
SCHEMA = 'kk-skin-package/1'
SCHEMA_V2 = 'kk-skin-package/2'
SCHEMA_V3 = 'kk-skin-package/3'
HEX = re.compile(r'^[0-9a-f]{64}$')
IDENT = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PackageError(message)


def _json(data: bytes, name: str) -> dict:
    return json_object(data, name)


def _recorded_profile(path: Path) -> tuple[dict, bytes, bytes]:
    profile_bytes = path.read_bytes()
    profile = _json(profile_bytes, 'robot profile')
    _require(profile.get('schema_version') == 1
             and isinstance(profile.get('id'), str) and IDENT.fullmatch(profile['id'])
             and profile.get('mechanical_platform') == 'original-robot-v1',
             'Unsupported robot profile')
    baseline_name = safe_path(profile.get('baseline_mjcf'))
    baseline = (path.parent / baseline_name).read_bytes()
    records = {r['path']: r for r in profile.get('files', [])}
    _require(baseline_name in records, 'Robot profile does not inventory its baseline')
    rec = records[baseline_name]
    _require(rec.get('sha256') == _sha(baseline) and rec.get('bytes') == len(baseline),
             'Trusted baseline integrity failed')
    return profile, profile_bytes, baseline


def _model_path(platform: str, name: str) -> str:
    return f'assembled/{platform}/{name}'


def _allowed_model_file(name: str) -> bool:
    return (name in {'robot.urdf', 'robot.xml', 'scene.xml', 'simulation-report.json',
                     'README.md', 'preview-pose.json', 'preview.png'}
            or (name.startswith('meshes/') and
                Path(name).suffix.lower() in {'.stl', '.obj', '.png'}))


def _check_xml_safety(root: ET.Element, *, scene: bool = False) -> None:
    """Reject XML constructs that can load code or resources outside the package."""
    forbidden = {'extension', 'plugin', 'include', 'model', 'flexcomp', 'composite'}
    scene_tags = {'mujoco', 'include', 'visual', 'global', 'headlight', 'worldbody',
                  'geom', 'light', 'keyframe', 'key'}
    mesh_nodes = set(root.findall('asset/mesh')) if not scene else set()
    for node in root.iter():
        _require('}' not in node.tag and node.tag not in forbidden - ({'include'} if scene else set()),
                 'XML includes/plugins/extensions are unsupported')
        if scene:
            _require(node.tag in scene_tags, 'Scene contains unsupported model or extension element')
        _require(all('}' not in key and key != 'plugin' for key in node.attrib),
                 'XML plugin or namespaced attribute is unsupported')
        if 'file' in node.attrib:
            _require((node in mesh_nodes and not scene) or (scene and node.tag == 'include'
                     and node.get('file') == 'robot.xml'),
                     'XML external resource reference is unsupported')
    if not scene:
        compiler = root.find('compiler')
        meshdir = 'meshes/' if compiler is None else compiler.get('meshdir', 'meshes/')
        if compiler is not None:
            _require(not set(compiler.attrib) & {'assetdir', 'texturedir'},
                     'MJCF compiler external asset directories are unsupported')
        mesh_directory = safe_path(meshdir.rstrip('/'))
        _require(mesh_directory == 'meshes' or mesh_directory.startswith('meshes/'),
                 'MJCF mesh directory must be the packaged meshes directory')


def _canon(root: ET.Element) -> str:
    return ET.canonicalize(ET.tostring(root, encoding='unicode'), strip_text=True)


def _resource_paths(xml: ET.Element, urdf: ET.Element, scene: ET.Element) -> set[str]:
    compiler = xml.find('compiler')
    meshdir = 'meshes' if compiler is None else compiler.get('meshdir', 'meshes')
    paths = set()
    for mesh in xml.findall('asset/mesh'):
        name = mesh.get('file')
        _require(isinstance(name, str) and name, 'MJCF mesh has no file')
        paths.add(safe_path(f'{meshdir.rstrip("/")}/{name}'))
    for mesh in urdf.findall('.//geometry/mesh'):
        name = mesh.get('filename')
        _require(isinstance(name, str) and name, 'URDF mesh has no filename')
        paths.add(safe_path(name))
    includes = scene.findall('include')
    _require(len(includes) == 1 and includes[0].get('file') == 'robot.xml',
             'Scene must include exactly the packaged robot.xml')
    return paths


def _check_whole_robot(baseline: ET.Element, robot: ET.Element, urdf: ET.Element,
                       parent_link: str) -> dict:
    _require(baseline.tag == robot.tag == 'mujoco' and urdf.tag == 'robot',
             'Expected MJCF and URDF robot roots')
    expected_bodies = [x.get('name') for x in baseline.findall('.//body')]
    actual_bodies = [x.get('name') for x in robot.findall('.//body')]
    expected_links = set(expected_bodies) | {'world'}
    actual_links = [x.get('name') for x in urdf.findall('link')]
    _require(len(expected_bodies) >= 2 and len(set(expected_bodies)) == len(expected_bodies)
             and parent_link in expected_bodies and actual_bodies == expected_bodies,
             'Full-robot MJCF must retain every baseline body')
    _require(len(actual_links) == len(expected_links) and set(actual_links) == expected_links,
             'Full-robot URDF must retain every baseline link')
    expected_movable = {x.get('name') for x in baseline.findall('.//body/joint')
                        if x.get('type', 'hinge') in ('hinge', 'slide')}
    actual_movable = {x.get('name') for x in urdf.findall('joint')
                      if x.get('type') in ('revolute', 'continuous', 'prismatic')}
    _require(expected_movable and actual_movable == expected_movable,
             'Full-robot URDF must retain baseline movable joints')
    _require(len(urdf.findall('joint')) == len(expected_bodies),
             'URDF joint tree must connect every robot link')
    return {'scope': 'full_robot', 'robot_links': len(expected_bodies),
            'movable_joints': len(expected_movable), 'shell_parent_link': parent_link}


def _check_visual_overrides(declaration: object, baseline: ET.Element,
                            robot: ET.Element, *, parent_link: str,
                            schema: str, upper_slot: dict | None = None) -> None:
    _require(isinstance(declaration, list)
             and (len(declaration) == 1 if schema == SCHEMA_V2 else True),
             'Visual overrides must be an array (one lower shell color in /2)')
    seen = set()
    for override in declaration:
        _require(isinstance(override, dict) and set(override) == {'link', 'geom', 'rgba'}
                 and isinstance(override.get('link'), str)
                 and isinstance(override.get('geom'), str),
                 'Visual override must declare link, geom and rgba')
        link, geom = override['link'], override['geom']
        _require(schema != SCHEMA_V2 or (link, geom) == ('base_link', 'base_link_visual'),
                 'Visual override may target only base_link/base_link_visual in /2')
        split_lower = (isinstance(upper_slot, dict)
                       and upper_slot.get('mode') == 'split_base'
                       and geom == upper_slot.get('geom_name'))
        _require((link, geom) not in seen and (link != parent_link or split_lower),
                 'Visual override is duplicated or targets the upper shell')
        seen.add((link, geom))
        rgba = override['rgba']
        _require(isinstance(rgba, list) and len(rgba) == 4
                 and all(type(value) in (int, float) and math.isfinite(value)
                         and 0 <= value <= 1 for value in rgba)
                 and rgba[3] == 1,
                 'Visual override requires finite RGBA channels in [0, 1] and opaque alpha')
        source_bodies = [body for body in baseline.findall('.//body') if body.get('name') == link]
        result_bodies = [body for body in robot.findall('.//body') if body.get('name') == link]
        _require(len(source_bodies) == len(result_bodies) == 1,
                 'Visual override target link is missing or ambiguous')
        source_geoms = [item for item in source_bodies[0].findall('geom') if item.get('name') == geom]
        result_geoms = [item for item in result_bodies[0].findall('geom') if item.get('name') == geom]
        _require(len(source_geoms) == len(result_geoms) == 1,
                 'Visual override target geom is missing or ambiguous')
        source, result = source_geoms[0], result_geoms[0]
        _require(source.get('contype', '0') == '0'
                 and source.get('conaffinity', '0') == '0'
                 and (source.get('class') == 'visual'
                      or (source.get('contype') == '0'
                          and source.get('conaffinity') == '0')),
                 'Visual override target is not a visual geom')
        try:
            actual = [float(value) for value in result.get('rgba', '').split()]
        except ValueError as error:
            raise PackageError('Visual override MJCF color is invalid') from error
        _require(len(actual) == 4 and all(math.isfinite(value) for value in actual)
                 and actual == rgba, 'Visual override declaration differs from MJCF color')
        if 'rgba' in source.attrib:
            result.set('rgba', source.get('rgba'))
        else:
            result.attrib.pop('rgba', None)


def _check_visual_slot(baseline: ET.Element, robot: ET.Element, profile: dict,
                       model_files: dict[str, bytes], visual_overrides: object = None,
                       schema: str = SCHEMA) -> None:
    source = copy.deepcopy(baseline)
    changed = copy.deepcopy(robot)
    slot = profile.get('visual_replacement', {'mode': 'split_base'})
    if visual_overrides is not None:
        _check_visual_overrides(visual_overrides, source, changed,
                                parent_link=profile.get('parent_link'), schema=schema,
                                upper_slot={'mode': slot.get('mode'),
                                            'geom_name': slot.get('geom_name',
                                                                  profile.get('source_base_visual'))})
    mode = slot.get('mode')
    parent_name = profile.get('parent_link')
    old_name = slot.get('geom_name', profile.get('source_base_visual'))
    _require(mode in ('dedicated_link', 'split_base') and isinstance(old_name, str),
             'Unsupported visual replacement slot')
    source_parent = next((b for b in source.findall('.//body') if b.get('name') == parent_name), None)
    result_parent = next((b for b in changed.findall('.//body') if b.get('name') == parent_name), None)
    _require(source_parent is not None and result_parent is not None, 'Visual parent link is missing')
    source_visual = next((g for g in source_parent.findall('geom') if g.get('name') == old_name), None)
    result_visual = next((g for g in result_parent.findall('geom') if g.get('name') == old_name), None)
    _require(source_visual is not None and (source_visual.get('class') == 'visual'
             or (source_visual.get('contype', '1') == '0'
                 and source_visual.get('conaffinity', '1') == '0')),
             'Declared baseline slot is not a visual geom')
    generated = [g for g in result_parent.findall('geom')
                 if re.fullmatch(r'shellflow_upper_[0-9]+', g.get('name', ''))]
    _require(generated and len({g.get('name') for g in generated}) == len(generated),
             'No distinct replacement shell visuals')
    asset = changed.find('asset')
    _require(asset is not None, 'MJCF assets are missing')
    for geom in generated:
        name = geom.get('name')
        _require(geom.get('mesh') == name and geom.get('type') == 'mesh'
                 and geom.get('contype') == '0' and geom.get('conaffinity') == '0'
                 and (geom.get('density') == '0' or
                      (mode == 'split_base' and geom.get('density') is None))
                 and geom.get('group') == '2',
                 'Replacement geom changes collision or mass properties')
        mesh = next((m for m in asset.findall('mesh') if m.get('name') == name), None)
        _require(mesh is not None and mesh.get('file') == 'upper_shell_' + name.rsplit('_', 1)[1] + '.stl',
                 'Replacement mesh asset is missing or renamed')
        asset.remove(mesh)
        result_parent.remove(geom)
    if mode == 'dedicated_link':
        _require(result_visual is None, 'Original upper visual was not replaced')
        source_parent.remove(source_visual)
    else:
        _require(result_visual is not None and result_visual.get('mesh') == 'shellflow_lower',
                 'Legacy lower visual was not installed')
        result_visual.set('mesh', source_visual.get('mesh'))
        lower = next((m for m in asset.findall('mesh') if m.get('name') == 'shellflow_lower'), None)
        _require(lower is not None and lower.get('file') == Path(profile['lower_visual_mesh']).name,
                 'Legacy lower mesh reference is invalid')
        asset.remove(lower)
        lower_name = safe_path(profile['lower_visual_mesh'])
        rec = next((r for r in profile.get('files', []) if r.get('path') == lower_name), None)
        shipped = model_files.get('meshes/' + Path(lower_name).name)
        _require(rec is not None and shipped is not None and rec.get('sha256') == _sha(shipped),
                 'Legacy lower mesh differs from trusted source')
    _require(_canon(source) == _canon(changed),
             'MJCF changes undeclared joints, inertias, collisions, sensors, cameras or other baseline fields')


def _check_urdf_export(robot_bytes: bytes, urdf_bytes: bytes, profile: dict) -> None:
    with tempfile.TemporaryDirectory(prefix='shellflow-skin-') as temp:
        root = Path(temp)
        source, expected = root / 'robot.xml', root / 'robot.urdf'
        source.write_bytes(robot_bytes)
        try:
            export_urdf(source, expected,
                        default_velocity_limit=profile.get('robot_velocity_limit_fallback_rad_s', 100.0),
                        joint_metadata=profile.get('urdf_joint_metadata'),
                        joint_order=profile.get('source_joint_order'),
                        source_revision_comment=profile.get('source_revision_comment'))
        except (ValueError, KeyError) as exc:
            raise PackageError('Packaged MJCF cannot produce the declared full-robot URDF') from exc
        _require(_canon(parse_xml(expected.read_bytes())) == _canon(parse_xml(urdf_bytes)),
                 'URDF differs from the assembled robot conversion')


def validate(files: dict[str, bytes], *, platform_profile: Path | None = None,
             capabilities: set[str] | None = None) -> dict:
    """Validate package contents; a trusted profile pins all baseline assets."""
    _require(MANIFEST in files, 'Missing skin-package.json')
    manifest = _json(files[MANIFEST], MANIFEST)
    schema = manifest.get('schema')
    _require(schema in (SCHEMA, SCHEMA_V2, SCHEMA_V3), 'Unsupported skin package schema')
    required_fields = {'schema', 'id', 'title', 'version', 'author', 'license_id',
                               'platform', 'source', 'collision_policy',
                               'inertia_policy', 'physical_fit_tested',
                               'physical_dynamics_validated', 'files'}
    if schema in (SCHEMA_V2, SCHEMA_V3):
        required_fields.add('visual_overrides')
    if schema != SCHEMA_V3:
        required_fields.add('manufacturing')
    _require(set(manifest) == required_fields,
             'Unknown or missing skin manifest field')
    for key in ('id', 'version'):
        _require(isinstance(manifest.get(key), str) and IDENT.fullmatch(manifest[key]) is not None,
                 f'Invalid {key}')
    _require(isinstance(manifest.get('title'), str) and 0 < len(manifest['title'].strip()) <= 256,
             'Missing or oversized title')
    _require(isinstance(manifest.get('author'), str)
             and isinstance(manifest.get('license_id'), str),
             'Author and license identifiers must be text')
    platform = manifest.get('platform')
    _require(isinstance(platform, dict) and isinstance(platform.get('id'), str)
             and IDENT.fullmatch(platform['id']),
             'Unsupported robot platform')
    if capabilities is not None:
        _require(platform['id'] in capabilities, 'Robot platform capability is unavailable')
    pid = platform['id']
    _require(set(platform) == {'id', 'profile_sha256', 'baseline_sha256',
                               'mechanical_platform', 'mechanical_interface_sha256',
                               'parent_link', 'visual_replacement', 'cad_unit',
                               'simulation_unit', 'frame'},
             'Unknown or missing skin platform field')
    _require(all(isinstance(platform.get(k), str) and HEX.fullmatch(platform[k])
                 for k in ('profile_sha256', 'baseline_sha256', 'mechanical_interface_sha256')),
             'Invalid platform provenance hash')
    _require(platform.get('cad_unit') == 'millimeter' and platform.get('simulation_unit') == 'meter'
             and platform.get('frame') == 'original-robot-v1 CAD Z-up'
             and platform.get('mechanical_platform') == 'original-robot-v1',
             'Unsupported mechanical frame or units')
    _require(manifest.get('collision_policy') == 'baseline_preserved'
             and manifest.get('inertia_policy') == 'baseline_preserved'
             and manifest.get('physical_dynamics_validated') is False
             and manifest.get('physical_fit_tested') is False,
             'Skin package may not claim collision, inertia, dynamics or physical-fit certification')
    manufacturing = manifest.get('manufacturing')
    if schema != SCHEMA_V3:
        _require(isinstance(manufacturing, dict) and manufacturing.get('status') == 'source_provided_unverified'
                 and manufacturing.get('shell_path') == 'print/shell.stl',
                 'Manufacturing source status is invalid')
        _require(set(manufacturing) == {'status', 'shell_path', 'ams_path', 'preview_path'},
                 'Unknown or missing manufacturing field')
    validate_files(manifest, files, MANIFEST)
    if schema == SCHEMA_V3:
        validate_preview(manifest, files)
    _require(all(set(rec) == {'bytes', 'sha256'} for rec in manifest['files'].values()),
             'Unknown file hash record field')
    allowed_outer = {'preview/preview.png', 'provenance/profile.json',
                     'provenance/baseline.xml', MANIFEST}
    if schema != SCHEMA_V3:
        allowed_outer |= {'print/shell.stl', 'print/ams.3mf'}
    _require(all(name in allowed_outer or name.startswith(_model_path(pid, ''))
                 for name in files), 'Skin package contains an unsupported path')
    required = {_model_path(pid, x) for x in ('robot.urdf', 'robot.xml', 'scene.xml',
                                               'simulation-report.json')} | {
        'provenance/profile.json', 'provenance/baseline.xml'}
    if schema != SCHEMA_V3:
        required.add('print/shell.stl')
    _require(required <= files.keys(), 'Missing complete robot or provenance member')
    profile_bytes = files['provenance/profile.json']
    profile = _json(profile_bytes, 'packaged profile')
    baseline_bytes = files['provenance/baseline.xml']
    _require(_sha(profile_bytes) == platform['profile_sha256']
             and _sha(baseline_bytes) == platform['baseline_sha256']
             and profile.get('id') == pid and profile.get('parent_link') == platform.get('parent_link')
             and profile.get('visual_replacement', {'mode': 'split_base'}) == platform.get('visual_replacement')
             and profile.get('mechanical_platform') == platform.get('mechanical_platform')
             and profile.get('source_step_sha256') == platform['mechanical_interface_sha256'],
             'Packaged robot profile or mechanical interface mismatch')
    _require(profile.get('collision_policy', 'baseline_preserved') == 'baseline_preserved'
             and profile.get('inertia_policy', 'baseline_preserved') == 'baseline_preserved',
             'Robot profile uses unsupported physics policy')
    if platform_profile is not None:
        trusted, trusted_bytes, trusted_baseline = _recorded_profile(Path(platform_profile))
        _require(trusted_bytes == profile_bytes and trusted_baseline == baseline_bytes,
                 'Package differs from trusted robot profile or baseline')
        for rec in trusted['files']:
            name = safe_path(rec['path'])
            if name.startswith('meshes/'):
                shipped = files.get(_model_path(pid, name))
                _require(shipped is not None and _sha(shipped) == rec['sha256']
                         and len(shipped) == rec['bytes'],
                         'Packaged baseline mesh differs from trusted source: ' + name)
    report_bytes = files[_model_path(pid, 'simulation-report.json')]
    report = _json(report_bytes, 'simulation report')
    _require(('visual_overrides' in report) == (schema in (SCHEMA_V2, SCHEMA_V3)),
             'Simulation report visual override version mismatch')
    if schema in (SCHEMA_V2, SCHEMA_V3):
        _require(manifest['visual_overrides'] == report['visual_overrides'],
                 'Visual override declaration differs from simulation report')
    source = manifest.get('source')
    _require(isinstance(source, dict) and set(source) == {'shell_sha256', 'report_sha256',
                 'producer_code_sha256', 'omitted_source_files'},
             'Unknown or missing source provenance field')
    producer_hashes = source.get('producer_code_sha256')
    _require(isinstance(producer_hashes, dict) and producer_hashes
             and all(isinstance(name, str) and isinstance(digest, str)
                     and HEX.fullmatch(digest) for name, digest in producer_hashes.items()),
             'Invalid producer code hashes')
    _require(isinstance(source, dict) and isinstance(source.get('shell_sha256'), str)
             and HEX.fullmatch(source['shell_sha256'])
             and (schema == SCHEMA_V3 or source['shell_sha256'] == _sha(files['print/shell.stl']))
             and source.get('report_sha256') == _sha(report_bytes)
             and source.get('producer_code_sha256') == report.get('producer_code_sha256'),
             'Source or producer hash mismatch')
    omitted = source.get('omitted_source_files')
    _require(isinstance(omitted, list) and all(isinstance(x, str) for x in omitted)
             and len(omitted) == len(set(omitted))
             and set(omitted) <= {'preview.py'}, 'Invalid source-file omission declaration')
    _require(report.get('source_shell_sha256') == source['shell_sha256']
             and report.get('robot_profile_sha256') == platform['profile_sha256']
             and report.get('source_step_sha256') == platform['mechanical_interface_sha256']
             and report.get('source_baseline_mjcf_sha256') == platform['baseline_sha256']
             and report.get('robot_profile_id') == pid
             and report.get('transform_target_link') == profile.get('parent_link')
             and report.get('visual_replacement_mode') == profile.get('visual_replacement', {'mode': 'split_base'})['mode'],
             'Simulation report does not bind this source and platform')
    _require(report.get('collision_policy') == 'baseline_preserved'
             and report.get('inertia_policy') == 'baseline_preserved'
             and report.get('physical_fit_tested') is False
             and report.get('physical_dynamics_validated') is False,
             'Simulation report makes unsupported physics or fit claim')
    _require(report.get('passed') is True and report.get('source_shell_frame') ==
             'original-robot-v1 CAD millimeters Z-up',
             'Simulation report lacks successful CAD-frame export evidence')
    _require(report.get('transform') ==
             (profile.get('cad_mm_to_parent_m') or profile.get('cad_mm_to_base_m')),
             'Simulation report transform differs from robot profile')
    reported_whole = report.get('whole_robot')
    _require(isinstance(reported_whole, dict) and reported_whole.get('scope') == 'full_robot'
             and reported_whole.get('shell_parent_link') == profile.get('parent_link'),
             'Simulation report lacks full-robot provenance')
    model_files = {name.removeprefix(_model_path(pid, '')): data for name, data in files.items()
                   if name.startswith(_model_path(pid, ''))}
    _require(all(_allowed_model_file(name) for name in model_files),
             'Skin package contains an unsupported assembled file')
    missing_report_files = set()
    report_records = report.get('files')
    _require(isinstance(report_records, list) and report_records,
             'Simulation report has no source asset inventory')
    report_names = set()
    for rec in report_records:
        _require(isinstance(rec, dict), 'Invalid simulation source asset record')
        name = safe_path(rec['path'])
        _require(name not in report_names, 'Duplicate simulation source asset record')
        report_names.add(name)
        if name in omitted and name not in model_files:
            missing_report_files.add(name)
            continue
        _require(name in model_files and _sha(model_files[name]) == rec.get('sha256')
                 and len(model_files[name]) == rec.get('bytes'),
                 'Simulation report asset inventory mismatch: ' + name)
    _require(missing_report_files == set(omitted),
             'Source-file omission does not match simulation report inventory')
    _require(set(model_files) == report_names - set(omitted) | {'simulation-report.json'},
             'Packaged model files differ from simulation source inventory')
    baseline = parse_xml(baseline_bytes)
    robot_bytes = files[_model_path(pid, 'robot.xml')]
    urdf_bytes = files[_model_path(pid, 'robot.urdf')]
    robot, urdf = parse_xml(robot_bytes), parse_xml(urdf_bytes)
    scene = parse_xml(files[_model_path(pid, 'scene.xml')])
    _require(scene.tag == 'mujoco', 'Scene must be MuJoCo XML')
    _check_xml_safety(baseline)
    _check_xml_safety(robot)
    _check_xml_safety(scene, scene=True)
    whole = _check_whole_robot(baseline, robot, urdf, profile['parent_link'])
    _check_visual_slot(baseline, robot, profile, model_files,
                       manifest['visual_overrides'] if schema in (SCHEMA_V2, SCHEMA_V3) else None,
                       schema=schema)
    _check_urdf_export(robot_bytes, urdf_bytes, profile)
    referenced_resources = _resource_paths(robot, urdf, scene)
    for name in referenced_resources:
        _require(name in model_files, 'Missing referenced robot resource: ' + name)
    if schema == SCHEMA_V3:
        baseline_resources = set()
        for rec in profile.get('files', []):
            if not isinstance(rec, dict) or not isinstance(rec.get('path'), str):
                continue
            name = safe_path(rec['path'])
            if name.startswith('meshes/') and name in model_files:
                _require(rec.get('sha256') == _sha(model_files[name])
                         and rec.get('bytes') == len(model_files[name]),
                         'Packaged baseline display resource differs from profile: ' + name)
                baseline_resources.add(name)
        _require(all(not name.startswith('meshes/')
                     or name in referenced_resources | baseline_resources
                     for name in model_files),
                 'Unreferenced mesh or print asset is not allowed in display-only skin')
    _require(reported_whole.get('robot_links') == whole['robot_links']
             and reported_whole.get('movable_joints') == whole['movable_joints'],
             'Simulation report full-robot counts disagree with model')
    if schema != SCHEMA_V3:
        _require(manufacturing.get('ams_path') in (None, 'print/ams.3mf')
                 and ('print/ams.3mf' in files) == (manufacturing.get('ams_path') == 'print/ams.3mf'),
                 'AMS declaration mismatch')
        _require(manufacturing.get('preview_path') in (None, 'preview/preview.png')
                 and ('preview/preview.png' in files) == (manufacturing.get('preview_path') == 'preview/preview.png'),
                 'Preview declaration mismatch')
    return {'ok': True, 'schema': schema, 'platform_id': pid,
            'id': manifest['id'], 'whole_robot': whole,
            'trusted_platform_profile': platform_profile is not None,
            'physical_fit_tested': False, 'physical_dynamics_validated': False}


def export_skin(simulation: Path, profile: Path, shell: Path | None, output: Path, *,
                package_id: str, title: str, version: str = '1.0.0', author: str = '',
                license_id: str = '', ams: Path | None = None,
                preview: Path | None = None) -> dict:
    """Create a deterministic .skin from an existing assembled full robot."""
    from .english_metadata import require_english_text
    simulation, profile, output = map(Path, (simulation, profile, output))
    shell = Path(shell) if shell is not None else None
    _require(output.suffix.lower() == '.skin', 'Output must end in .skin')
    _require(not output.exists(), 'Output already exists')
    _require(bool(IDENT.fullmatch(package_id)) and bool(IDENT.fullmatch(version)),
             'Invalid package ID or version')
    _require(bool(title.strip()), 'Title is required')
    require_english_text(title, 'skin title')
    platform, profile_bytes, baseline_bytes = _recorded_profile(profile)
    pid = platform['id']
    files = {}
    omitted = []
    for path in sorted(simulation.rglob('*')):
        if path.is_file():
            _require(not path.is_symlink(), 'Simulation source may not contain file links')
            rel = safe_path(path.relative_to(simulation).as_posix())
            if rel == 'preview.py':
                omitted.append(rel)
            else:
                _require(_allowed_model_file(rel), 'Unsupported simulation asset: ' + rel)
                files[_model_path(pid, rel)] = path.read_bytes()
    files['provenance/profile.json'] = profile_bytes
    files['provenance/baseline.xml'] = baseline_bytes
    report_path = _model_path(pid, 'simulation-report.json')
    report = _json(files.get(report_path, b''), 'simulation report')
    source_shell_sha = report.get('source_shell_sha256')
    _require(isinstance(source_shell_sha, str) and HEX.fullmatch(source_shell_sha),
             'Simulation report has no valid source shell hash')
    if shell is not None:
        _require(_sha_file(shell) == source_shell_sha,
                 'Supplied shell differs from simulation report source')
    if 'visual_overrides' not in report:
        report['visual_overrides'] = []
        files[report_path] = (json.dumps(report, ensure_ascii=False, sort_keys=True,
                                        separators=(',', ':')) + '\n').encode('utf-8')
    schema = SCHEMA_V3
    manifest = {
        'schema': schema, 'id': package_id, 'title': title,
        'version': version, 'author': author, 'license_id': license_id,
        'platform': {'id': pid, 'profile_sha256': _sha(profile_bytes),
                     'baseline_sha256': _sha(baseline_bytes),
                     'mechanical_platform': platform.get('mechanical_platform'),
                     'mechanical_interface_sha256': platform.get('source_step_sha256'),
                     'parent_link': platform.get('parent_link'),
                     'visual_replacement': platform.get('visual_replacement', {'mode': 'split_base'}),
                     'cad_unit': 'millimeter', 'simulation_unit': 'meter',
                     'frame': 'original-robot-v1 CAD Z-up'},
        'source': {'shell_sha256': source_shell_sha,
                   'report_sha256': _sha(files[report_path]),
                   'producer_code_sha256': report.get('producer_code_sha256'),
                   'omitted_source_files': omitted},
        'collision_policy': 'baseline_preserved', 'inertia_policy': 'baseline_preserved',
        'physical_fit_tested': False, 'physical_dynamics_validated': False,
        'files': file_records(files),
    }
    manifest['visual_overrides'] = report['visual_overrides']
    if preview is not None:
        _require(Path(preview).suffix.lower() == '.png', 'Preview must be PNG')
        add_preview(manifest, files, Path(preview))
        manifest['files'] = file_records(files)
    files[MANIFEST] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                  separators=(',', ':')) + '\n').encode('utf-8')
    result = validate(files, platform_profile=profile)
    write_archive(output, files)
    return {**result, 'output': str(output), 'sha256': _sha_file(output),
            'files': len(files)}
