"""Jumper URDF import contract, including the actual accepted 41-link profile."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from shellflow.package_io import PackageError
from shellflow.robot_import import convert_urdf, _sanitize_audit_paths


ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def small_urdf(*, collision_file='upper_shell_link.stl', effort='1.5'):
    def link(name):
        return f'''<link name="{name}"><inertial><origin xyz="0 0 0" rpy="0 0 0"/>
          <mass value="0.5"/><inertia ixx="0.01" ixy="0.001" ixz="0.002"
            iyy="0.02" iyz="0.003" izz="0.03"/></inertial>
          <visual><origin xyz="0 0 0" rpy="0 0 0"/><geometry>
            <mesh filename="../meshes/visual/{name}.stl"/></geometry>
            <material name=""><color rgba="0.85 0.08 0.05 1"/></material></visual>
          <collision><origin xyz="0 0 0" rpy="0 0 0"/><geometry>
            <mesh filename="../meshes/visual/{collision_file if name == 'upper_shell_link' else name+'.stl'}"/>
          </geometry></collision></link>'''
    return f'''<robot name="jumper"><mujoco><compiler balanceinertia="false"
      discardvisual="false" strippath="false"/></mujoco>
      {link('base_link')}{link('upper_shell_link')}{link('leg_link')}
      <joint name="upper_shell_joint" type="fixed"><origin xyz="0 0 .03" rpy="0 0 0"/>
        <parent link="base_link"/><child link="upper_shell_link"/></joint>
      <joint name="LF_J0_joint" type="revolute"><origin xyz=".1 0 0" rpy="0 0 0"/>
        <parent link="base_link"/><child link="leg_link"/><axis xyz="0 1 0"/>
        <limit lower="-1" upper="1" effort="{effort}" velocity="42"/></joint>
      </robot>'''.encode()


class RobotImportTests(unittest.TestCase):
    def test_audit_paths_become_portable_with_external_sha_kept_separate(self):
        def absolute(value):
            return 'C:' + chr(92) + value.replace('/', chr(92))
        paths = {
            absolute('source/urdf/jumper.urdf'): 'robots/jumper/urdf/jumper.urdf',
            absolute('repo/robots/jumper-v1-6/baseline.xml'):
                'robots/jumper-v1-6/baseline.xml',
            absolute('repo/robots/jumper-v1-6/meshes/shangke_link.STL'):
                'robots/jumper-v1-6/meshes/shangke_link.STL',
            absolute('source/meshes/visual/upper_shell_link.stl'):
                'robots/jumper/meshes/visual/upper_shell_link.stl',
        }
        raw = {'schema': 'jumper-source-audit/1',
               'source': {'urdf': next(iter(paths))},
               'old': {'baseline': list(paths)[1]},
               'comparison': {'shell_mesh': {'old_path': list(paths)[2],
                                             'new_path': list(paths)[3]}}}
        original_sha = sha(json.dumps(raw).encode())
        portable_bytes = _sanitize_audit_paths(raw, paths)
        portable = json.loads(portable_bytes)
        self.assertEqual(portable['path_reference_basis'],
                         'robot-shell-workflow repository root')
        self.assertTrue(all(value.encode() not in portable_bytes for value in paths))
        self.assertEqual(original_sha, sha(json.dumps(raw).encode()))
        raw['comparison']['shell_mesh']['new_path'] = absolute('unknown/mesh.stl')
        with self.assertRaisesRegex(PackageError, 'unrecognized machine-absolute'):
            _sanitize_audit_paths(raw, paths)

    def test_synthetic_fullinertia_fixed_body_and_shared_mesh(self):
        baseline, report = convert_urdf(small_urdf())
        root = ET.fromstring(baseline)
        self.assertEqual((report['source_links'], report['source_joints'],
                          report['source_movable_joints']), (3, 2, 1))
        self.assertEqual([body.get('name') for body in root.findall('.//body')],
                         ['base_link', 'upper_shell_link', 'leg_link'])
        self.assertEqual(len(root.findall('.//freejoint')), 1)
        self.assertEqual(len(root.findall('.//joint')), 1)
        self.assertEqual(root.find(".//body[@name='leg_link']/joint").get('user'), '1.5 42')
        self.assertEqual(root.find(".//body[@name='leg_link']/inertial").get('fullinertia'),
                         '0.01 0.02 0.03 0.001 0.002 0.003')
        upper = root.find(".//body[@name='upper_shell_link']")
        self.assertIsNone(upper.find('joint'))
        self.assertEqual({geom.get('mesh') for geom in upper.findall('geom')},
                         {'upper_shell_link'})
        self.assertEqual({geom.get('group') for geom in upper.findall('geom')}, {'2', '3'})
        self.assertEqual(root.find('compiler').get('fusestatic'), 'false')

    def test_synthetic_source_mismatch_is_rejected(self):
        with self.assertRaisesRegex(PackageError, 'Visual/collision'):
            convert_urdf(small_urdf(collision_file='different.stl'))
        with self.assertRaisesRegex(PackageError, 'Invalid.*effort|Invalid limits'):
            convert_urdf(small_urdf(effort='0'))

    def test_current_jumper_source_and_native_adapter_match(self):
        package = ROOT / 'robots/jumper'
        if not (package / 'profile.json').is_file():
            self.skipTest('Jumper source profile is not installed')
        profile = json.loads((package / 'profile.json').read_text(encoding='utf-8'))
        report = json.loads((package / 'import-report.json').read_text(encoding='utf-8'))
        source_bytes = (package / 'urdf/jumper.urdf').read_bytes()
        source = ET.fromstring(source_bytes)
        native = ET.fromstring((package / 'baseline.xml').read_bytes())
        self.assertEqual(profile['id'], 'jumper')
        self.assertEqual(profile['source']['source_urdf_sha256'], sha(source_bytes))
        self.assertEqual(profile['parent_link'], 'upper_shell_link')
        self.assertEqual((len(source.findall('link')), len(source.findall('joint'))), (41, 40))
        self.assertEqual(len([j for j in source.findall('joint') if j.get('type') == 'revolute']), 22)
        self.assertEqual([j.get('name') for j in source.findall('joint')],
                         profile['source_joint_order'])
        self.assertEqual({b.get('name') for b in native.findall('.//body')},
                         {l.get('name') for l in source.findall('link')})
        self.assertEqual(len(native.findall('.//joint')), 22)
        self.assertEqual(len(native.findall('.//freejoint')), 1)
        self.assertEqual(len(native.findall('asset/mesh')), 41)
        self.assertEqual((len(native.findall('.//sensor')), len(native.findall('.//camera'))),
                         (0, 0))
        for link in source.findall('link'):
            name = link.get('name')
            body = next(b for b in native.findall('.//body') if b.get('name') == name)
            visual = body.find("geom[@name='" + name + "_visual']")
            collision = body.find("geom[@name='" + name + "_collision']")
            self.assertEqual((visual.get('mesh'), collision.get('mesh')), (name, name))
            self.assertEqual((visual.get('group'), collision.get('group')), ('2', '3'))
            self.assertEqual(float(body.find('inertial').get('mass')),
                             float(link.find('inertial/mass').get('value')))
            tensor = link.find('inertial/inertia')
            expected = [tensor.get(key) for key in ('ixx', 'iyy', 'izz', 'ixy', 'ixz', 'iyz')]
            self.assertEqual(body.find('inertial').get('fullinertia').split(), expected)
            self.assertEqual(visual.get('rgba'), link.find('visual/material/color').get('rgba'))
        self.assertEqual(float(next(b for b in native.findall('.//body')
                                    if b.get('name') == 'base_link').find('inertial').get('mass')),
                         0.886006064277726)
        self.assertFalse(report['six_hole_interface_validated'])
        self.assertFalse(profile['physical_fit_tested'])
        pose = json.loads((package / 'preview-pose.json').read_text(encoding='utf-8'))
        packaged_audit_bytes = (package / 'source-audit.json').read_bytes()
        self.assertEqual(report['source_audit_sha256'], sha(packaged_audit_bytes))
        self.assertEqual(pose['source_audit_sha256'], sha(packaged_audit_bytes))
        self.assertRegex(report['external_source_audit_sha256'], r'^[0-9a-f]{64}$')
        self.assertNotEqual(report['external_source_audit_sha256'],
                            report['source_audit_sha256'])
        self.assertIsNone(re.search(rb'(?i)[a-z]:[\\/]', packaged_audit_bytes))
        self.assertEqual(json.loads(packaged_audit_bytes)['path_reference_basis'],
                         'robot-shell-workflow repository root')
        self.assertEqual(pose['joints']['LM_J0_joint'], 0.0012)
        self.assertEqual(pose['joints']['RF_J4_joint'], 0.1)
        self.assertEqual(set(pose['joints']),
                         {j.get('name') for j in source.findall('joint')
                          if j.get('type') == 'revolute'})
        self.assertEqual(set(report['preview_pose_mapping']['corrections']),
                         {'RF_J4_joint'})
        for rec in profile['files']:
            path = package / rec['path']
            if path.suffix.lower() == '.stl' and path.read_bytes().startswith(b'version https://git-lfs'):
                continue  # CI without LFS payloads still checks source XML semantics.
            self.assertEqual((sha(path.read_bytes()), path.stat().st_size),
                             (rec['sha256'], rec['bytes']))


if __name__ == '__main__':
    unittest.main()
