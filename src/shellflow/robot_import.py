"""Import the user-maintained Jumper URDF as a lossless, versionless robot baseline.

The reference URDF and visual STL payloads are copied byte-for-byte. MJCF is a
native adapter with a free root; fixed link bodies and authored inertials stay
explicit. It does not invent sensors, actuators or contact approximations.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET

from .package_io import PackageError, parse_xml


SOURCE_FRAME = 'original-robot-v1 CAD millimeters Z-up'
REVISION = re.compile(rb'(?s)^\s*<\?xml[^>]*\?>\s*(<!--.*?-->)')
MESH_PREFIX = '../meshes/visual/'
EXPECTED_LINKS = 41
EXPECTED_JOINTS = 40
EXPECTED_MOVABLE = 22
CURRENT_LM_J0_LIMIT_RAD = (-0.75, 1.0)


def _fail(message: str) -> None:
    raise PackageError(message)


def _check(ok: bool, message: str) -> None:
    if not ok:
        _fail(message)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                    encoding='utf-8')


def _numbers(value: str | None, count: int, label: str) -> tuple[float, ...]:
    try:
        result = tuple(float(item) for item in value.split())
    except (ValueError, AttributeError) as exc:
        raise PackageError(f'Invalid {label}') from exc
    _check(len(result) == count and all(math.isfinite(v) for v in result), f'Invalid {label}')
    return result


def _origin(node: ET.Element | None, label: str) -> tuple[str, str]:
    _check(node is not None, f'Missing {label} origin')
    xyz = node.get('xyz', '0 0 0')
    rpy = node.get('rpy', '0 0 0')
    _numbers(xyz, 3, label + ' xyz')
    _numbers(rpy, 3, label + ' rpy')
    return xyz, rpy


def _quat(rpy: str) -> str:
    roll, pitch, yaw = _numbers(rpy, 3, 'RPY')
    cr, sr = math.cos(roll/2), math.sin(roll/2)
    cp, sp = math.cos(pitch/2), math.sin(pitch/2)
    cy, sy = math.cos(yaw/2), math.sin(yaw/2)
    values = (cr*cp*cy+sr*sp*sy, sr*cp*cy-cr*sp*sy,
              cr*sp*cy+sr*cp*sy, cr*cp*sy-sr*sp*cy)
    return ' '.join(format(v, '.17g') for v in values)


def _geometry(link: ET.Element, role: str) -> dict:
    nodes = link.findall(role)
    _check(len(nodes) == 1, f'Expected one {role} for {link.get("name")}')
    node = nodes[0]
    mesh = node.find('geometry/mesh')
    _check(mesh is not None and node.find('geometry') is not None
           and len(node.find('geometry')) == 1,
           f'Expected one mesh {role} for {link.get("name")}')
    filename = mesh.get('filename')
    _check(isinstance(filename, str) and filename.startswith(MESH_PREFIX)
           and filename.endswith('.stl') and '/' not in filename[len(MESH_PREFIX):]
           and '\\' not in filename and '..' not in filename[len(MESH_PREFIX):],
           f'Unsupported {role} mesh path for {link.get("name")}')
    scale = mesh.get('scale', '1 1 1')
    _check(min(_numbers(scale, 3, role + ' mesh scale')) > 0,
           f'Invalid {role} mesh scale')
    xyz, rpy = _origin(node.find('origin'), role)
    return {'file': filename[len(MESH_PREFIX):], 'scale': scale, 'xyz': xyz,
            'rpy': rpy, 'node': node}


def _inertial(link: ET.Element) -> dict:
    node = link.find('inertial')
    _check(node is not None, f'Missing inertial for {link.get("name")}')
    xyz, rpy = _origin(node.find('origin'), 'inertial')
    # The currently accepted Jumper reference has body-aligned inertial axes.
    # Reject any later rotated frame until the tensor rotation is implemented.
    _check(all(abs(v) < 1e-14 for v in _numbers(rpy, 3, 'inertial RPY')),
           'Rotated inertial frame needs an explicit tensor-frame adapter')
    mass = node.find('mass')
    tensor = node.find('inertia')
    _check(mass is not None and tensor is not None, 'Missing authored mass/inertia')
    mass_text = mass.get('value')
    _check(_numbers(mass_text, 1, 'mass')[0] > 0, 'Invalid mass')
    keys = ('ixx', 'iyy', 'izz', 'ixy', 'ixz', 'iyz')
    for key in keys:
        _numbers(tensor.get(key), 1, 'inertia ' + key)
    return {'xyz': xyz, 'rpy': rpy, 'mass': mass_text,
            'fullinertia': ' '.join(tensor.get(key) for key in keys),
            'tensor': {key: tensor.get(key) for key in keys}}


def convert_urdf(source_bytes: bytes) -> tuple[bytes, dict]:
    """Convert the strict shared-mesh Jumper URDF subset into native MJCF bytes."""
    source = parse_xml(source_bytes)
    _check(source.tag == 'robot' and source.get('name') == 'jumper',
           'Expected the Jumper whole-robot URDF')
    _check(all(child.tag in {'mujoco', 'link', 'joint'} for child in source),
           'Unsupported URDF extension or plugin')
    extension = source.find('mujoco/compiler')
    _check(extension is not None and extension.get('balanceinertia') == 'false'
           and extension.get('discardvisual') == 'false'
           and extension.get('strippath') == 'false',
           'Source compiler preservation settings differ from accepted reference')
    link_nodes = source.findall('link')
    joint_nodes = source.findall('joint')
    links = {link.get('name'): link for link in link_nodes}
    _check(len(links) == len(link_nodes) and all(links) and 'base_link' in links,
           'Duplicate, empty or missing robot link')
    joints = {}
    children: dict[str, list[tuple[str, ET.Element]]] = {name: [] for name in links}
    child_names = set()
    metadata = {}
    for node in joint_nodes:
        name, kind = node.get('name'), node.get('type')
        parent_node, child_node = node.find('parent'), node.find('child')
        _check(name and name not in joints and kind in {'fixed', 'revolute'}
               and parent_node is not None and child_node is not None,
               'Invalid or duplicate joint')
        parent, child = parent_node.get('link'), child_node.get('link')
        _check(parent in links and child in links and child != 'base_link'
               and child not in child_names, 'Joint tree is not a rooted robot tree')
        _origin(node.find('origin'), name)
        child_names.add(child)
        joints[name] = node
        children[parent].append((child, node))
        entry = {'name': name, 'type': kind}
        if kind == 'revolute':
            axis = node.find('axis')
            limit = node.find('limit')
            _check(axis is not None and limit is not None,
                   f'Missing axis or limit for {name}')
            _check(sum(v*v for v in _numbers(axis.get('xyz'), 3, name + ' axis')) > 0,
                   f'Invalid axis for {name}')
            lower = _numbers(limit.get('lower'), 1, name + ' lower')[0]
            upper = _numbers(limit.get('upper'), 1, name + ' upper')[0]
            effort = _numbers(limit.get('effort'), 1, name + ' effort')[0]
            velocity = _numbers(limit.get('velocity'), 1, name + ' velocity')[0]
            _check(lower < upper and effort > 0 and velocity > 0,
                   f'Invalid limits for {name}')
            entry.update(velocity=limit.get('velocity'), effort=limit.get('effort'),
                         lower=limit.get('lower'), upper=limit.get('upper'),
                         axis=axis.get('xyz'))
        metadata[child] = entry
    _check(child_names == set(links) - {'base_link'} and len(joints) == len(links)-1,
           'URDF is not a complete connected robot tree')
    geometry = {}
    inertials = {}
    for name, link in links.items():
        _check(set(child.tag for child in link) == {'inertial', 'visual', 'collision'},
               f'Unsupported element in link {name}')
        visual, collision = _geometry(link, 'visual'), _geometry(link, 'collision')
        _check(all(visual[key] == collision[key] for key in ('file', 'scale', 'xyz', 'rpy')),
               f'Visual/collision source geometry differs for {name}')
        _check(visual['file'] == name + '.stl', f'Unexpected source mesh name for {name}')
        rgba = visual['node'].find('material/color')
        _check(rgba is not None, f'Missing authored visual color for {name}')
        color = rgba.get('rgba')
        _numbers(color, 4, name + ' color')
        geometry[name] = {key: visual[key] for key in ('file', 'scale', 'xyz', 'rpy')}
        geometry[name]['color'] = color
        inertials[name] = _inertial(link)
    robot = ET.Element('mujoco', model='jumper')
    ET.SubElement(robot, 'compiler', angle='radian', meshdir='meshes/visual/',
                  balanceinertia='false', discardvisual='false', strippath='false',
                  fusestatic='false', autolimits='true')
    ET.SubElement(robot, 'size', nuser_jnt='2')
    asset = ET.SubElement(robot, 'asset')
    for name in links:
        item = geometry[name]
        ET.SubElement(asset, 'mesh', name=name, file=item['file'], scale=item['scale'])
    world = ET.SubElement(robot, 'worldbody')
    source_joint_order = list(joints)
    derived_joint_order = []
    visited = set()

    def body(name: str, parent: ET.Element, source_joint: ET.Element | None = None):
        _check(name not in visited, 'Cycle in URDF joint tree')
        visited.add(name)
        attrs = {'name': name}
        if source_joint is not None:
            xyz, rpy = _origin(source_joint.find('origin'), name)
            attrs.update(pos=xyz, quat=_quat(rpy))
            derived_joint_order.append(source_joint.get('name'))
        current = ET.SubElement(parent, 'body', **attrs)
        if source_joint is None:
            ET.SubElement(current, 'freejoint', name='floating_base')
        elif source_joint.get('type') == 'revolute':
            joint_name = source_joint.get('name')
            entry = metadata[name]
            effort = float(entry['effort'])
            ET.SubElement(current, 'joint', name=joint_name, type='hinge',
                          axis=entry['axis'], limited='true',
                          range=entry['lower'] + ' ' + entry['upper'],
                          actuatorfrcrange=f'{-effort:.17g} {effort:.17g}',
                          user=entry['effort'] + ' ' + entry['velocity'])
        inertia = inertials[name]
        ET.SubElement(current, 'inertial', pos=inertia['xyz'], mass=inertia['mass'],
                      fullinertia=inertia['fullinertia'])
        geom = geometry[name]
        shared = {'type': 'mesh', 'mesh': name, 'pos': geom['xyz'],
                  'quat': _quat(geom['rpy'])}
        ET.SubElement(current, 'geom', name=name + '_visual', **shared,
                      rgba=geom['color'], contype='0', conaffinity='0',
                      density='0', group='2')
        ET.SubElement(current, 'geom', name=name + '_collision', **shared,
                      contype='1', conaffinity='1', density='0', group='3')
        for child, joint in children[name]:
            body(child, current, joint)

    body('base_link', world)
    _check(len(visited) == len(links) and derived_joint_order == source_joint_order,
           'MJCF body traversal changed the source joint order')
    ET.indent(robot, space='  ')
    baseline = ET.tostring(robot, encoding='utf-8', xml_declaration=True) + b'\n'
    report = {'schema_version': 1, 'source_urdf_sha256': _sha(source_bytes),
              'baseline_mjcf_sha256': _sha(baseline),
              'source_links': len(links), 'source_joints': len(joints),
              'source_movable_joints': sum(j.get('type') == 'revolute' for j in joints.values()),
              'source_joint_order': source_joint_order,
              'derived_joint_order': derived_joint_order,
              'source_sensor_count': 0, 'source_camera_count': 0,
              'native_added_freejoint': 'floating_base',
              'native_actuator_count': 0,
              'native_joint_user_fields': ['source_effort_Nm', 'source_velocity_rad_s'],
              'visual_geom_group': 2, 'collision_geom_group': 3,
              'display_group_scope': 'classification only; collision contacts remain enabled',
              'fixed_links_preserved': True,
              'shared_original_visual_collision_meshes': True,
              'source_base_mass_kg': inertials['base_link']['mass'],
              'authored_inertia_policy': 'preserved_full_tensor',
              'source_joint_metadata': metadata,
              'native_collision_limit': 'MuJoCo mesh contact uses convex hulls; source STL unchanged',
              'physical_dynamics_validated': False, 'physical_fit_tested': False}
    return baseline, report


def _map_preview_pose(legacy_path: Path, legacy: dict, report: dict,
                      audit: dict, audit_bytes: bytes,
                      source_root: ET.Element) -> tuple[dict | None, dict]:
    """Map historical home pose by old joint child -> audited new child link."""
    old_pose_name = legacy.get('preview_pose')
    _check(isinstance(old_pose_name, str), 'Legacy preview pose is missing')
    old_pose_path = legacy_path.parent / old_pose_name
    old_pose_bytes = old_pose_path.read_bytes()
    old_pose = json.loads(old_pose_bytes)
    old_baseline = parse_xml((legacy_path.parent / legacy['baseline_mjcf']).read_bytes())
    old_joint_children = {}
    for body in old_baseline.findall('.//body'):
        for joint in body.findall('joint'):
            old_joint_children[joint.get('name')] = body.get('name')
    link_map = audit.get('comparison', {}).get('old_to_new_links')
    _check(isinstance(link_map, dict), 'Audit lacks old-to-new link mapping')
    new_by_child = report['source_joint_metadata']
    selected = {}
    evidence = {}
    corrections = {}
    for old_name, value in old_pose.get('joints', {}).items():
        old_child = old_joint_children.get(old_name)
        new_child = link_map.get(old_child)
        entry = new_by_child.get(new_child)
        _check(old_child is not None and new_child is not None and entry is not None
               and entry['type'] == 'revolute',
               'Preview pose cannot map old joint through audited child link: ' + old_name)
        new_name = entry['name']
        _check(new_name not in selected, 'Preview pose maps two joints to one new joint')
        source_position = float(value)
        position = source_position
        _check(math.isfinite(position), 'Nonfinite preview joint position')
        lower, upper = float(entry['lower']), float(entry['upper'])
        if 'finger_link' in new_child:
            _check(source_position == 0.0, 'Legacy preview finger pose is not zero')
        if not lower <= position <= upper:
            position = min(max(position, lower), upper)
            corrections[new_name] = {
                'source_position_rad': source_position,
                'display_position_rad': position,
                'source_limit_rad': [lower, upper],
                'basis': 'nearest value within latest authored URDF joint limit'}
        selected[new_name] = position
        evidence[old_name] = {'old_child_link': old_child, 'new_child_link': new_child,
                              'new_joint': new_name, 'source_position_rad': source_position,
                              'display_position_rad': position,
                              'source_limit_rad': [lower, upper]}
    source_movable = [joint.get('name') for joint in source_root.findall('joint')
                      if joint.get('type') == 'revolute']
    _check(set(selected) == set(source_movable),
           'Preview pose does not cover all latest movable joints')
    ordered = {name: selected[name] for name in source_movable}
    return ({'base_height_m': float(old_pose['base_height_m']),
             'joints': ordered, 'source_legacy_pose_sha256': _sha(old_pose_bytes),
             'source_audit_sha256': _sha(audit_bytes),
             'mapping_method': 'old_joint_to_old_child_to_audited_new_child_to_new_joint',
             'corrections': corrections,
             'all_joint_limits_checked': True,
             'scope': ('Static nearest valid pose, not retained standing HOME or calibrated gripper. '
                       'No controller, collision, dynamics or physical-fit certification.')},
            {'status': 'mapped_with_nearest_valid_limit_corrections',
             'source_legacy_pose_sha256': _sha(old_pose_bytes),
             'mapping_method': 'old_joint_to_old_child_to_audited_new_child_to_new_joint',
             'corrections': corrections, 'mapped_joints': evidence})


def _sanitize_audit_paths(audit: dict, replacements: dict[str, str]) -> bytes:
    """Keep audited values while replacing four machine paths with repo paths."""
    used = set()

    def visit(value):
        if isinstance(value, dict):
            return {key: visit(item) for key, item in value.items()}
        if isinstance(value, list):
            return [visit(item) for item in value]
        if isinstance(value, str):
            if value in replacements:
                used.add(value)
                return replacements[value]
            _check(re.search(r'(?i)[a-z]:[\\/]|\\\\[^\\/]+[\\/]', value) is None,
                   'Source audit contains an unrecognized machine-absolute path')
        return value

    portable = visit(audit)
    _check(used == set(replacements), 'Source audit did not contain all expected paths')
    portable['path_reference_basis'] = 'robot-shell-workflow repository root'
    return (json.dumps(portable, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')


def import_jumper(source: Path, destination: Path, *, legacy_profile: Path | None = None,
                  source_audit: Path | None = None) -> dict:
    """Create robots/jumper from the accepted source package in a new directory."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    _check(not destination.exists(), 'Destination already exists')
    urdf_path = source / 'urdf/jumper.urdf'
    source_bytes = urdf_path.read_bytes()
    source_digest = _sha(source_bytes)
    baseline, report = convert_urdf(source_bytes)
    _check((report['source_links'], report['source_joints'], report['source_movable_joints']) ==
           (EXPECTED_LINKS, EXPECTED_JOINTS, EXPECTED_MOVABLE),
           'Source is not the accepted 41-link Jumper revision')
    lm_j0 = next((entry for entry in report['source_joint_metadata'].values()
                  if entry['name'] == 'LM_J0_joint'), None)
    _check(lm_j0 is not None and lm_j0['type'] == 'revolute' and
           (float(lm_j0['lower']), float(lm_j0['upper'])) == CURRENT_LM_J0_LIMIT_RAD,
           'Current Jumper LM_J0_joint source limit must be [-0.75, 1] rad; '
           'refuse an outdated or changed mechanical revision')
    _check(float(report['source_base_mass_kg']) == 0.886006064277726,
           'Source base mass differs from accepted reference')
    revision = REVISION.match(source_bytes)
    _check(revision is not None, 'Source URDF revision comment is missing')
    meshes = source / 'meshes/visual'
    expected = {name + '.stl' for name in report['source_joint_metadata']} | {'base_link.stl'}
    actual = {path.name for path in meshes.iterdir() if path.is_file()}
    _check(actual == expected, 'Source original visual mesh set differs from 41 links')
    source_mesh_hashes = {name: _sha_file(meshes / name) for name in expected}
    legacy = None
    if legacy_profile is not None:
        legacy_path = Path(legacy_profile).resolve()
        legacy = json.loads(legacy_path.read_text(encoding='utf-8'))
        _check(legacy.get('mechanical_platform') == 'original-robot-v1'
               and legacy.get('source_step_sha256'),
               'Legacy mechanical profile is not the expected interface')
    else:
        _fail('An audited original-robot-v1 mechanical profile is required')
    _check(source_audit is not None, 'Current-source audit is required for link and pose mapping')
    audit_path = Path(source_audit).resolve()
    audit_bytes = audit_path.read_bytes()
    audit = json.loads(audit_bytes)
    _check(audit.get('schema') == 'jumper-source-audit/1'
           and audit.get('source', {}).get('sha256') == source_digest
           and audit.get('source', {}).get('link_count') == EXPECTED_LINKS
           and audit.get('source', {}).get('joint_count') == EXPECTED_JOINTS,
           'Source audit does not match the current URDF bytes')
    for name, digest in source_mesh_hashes.items():
        record = audit['source']['resources'].get(MESH_PREFIX + name)
        _check(isinstance(record, dict) and record.get('sha256') == digest,
               'Source audit mesh hash mismatch: ' + name)
    portable_audit_bytes = _sanitize_audit_paths(audit, {
        str(urdf_path): 'robots/jumper/urdf/jumper.urdf',
        str(legacy_path.parent / legacy['baseline_mjcf']):
            'robots/jumper-v1-6/baseline.xml',
        str(legacy_path.parent / 'meshes/shangke_link.STL'):
            'robots/jumper-v1-6/meshes/shangke_link.STL',
        str(meshes / 'upper_shell_link.stl'):
            'robots/jumper/meshes/visual/upper_shell_link.stl',
    })
    portable_audit = json.loads(portable_audit_bytes)
    # The transform is populated only after finite CAD seam samples are tested
    # against this source upper mesh. A changed visual mesh alone cannot prove
    # that the parent frame or physical mounting surface stayed identical.
    source_root = parse_xml(source_bytes)
    shell_joint = next((j for j in source_root.findall('joint')
                        if j.get('name') == 'upper_shell_joint'), None)
    _check(shell_joint is not None and shell_joint.get('type') == 'fixed',
           'Source upper shell fixed joint is missing')
    source_parent, source_child = shell_joint.find('parent'), shell_joint.find('child')
    _check(source_parent is not None and source_child is not None
           and source_parent.get('link') == 'base_link'
           and source_child.get('link') == 'upper_shell_link',
           'Source upper shell parent link has changed')
    upper_joint_xyz, upper_joint_rpy = _origin(shell_joint.find('origin'), 'upper_shell_joint')
    _check(all(abs(v) < 1e-14 for v in _numbers(upper_joint_rpy, 3, 'upper shell joint RPY')),
           'Rotated upper shell joint needs a new CAD frame adapter')
    alignment = _align_source_shell(meshes / 'upper_shell_link.stl',
                                    legacy_path, legacy, upper_joint_xyz)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.jumper-import-', dir=destination.parent) as temporary:
        stage = Path(temporary)
        (stage / 'urdf').mkdir()
        (stage / 'meshes/visual').mkdir(parents=True)
        (stage / 'urdf/jumper.urdf').write_bytes(source_bytes)
        for name in sorted(expected):
            shutil.copyfile(meshes / name, stage / 'meshes/visual' / name)
            _check(_sha_file(stage / 'meshes/visual' / name) == source_mesh_hashes[name]
                   and _sha_file(meshes / name) == source_mesh_hashes[name],
                   'Source mesh changed during import: ' + name)
        (stage / 'baseline.xml').write_bytes(baseline)
        (stage / 'source-audit.json').write_bytes(portable_audit_bytes)
        seam_name = legacy.get('seam_reference')
        _check(isinstance(seam_name, str), 'Legacy seam reference is missing')
        shutil.copyfile(legacy_path.parent / seam_name, stage / 'seam-reference.json')
        preview, pose_mapping = _map_preview_pose(legacy_path, legacy, report,
                                                   portable_audit, portable_audit_bytes,
                                                   source_root)
        if preview is not None:
            _json(stage / 'preview-pose.json', preview)
        report['source_meshes'] = [{'path': 'meshes/visual/' + name,
                                    'bytes': (stage / 'meshes/visual' / name).stat().st_size,
                                    'sha256': _sha_file(stage / 'meshes/visual' / name)}
                                   for name in sorted(expected)]
        report['alignment'] = alignment
        report['source_audit_sha256'] = _sha(portable_audit_bytes)
        report['external_source_audit_sha256'] = _sha(audit_bytes)
        report['preview_pose_mapping'] = pose_mapping
        report['source_revision_comment'] = revision.group(1).decode('utf-8')
        report['source_urdf_path'] = 'urdf/jumper.urdf'
        report['legacy_profile_sha256'] = _sha_file(legacy_path)
        report['importer_code_sha256'] = _sha_file(Path(__file__))
        report['six_hole_interface_validated'] = False
        report['mechanical_interface_status'] = ('original STEP identifier inherited; '
            'finite seam registration passed; six-hole surface fit and physical assembly unverified')
        _json(stage / 'import-report.json', report)
        inventory = []
        for path in sorted(stage.rglob('*')):
            if path.is_file():
                inventory.append({'role': 'source_urdf' if path.name == 'jumper.urdf' else
                                  'baseline_mjcf' if path.name == 'baseline.xml' else
                                  'robot_mesh' if path.suffix == '.stl' else 'import_evidence',
                                  'path': path.relative_to(stage).as_posix(),
                                  'sha256': _sha_file(path), 'bytes': path.stat().st_size})
        velocities = {entry['velocity'] for entry in report['source_joint_metadata'].values()
                      if entry['type'] == 'revolute'}
        profile = {'schema_version': 1, 'id': 'jumper',
                   'mechanical_platform': 'original-robot-v1',
                   'source_step_sha256': legacy['source_step_sha256'],
                   'baseline_mjcf': 'baseline.xml', 'source_urdf': 'urdf/jumper.urdf',
                   'parent_link': 'upper_shell_link',
                   'visual_replacement': {'mode': 'dedicated_link',
                                          'geom_name': 'upper_shell_link_visual'},
                   'cad_mm_to_parent_m': alignment['cad_mm_to_parent_m'],
                   'cad_mm_to_base_m': alignment['cad_mm_to_base_m'],
                   'seam_reference': 'seam-reference.json',
                   'source_audit': 'source-audit.json',
                   'source_joint_order': report['source_joint_order'],
                   'urdf_joint_metadata': report['source_joint_metadata'],
                   'source_revision_comment': report['source_revision_comment'],
                   'robot_velocity_limit_fallback_rad_s': float(next(iter(velocities)))
                       if len(velocities) == 1 else 100.0,
                   'collision_policy': 'baseline_preserved',
                   'inertia_policy': 'baseline_preserved',
                   'physical_fit_tested': False, 'physical_dynamics_validated': False,
                   'six_hole_interface_validated': False,
                   'redistribution_status': legacy.get('redistribution_status'),
                   'source': {'kind': 'user_maintained_urdf',
                              'source_urdf_sha256': _sha(source_bytes),
                              'baseline_mjcf_sha256': _sha(baseline)},
                   'files': inventory}
        if preview is not None:
            profile['preview_pose'] = 'preview-pose.json'
        _json(stage / 'profile.json', profile)
        _check(_sha_file(urdf_path) == source_digest,
               'Source URDF changed during import')
        _check(_sha_file(audit_path) == _sha(audit_bytes),
               'Source audit changed during import')
        _check(not destination.exists(), 'Destination appeared during import')
        stage.rename(destination)
    return {'ok': True, 'id': 'jumper', 'destination': str(destination),
            'source_urdf_sha256': report['source_urdf_sha256'],
            'baseline_mjcf_sha256': report['baseline_mjcf_sha256'],
            'profile_sha256': _sha_file(destination / 'profile.json'),
            'links': EXPECTED_LINKS, 'joints': EXPECTED_JOINTS,
            'movable_joints': EXPECTED_MOVABLE,
            'alignment': alignment}


def _align_source_shell(mesh: Path, legacy_path: Path, legacy: dict,
                        upper_joint_xyz: str) -> dict:
    """Finite seam evidence for reusing a CAD frame; failure refuses import."""
    import numpy as np
    import trimesh

    old_parent = legacy.get('cad_mm_to_parent_m')
    base = legacy.get('cad_mm_to_base_m')
    _check(isinstance(old_parent, dict) and isinstance(base, dict)
           and legacy.get('seam_reference'),
           'Legacy CAD alignment evidence is missing')
    origin = np.asarray(_numbers(upper_joint_xyz, 3, 'upper shell joint xyz'))
    _check(base.get('scale') == old_parent.get('scale')
           and base.get('rotation_matrix') == old_parent.get('rotation_matrix'),
           'Legacy parent and base CAD rotations disagree')
    transform = copy.deepcopy(base)
    transform['translation_m'] = (np.asarray(base['translation_m']) - origin).tolist()
    transform['formula'] = ('p_upper_shell_m = rotation_matrix @ '
                            '(p_engineering_mm * 0.001) + translation_m')
    sample_bytes = (legacy_path.parent / legacy['seam_reference']).read_bytes()
    samples = json.loads(sample_bytes)['points']
    points = np.asarray(samples, dtype=float)
    _check(points.ndim == 2 and points.shape[1] == 3 and len(points) >= 20
           and np.isfinite(points).all(), 'Invalid finite seam samples')
    source_mesh = trimesh.load_mesh(mesh, process=False)
    _check(isinstance(source_mesh, trimesh.Trimesh) and len(source_mesh.faces) > 0,
           'Source upper shell STL is not a triangle mesh')
    local = (points * float(transform['scale'])) @ np.asarray(transform['rotation_matrix']).T
    local += np.asarray(transform['translation_m'])
    distances = []
    # closest_point_naive avoids an rtree dependency; chunks keep its temporary
    # point×triangle array bounded for the 553 accepted seam samples.
    for begin in range(0, len(local), 8):
        _, delta, _ = trimesh.proximity.closest_point_naive(source_mesh, local[begin:begin+8])
        distances.extend(delta.tolist())
    p95 = float(np.percentile(distances, 95))
    maximum = float(max(distances))
    _check(p95 <= 0.00025 and maximum <= 0.001,
           f'New upper shell fails original CAD seam registration: p95={p95}, max={maximum} m')
    return {'method': 'source_stl_to_original_cad_seam_samples',
            'source_mesh_sha256': _sha_file(mesh),
            'legacy_profile_sha256': _sha_file(legacy_path),
            'legacy_seam_reference_sha256': _sha(sample_bytes),
            'source_upper_joint_origin_base_m': origin.tolist(),
            'sample_count': len(points), 'p95_m': p95, 'max_m': maximum,
            'p95_limit_m': 0.00025, 'max_limit_m': 0.001,
            'scope': 'finite display registration samples; no physical fit certification',
            'cad_mm_to_parent_m': transform, 'cad_mm_to_base_m': base,
            'passed': True}
