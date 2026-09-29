"""Assemble a CAD-frame shell with a hash-bound robot; no print geometry edits."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import trimesh
from scipy.spatial import cKDTree


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(data)
    return digest.hexdigest()


def relative_file(root, value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError('Expected portable relative file path')
    target = (root / value).resolve()
    if Path(value).is_absolute() or '..' in Path(value).parts or not target.is_relative_to(root.resolve()):
        raise ValueError('File path leaves its package')
    return target


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_xml(path, root):
    ET.indent(root, space='  ')
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)


def load_mujoco(path):
    """VFS also supports Windows paths containing non-ASCII characters."""
    import mujoco
    path = Path(path)
    assets = {p.relative_to(path.parent).as_posix(): p.read_bytes()
              for p in path.parent.rglob('*') if p.is_file() and p.suffix.lower() in {'.stl', '.obj', '.xml', '.png'}}
    return mujoco.MjModel.from_xml_string(path.read_text(encoding='utf-8'), assets)


def verify_profile(profile_path):
    profile_path = Path(profile_path).resolve()
    profile = json.loads(profile_path.read_text(encoding='utf-8'))
    if profile.get('schema_version') != 1 or not profile.get('files'):
        raise ValueError('Unsupported robot profile')
    for record in profile['files']:
        source = relative_file(profile_path.parent, record['path'])
        if not source.is_file() or source.stat().st_size != record['bytes'] or sha(source) != record['sha256']:
            raise ValueError('Robot asset integrity failed: ' + record['path'])
    return profile


def colors_from_ams(path, source_mesh):
    """Read supported whole-face Bambu paint codes, only after exact STL matching.

    Build/plate transforms are deliberately not applied to CAD assembly coordinates.
    Other 3MF object layouts and subdivided paints require their own adapter.
    """
    codes = {'4': 0, '8': 1, '0C': 2, '1C': 3}
    with zipfile.ZipFile(path) as archive:
        if any(i.file_size > 1024**3 for i in archive.infolist()):
            raise ValueError('3MF member exceeds adapter size limit')
        settings = json.loads(archive.read('Metadata/project_settings.config'))
        palette = settings['filament_colour']
        if not 1 <= len(palette) <= 4:
            raise ValueError('This adapter supports one to four palette slots')
        main = ET.fromstring(archive.read('3D/3dmodel.model'))
        if main.get('unit', 'millimeter') != 'millimeter':
            raise ValueError('AMS must use millimeter model units')
        components = [e for e in main.iter() if e.tag.endswith('}component')]
        if len(components) != 1:
            raise ValueError('3MF requires a single referenced mesh component')
        if components[0].get('transform', '1 0 0 0 1 0 0 0 1 0 0 0') != '1 0 0 0 1 0 0 0 1 0 0 0':
            raise ValueError('Non-identity component transform requires a dedicated adapter')
        filename = next((v.lstrip('/') for k, v in components[0].attrib.items() if k.endswith('}path')), None)
        if not filename:
            raise ValueError('No external component path in supported 3MF')
        verts, faces, colors = [], [], []
        with archive.open(filename) as stream:
            for _, element in ET.iterparse(stream, events=['end']):
                tag = element.tag.split('}')[-1]
                if tag == 'vertex':
                    verts.append(tuple(float(element.get(k)) for k in ('x', 'y', 'z')))
                elif tag == 'triangle':
                    faces.append(tuple(int(element.get(k)) for k in ('v1', 'v2', 'v3')))
                    color = element.get('paint_color', '').upper()
                    if color not in codes or codes[color] >= len(palette):
                        raise ValueError('Unknown or subdivided paint code')
                    colors.append(codes[color])
                element.clear()
        vertices = np.asarray(verts, dtype=np.float32)
        indices = np.asarray(faces, dtype=np.int64)
        if len(indices) != len(source_mesh.faces):
            raise ValueError('AMS and STL have different triangle counts')
        for start in range(0, len(indices), 20000):
            actual = vertices[indices[start:start + 20000]]
            expected = np.asarray(source_mesh.vertices[source_mesh.faces[start:start + 20000]], dtype=np.float32)
            if not np.array_equal(actual, expected):
                raise ValueError('AMS triangles do not exactly match the selected STL in order and CAD coordinates')
        return np.asarray(colors, dtype=np.uint8), palette


def simplify_visual(mesh, target_faces):
    if target_faces < 1000:
        raise ValueError('Visual face budget must be at least 1000')
    report = {'input_faces': len(mesh.faces), 'requested_faces': target_faces,
              'manufacturing_mesh_modified': False, 'sampling_is_not_global_error_bound': True}
    if len(mesh.faces) <= target_faces:
        result = mesh.copy()
    else:
        import fast_simplification
        vertices, faces = fast_simplification.simplify(np.asarray(mesh.vertices), np.asarray(mesh.faces),
                                                     target_count=target_faces, agg=5.0)
        result = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    # Deterministic finite checks in both directions, in source millimeters.
    deviations = []
    for sample_mesh, reference in ((mesh, result), (result, mesh)):
        sample = sample_mesh.vertices[np.linspace(0, len(sample_mesh.vertices) - 1,
                                                  min(1000, len(sample_mesh.vertices)), dtype=int)]
        parts = []
        for begin in range(0, len(sample), 100):
            _, distances, _ = trimesh.proximity.closest_point(reference, sample[begin:begin + 100])
            parts.append(distances)
        deviations.append(np.concatenate(parts))
    values = np.concatenate(deviations)
    report.update(output_faces=len(result.faces), sampled_vertices=len(values),
                  sampled_p99_mm=float(np.percentile(values, 99)), sampled_max_mm=float(values.max()),
                  visual_sample_limit_mm=2.0)
    if not np.isfinite(values).all() or values.max() > 2.0:
        raise ValueError('Visual simplification exceeded 2 mm sampled error; increase --faces')
    return result, report


def transfer_colors(source, simplified, colors):
    # Choose nearby source face with similar normal to avoid painting from the inner wall.
    tree = cKDTree(source.triangles_center)
    distances, candidates = tree.query(simplified.triangles_center, k=min(4, len(source.faces)))
    if candidates.ndim == 1:
        return colors[candidates]
    dot = np.einsum('ijk,ik->ij', source.face_normals[candidates], simplified.face_normals)
    best = np.argmin(distances + np.maximum(0.0, 1.0 - dot) * 3.0, axis=1)
    return colors[candidates[np.arange(len(candidates)), best]]


def compare_compiled(baseline, assembled):
    import mujoco
    left = load_mujoco(baseline)
    right = load_mujoco(assembled)
    checks = {}
    for field in ('nq', 'nv', 'njnt', 'nu', 'nbody', 'ncam', 'nsensor'):
        checks[field + '_preserved'] = getattr(left, field) == getattr(right, field)
    for field in ('jnt_type', 'jnt_range', 'jnt_axis', 'jnt_pos', 'dof_damping', 'dof_armature',
                  'body_mass', 'body_inertia', 'body_ipos', 'body_iquat', 'actuator_gainprm',
                  'sensor_type', 'sensor_objid', 'sensor_dim', 'cam_pos', 'cam_quat'):
        checks[field + '_preserved'] = bool(np.array_equal(getattr(left, field), getattr(right, field)))
    source_joints = [mujoco.mj_id2name(left, mujoco.mjtObj.mjOBJ_JOINT, i) for i in range(left.njnt)]
    result_joints = [mujoco.mj_id2name(right, mujoco.mjtObj.mjOBJ_JOINT, i) for i in range(right.njnt)]
    checks['joint_names_preserved'] = source_joints == result_joints
    collision_count = 0
    for geom in range(left.ngeom):
        if not (left.geom_contype[geom] or left.geom_conaffinity[geom]):
            continue
        name = mujoco.mj_id2name(left, mujoco.mjtObj.mjOBJ_GEOM, geom)
        other = mujoco.mj_name2id(right, mujoco.mjtObj.mjOBJ_GEOM, name)
        same = other >= 0 and all(np.array_equal(getattr(left, key)[geom], getattr(right, key)[other])
               for key in ('geom_type', 'geom_pos', 'geom_quat', 'geom_size', 'geom_contype', 'geom_conaffinity', 'geom_friction'))
        checks['collision_' + name + '_preserved'] = bool(same)
        collision_count += 1
    if not all(checks.values()):
        raise ValueError('Robot assembly changed baseline dynamics or joints: ' + ', '.join(k for k, v in checks.items() if not v))
    data = mujoco.MjData(right)
    pose_corrections = {}
    for joint in range(right.njnt):
        if (right.jnt_limited[joint] and
                int(right.jnt_type[joint]) in (int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE))):
            address = right.jnt_qposadr[joint]
            before = float(data.qpos[address])
            after = float(np.clip(before, *right.jnt_range[joint]))
            if before != after:
                data.qpos[address] = after
                pose_corrections[result_joints[joint]] = dict(before=before, after=after)
    mujoco.mj_forward(right, data)
    for _ in range(10):
        mujoco.mj_step(right, data)
    if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
        raise ValueError('Native MuJoCo finite-step smoke test failed')
    return dict(passed=True, checks=checks, preserved_collision_geoms=collision_count,
                actuators=right.nu, joints=right.njnt, mujoco_version=mujoco.__version__,
                finite_steps=10, smoke_initial_pose='default_clamped_to_authored_joint_limits',
                smoke_pose_corrections=pose_corrections, physical_dynamics_validated=False)


def verify_whole_robot(baseline, assembled_urdf, shell_parent_link):
    """Reject a shell-only export and require every baseline body as a URDF link."""
    source = ET.parse(baseline).getroot()
    roots = source.findall('worldbody/body')
    expected = [body.get('name') for body in source.findall('.//body')]
    urdf = ET.parse(assembled_urdf).getroot()
    actual = {link.get('name') for link in urdf.findall('link')}
    movable = [joint.get('name') for joint in source.findall('.//body/joint')
               if joint.get('type', 'hinge') in ('hinge', 'slide')]
    exported_movable = {joint.get('name') for joint in urdf.findall('joint')
                        if joint.get('type') in ('revolute', 'continuous', 'prismatic')}
    if (len(roots) != 1 or len(expected) < 2 or not movable
            or shell_parent_link not in expected or not set(expected) <= actual
            or set(movable) != exported_movable):
        raise ValueError('Full-robot URDF must retain the baseline links and movable joints, including the shell parent')
    return dict(passed=True, scope='full_robot', root_link=roots[0].get('name'),
                robot_links=len(expected), movable_joints=len(movable),
                native_actuators=len(source.findall('actuator/*')),
                shell_parent_link=shell_parent_link, retained_links=expected,
                retained_movable_joints=movable)


def apply_visual_overrides(xml, overrides, upper_link):
    """Apply explicit opaque colors to existing non-colliding body visuals only."""
    if not isinstance(overrides, list):
        raise ValueError('Visual overrides must be an array')
    seen = set()
    for record in overrides:
        if not isinstance(record, dict) or set(record) != {'link', 'geom', 'rgba'}:
            raise ValueError('Visual override requires link, geom and rgba')
        link, name, rgba = record['link'], record['geom'], record['rgba']
        if not isinstance(link, str) or not isinstance(name, str) or link == upper_link:
            raise ValueError('Visual override requires a non-upper baseline link')
        if (link, name) in seen:
            raise ValueError('Duplicate visual override')
        seen.add((link, name))
        if (not isinstance(rgba, list) or len(rgba) != 4
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not np.isfinite(v) or not 0 <= v <= 1 for v in rgba)
                or rgba[3] != 1):
            raise ValueError('Visual override requires finite opaque RGBA')
        bodies = [body for body in xml.iter('body') if body.get('name') == link]
        geoms = [geom for body in bodies for geom in body.findall('geom') if geom.get('name') == name]
        if len(geoms) != 1 or not ((geoms[0].get('class') == 'visual'
                and geoms[0].get('contype', '0') == '0' and geoms[0].get('conaffinity', '0') == '0')
                or (geoms[0].get('contype', '1') == '0' and geoms[0].get('conaffinity', '1') == '0')):
            raise ValueError('Visual override requires a non-colliding baseline visual geom')
        geoms[0].set('rgba', ' '.join(map(str, rgba)))


def assemble(shell, output, profile_path, *, ams3mf=None, faces=100000, lower_shell_color=None,
             visual_overrides=None):
    from .urdf import export_urdf, verify_urdf
    import mujoco
    shell, output, profile_path = Path(shell).resolve(), Path(output).resolve(), Path(profile_path).resolve()
    if output.exists():
        raise FileExistsError('Output already exists; choose a new version directory')
    if not shell.is_file() or shell.suffix.lower() != '.stl':
        raise ValueError('Expected a final STL in the declared original CAD millimeter frame')
    visual_overrides = copy.deepcopy(visual_overrides) if visual_overrides is not None else []
    if lower_shell_color is not None:
        if not isinstance(lower_shell_color, str) or re.fullmatch(r'#[0-9A-Fa-f]{6}', lower_shell_color) is None:
            raise ValueError('Lower shell color must be #RRGGBB')
        lower_rgba = [int(lower_shell_color[i:i + 2], 16) / 255 for i in (1, 3, 5)] + [1.0]
        visual_overrides.append({'link': 'base_link', 'geom': 'base_link_visual', 'rgba': lower_rgba})
    profile = verify_profile(profile_path)
    baseline = relative_file(profile_path.parent, profile['baseline_mjcf'])
    source_sha = sha(shell)
    mesh = trimesh.load_mesh(shell, process=True)
    if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces) or not np.isfinite(mesh.vertices).all():
        raise ValueError('Invalid shell triangle mesh')
    if not 100.0 <= float(mesh.extents.max()) <= 1000.0:
        raise ValueError('Shell units/frame require review; expected CAD millimeters, not meters')
    seam = json.loads(relative_file(profile_path.parent, profile['seam_reference']).read_text(encoding='utf-8'))
    distances = []
    points = np.asarray(seam['points'], dtype=float)
    for begin in range(0, len(points), 100):
        _, delta, _ = trimesh.proximity.closest_point(mesh, points[begin:begin + 100])
        distances.extend(delta.tolist())
    seam_check = dict(sample_count=len(points), p95_mm=float(np.percentile(distances, 95)),
                      max_mm=float(max(distances)), p95_limit_mm=0.25, max_limit_mm=1.0,
                      scope='finite shared-interface samples for display registration, not physical fit')
    if seam_check['p95_mm'] > 0.25 or seam_check['max_mm'] > 1.0:
        raise ValueError('Shell does not match shared CAD seam samples: ' + json.dumps(seam_check))
    seam_check['passed'] = True
    simplified, decimation = simplify_visual(mesh, faces)
    color_report = dict(mode='monochrome', reason='No matching supported AMS provided')
    face_colors = np.zeros(len(simplified.faces), dtype=np.uint8)
    palette = ['#E8DDC8']
    ams_path = Path(ams3mf).resolve() if ams3mf else shell.parent / 'ams.3mf'
    if ams_path.is_file():
        try:
            adapter_report = None
            try:
                colors, palette = colors_from_ams(ams_path, mesh)
            except ValueError:
                from .ams_colors import colors_from_ams as read_recentered_ams
                colors, palette, adapter_report = read_recentered_ams(ams_path, mesh)
            face_colors = transfer_colors(mesh, simplified, colors)
            color_report = dict(mode='palette_from_exact_matching_ams', source_sha256=sha(ams_path),
                                simplified_face_assignment='nearest_similar_normal_source_face',
                                exact_paint_boundary_preservation=False, palette=palette)
            if adapter_report is not None:
                color_report['mode'] = adapter_report['mode']
                color_report['ams_geometry_mapping'] = adapter_report
        except (ValueError, KeyError, ET.ParseError, zipfile.BadZipFile) as error:
            color_report = dict(mode='monochrome', reason=str(error), source_sha256=sha(ams_path))
            palette = ['#E8DDC8']
    transform = profile.get('cad_mm_to_parent_m') or profile['cad_mm_to_base_m']
    simplified.vertices = (np.asarray(simplified.vertices) * transform['scale']) @ np.asarray(transform['rotation_matrix']).T + np.asarray(transform['translation_m'])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.shellflow-sim-', dir=output.parent) as temporary:
        stage = Path(temporary)
        (stage / 'meshes').mkdir()
        xml = ET.parse(baseline).getroot()
        assets = xml.find('asset')
        compiler = xml.find('compiler')
        meshdir = compiler.get('meshdir', 'meshes') if compiler is not None else 'meshes'
        mesh_destination = relative_file(stage, meshdir.rstrip('/'))
        mesh_destination.mkdir(parents=True, exist_ok=True)
        # Copy every referenced baseline mesh, preserving their original coordinates.
        for resource in assets.findall('mesh'):
            relative = meshdir.rstrip('/') + '/' + resource.get('file')
            source = relative_file(profile_path.parent, relative)
            target = relative_file(stage, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        parent = xml.find(".//body[@name='" + profile['parent_link'] + "']")
        if parent is None:
            raise ValueError('Expected shell parent link is missing')
        replacement = profile.get('visual_replacement', {'mode': 'split_base'})
        mode = replacement['mode']
        original_name = replacement.get('geom_name', profile.get('source_base_visual'))
        if not isinstance(original_name, str):
            raise ValueError('Robot profile must name the replaced visual geom')
        old_visual = parent.find("geom[@name='" + original_name + "']")
        if old_visual is None:
            raise ValueError('Expected original shell visual is missing')
        if mode == 'split_base':
            lower = relative_file(profile_path.parent, profile['lower_visual_mesh'])
            shutil.copy2(lower, stage / 'meshes' / lower.name)
            ET.SubElement(assets, 'mesh', name='shellflow_lower', file=lower.name)
            old_visual.set('mesh', 'shellflow_lower')
        elif mode == 'dedicated_link':
            # Keep the named link, fixed joint, inertial and collision geometry intact.
            # Its original visual must be removed, otherwise both shells overlap.
            parent.remove(old_visual)
        else:
            raise ValueError('Unsupported visual replacement mode: ' + str(mode))
        apply_visual_overrides(xml, visual_overrides,
                               profile['parent_link'] if mode == 'dedicated_link' else '')
        for index in np.unique(face_colors):
            part = simplified.submesh([np.flatnonzero(face_colors == index)], append=True, repair=False)
            filename = 'upper_shell_' + str(int(index)) + '.stl'
            part.export(mesh_destination / filename)
            mesh_name = 'shellflow_upper_' + str(int(index))
            ET.SubElement(assets, 'mesh', name=mesh_name, file=filename)
            rgba = [int(palette[int(index)].lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4)] + [1.0]
            ET.SubElement(parent, 'geom', name=mesh_name, type='mesh', mesh=mesh_name,
                          contype='0', conaffinity='0', density='0', group='2', rgba=' '.join(map(str, rgba)))
        write_xml(stage / 'robot.xml', xml)
        urdf_report = export_urdf(stage / 'robot.xml', stage / 'robot.urdf',
                                  default_velocity_limit=profile.get('robot_velocity_limit_fallback_rad_s', 100.0),
                                  joint_metadata=profile.get('urdf_joint_metadata'),
                                  joint_order=profile.get('source_joint_order'),
                                  source_revision_comment=profile.get('source_revision_comment'))
        urdf_verification = verify_urdf(stage / 'robot.xml', stage / 'robot.urdf')
        if not urdf_verification['passed']:
            raise ValueError('URDF kinematic/inertial comparison failed: ' + json.dumps(urdf_verification['failures']))
        whole_robot = verify_whole_robot(baseline, stage / 'robot.urdf', profile['parent_link'])
        native = compare_compiled(baseline, stage / 'robot.xml')
        imported = load_mujoco(stage / 'robot.urdf')
        imported_data = mujoco.MjData(imported)
        mujoco.mj_forward(imported, imported_data)
        if not np.isfinite(imported_data.xpos).all():
            raise ValueError('URDF forward-kinematics check failed')
        # A separate scene keeps the portable robot definition free of floor/camera objects.
        scene = ET.Element('mujoco', model='shellflow-preview')
        ET.SubElement(scene, 'include', file='robot.xml')
        visual = ET.SubElement(scene, 'visual')
        ET.SubElement(visual, 'global', offwidth='1200', offheight='900')
        ET.SubElement(visual, 'headlight', ambient='0.5 0.5 0.5', diffuse='0.7 0.7 0.7')
        world = ET.SubElement(scene, 'worldbody')
        ET.SubElement(world, 'geom', name='preview_floor', type='plane', pos='0 0 0', size='2 2 0.1', rgba='0.20 0.23 0.27 1')
        ET.SubElement(world, 'light', pos='0 -1 2', dir='0 0 -1', diffuse='0.8 0.8 0.8')
        pose_info = None
        if profile.get('preview_pose'):
            pose_path = relative_file(profile_path.parent, profile['preview_pose'])
            shutil.copy2(pose_path, stage / 'preview-pose.json')
            pose_info = json.loads(pose_path.read_text(encoding='utf-8'))
            pose_model = load_mujoco(stage / 'robot.xml')
            pose_data = mujoco.MjData(pose_model)
            root_joint = mujoco.mj_name2id(pose_model, mujoco.mjtObj.mjOBJ_JOINT, 'floating_base')
            if root_joint < 0 or int(pose_model.jnt_type[root_joint]) != int(mujoco.mjtJoint.mjJNT_FREE):
                raise ValueError('Preview profile requires named floating base')
            pose_data.qpos[pose_model.jnt_qposadr[root_joint] + 2] = pose_info['base_height_m']
            for name, value in pose_info['joints'].items():
                joint = mujoco.mj_name2id(pose_model, mujoco.mjtObj.mjOBJ_JOINT, name)
                if joint < 0 or not pose_model.jnt_range[joint, 0] <= value <= pose_model.jnt_range[joint, 1]:
                    raise ValueError('Display joint position is missing or outside its range: ' + name)
                pose_data.qpos[pose_model.jnt_qposadr[joint]] = value
            for actuator in range(pose_model.nu):
                joint = pose_model.actuator_trnid[actuator, 0]
                pose_data.ctrl[actuator] = pose_data.qpos[pose_model.jnt_qposadr[joint]]
            keys = ET.SubElement(scene, 'keyframe')
            ET.SubElement(keys, 'key', name='display_home', qpos=' '.join(map(str, pose_data.qpos)),
                          ctrl=' '.join(map(str, pose_data.ctrl)))
        write_xml(stage / 'scene.xml', scene)
        load_mujoco(stage / 'scene.xml')
        preview_script = Path(__file__).resolve().parents[2] / 'scripts/preview_simulation.py'
        shutil.copy2(preview_script, stage / 'preview.py')
        instructions = ('# Assembled robot\n\n'
            'Load `robot.urdf` with its relative `meshes/` directory. Load `scene.xml` in MuJoCo for a preview, '
            'or `robot.xml` to retain the baseline actuators and MuJoCo parameters. '
            'Run `python preview.py` from this package, or `python preview.py --render preview.png` for a static view.\n\n'
            'Runtime: install Python and `python -m pip install mujoco`. Interactive viewing and rendering require a '
            'working graphics/OpenGL environment. On macOS use `mjpython preview.py` for the interactive viewer. '
            'Copy the full meshes directory with actual binary assets, not Git LFS pointer text. Default viewing is '
            'static; `--simulate` explicitly starts the preserved baseline physics.\n\n'
            'The upper visual is replaced and the original lower assembly is retained. Shell visuals are simplified '
            'copies; the original manufacturing STL is unchanged. Baseline mass/inertia/collision remain in place. '
            'The new shell has no newly certified collision or measured inertial model; this package is for visual '
            'assembly and baseline simulation reuse, not physical dynamics certification.\n\n'
            'This is a full-robot URDF, including all baseline links and movable joints. URDF has no native '
            'representation of MJCF actuators. A baseline with no actuators needs its task/controller setup '
            'before controlled simulation; none are invented here. Missing source velocity limits are explicitly '
            'marked as importer defaults in the report.\n')
        (stage / 'README.md').write_text(instructions, encoding='utf-8')
        records = [dict(role='simulation_asset', path=p.relative_to(stage).as_posix(), sha256=sha(p), bytes=p.stat().st_size)
                   for p in sorted(stage.rglob('*')) if p.is_file()]
        if sha(shell) != source_sha:
            raise ValueError('Manufacturing source changed during assembly')
        report = dict(schema_version=1, passed=True, files=records,
            source_shell_sha256=source_sha, source_shell_frame='original-robot-v1 CAD millimeters Z-up',
            robot_profile_sha256=sha(profile_path), source_step_sha256=profile['source_step_sha256'],
            robot_profile_id=profile.get('id'), robot_source=profile.get('source'),
            source_baseline_mjcf_sha256=sha(baseline), transform=transform,
            transform_target_link=profile['parent_link'], visual_replacement_mode=mode, whole_robot=whole_robot,
            seam_registration=seam_check, simplification=decimation, colors=color_report,
            urdf_conversion=urdf_report, urdf_verification=urdf_verification,
            preview_pose=pose_info,
            producer_code_sha256={p.name: sha(p) for p in (Path(__file__), Path(__file__).with_name('urdf.py'),
                                                         Path(__file__).with_name('ams_colors.py'), preview_script)},
            native_mujoco=native, urdf_load=dict(passed=True, nq=imported.nq, nv=imported.nv, joints=imported.njnt),
            collision_policy='baseline_preserved', inertia_policy='baseline_preserved',
            physical_fit_tested=False, physical_dynamics_validated=False,
            dependencies={name: importlib.metadata.version(name) for name in ('numpy', 'scipy', 'trimesh', 'mujoco', 'fast-simplification')},
            limitations=['No newly measured shell mass/inertia or replacement collision geometry',
                         'No full-motion interference proof or physical fit test',
                         'Simplification error is finite sampling, not a global bound',
                         'Paint boundaries on simplified visuals are approximate',
                         'No additional separately printed accessories are mounted unless explicitly supplied'])
        report['visual_overrides'] = visual_overrides
        write_json(stage / 'simulation-report.json', report)
        # Rename only after all exports compile and checks succeed. Output is never overwritten.
        if output.exists():
            raise FileExistsError('Output appeared during assembly')
        stage.rename(output)
    return dict(ok=True, output=str(output), report=str(output / 'simulation-report.json'),
                urdf=str(output / 'robot.urdf'), mjcf=str(output / 'robot.xml'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shell', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--profile', type=Path, default=Path(__file__).resolve().parents[2] / 'robots/jumper/profile.json')
    parser.add_argument('--ams3mf', type=Path)
    parser.add_argument('--faces', type=int, default=100000)
    parser.add_argument('--lower-shell-color', help='Visual-only base_link_visual color as #RRGGBB')
    parser.add_argument('--visual-overrides', type=Path, help='JSON array of explicit body visual RGBA overrides')
    args = parser.parse_args(argv)
    try:
        result = assemble(args.shell, args.output, args.profile, ams3mf=args.ams3mf,
                          faces=args.faces, lower_shell_color=args.lower_shell_color,
                          visual_overrides=json.loads(args.visual_overrides.read_text(encoding='utf-8'))
                          if args.visual_overrides else None)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, ET.ParseError, ImportError) as error:
        print(json.dumps(dict(ok=False, error=str(error)), ensure_ascii=False))
        return 2
