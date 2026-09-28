"""Integration guards for the optional producer, using tiny synthetic assets."""
from pathlib import Path
import importlib.util
import json
import tempfile
import unittest
import zipfile
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

AVAILABLE = all(importlib.util.find_spec(name) for name in ('numpy', 'scipy', 'trimesh', 'mujoco', 'fast_simplification', 'rtree'))
if AVAILABLE:
    import numpy as np
    import trimesh
    from shellflow import simulation as sim


@unittest.skipUnless(AVAILABLE, 'optional sim dependencies are not installed')
class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile_root = self.root / 'profile'
        (self.profile_root / 'meshes').mkdir(parents=True)
        self.shell = self.root / 'shell.stl'
        box = trimesh.creation.box(extents=[180, 200, 60])
        box.apply_translation([0, 0, 60])
        box.export(self.shell)
        self.mesh = trimesh.load_mesh(self.shell, process=True)
        baseline_box = trimesh.creation.box(extents=[.18, .2, .02])
        for name in ('base.stl', 'lower.stl'):
            baseline_box.export(self.profile_root / 'meshes' / name)
        xml = '''<mujoco><compiler angle="radian" meshdir="meshes/"/>
        <asset><mesh name="base" file="base.stl"/></asset>
        <worldbody><body name="base_link"><joint name="floating_base" type="free"/>
        <inertial mass="1" pos="0 0 0" diaginertia=".01 .01 .01"/>
        <geom name="base_link_visual" type="mesh" mesh="base" contype="0" conaffinity="0"/>
        <geom name="base_collision" type="box" size=".09 .1 .01"/>
        <body name="leg" pos=".1 0 0"><joint name="leg_joint" axis="0 1 0" range="-1 1" actuatorfrcrange="-2 2"/>
        <inertial mass=".1" pos="0 0 -.03" diaginertia=".001 .001 .001"/>
        <geom name="leg_collision" type="box" size=".01 .01 .04"/></body>
        </body></worldbody></mujoco>'''
        (self.profile_root / 'baseline.xml').write_text(xml, encoding='utf-8')
        (self.profile_root / 'seam.json').write_text(json.dumps({'points': self.mesh.vertices.tolist()}))
        files = [dict(path=p.relative_to(self.profile_root).as_posix(), sha256=sim.sha(p), bytes=p.stat().st_size)
                 for p in self.profile_root.rglob('*') if p.is_file()]
        profile = dict(schema_version=1, files=files, baseline_mjcf='baseline.xml', lower_visual_mesh='meshes/lower.stl',
                       source_base_visual='base_link_visual', parent_link='base_link', seam_reference='seam.json',
                       source_step_sha256='0' * 64, cad_mm_to_base_m=dict(scale=.001, rotation_matrix=np.eye(3).tolist(), translation_m=[0, 0, 0]))
        self.profile = self.profile_root / 'profile.json'
        self.profile.write_text(json.dumps(profile))

    def test_real_export_preserves_source_and_joint_tree(self):
        before = sim.sha(self.shell)
        output = self.root / 'assembled'
        result = sim.assemble(self.shell, output, self.profile, faces=1000)
        self.assertTrue(result['ok'])
        self.assertEqual(sim.sha(self.shell), before)
        report = json.loads((output / 'simulation-report.json').read_text())
        self.assertTrue(report['urdf_verification']['passed'])
        self.assertEqual(report['urdf_load']['joints'], 2)
        self.assertFalse(report['physical_dynamics_validated'])
        self.assertFalse(report['physical_fit_tested'])
        self.assertEqual(report['collision_policy'], 'baseline_preserved')
        for record in report['files']:
            self.assertEqual(sim.sha(output / record['path']), record['sha256'])
        with self.assertRaises(FileExistsError):
            sim.assemble(self.shell, output, self.profile)

    def test_lower_shell_color_changes_only_visual_and_reports_it(self):
        original = sim.sha(self.shell)
        baseline = sim.sha(self.profile_root / 'baseline.xml')
        output = self.root / 'recolored'
        sim.assemble(self.shell, output, self.profile, faces=1000,
                     lower_shell_color='#123456')
        self.assertEqual(sim.sha(self.shell), original)
        self.assertEqual(sim.sha(self.profile_root / 'baseline.xml'), baseline)
        report = json.loads((output / 'simulation-report.json').read_text())
        self.assertEqual(report['visual_overrides'], [
            {'link': 'base_link', 'geom': 'base_link_visual',
             'rgba': [18 / 255, 52 / 255, 86 / 255, 1.0]}])
        result = ET.parse(output / 'robot.xml').getroot()
        lower = result.find(".//body[@name='base_link']/geom[@name='base_link_visual']")
        self.assertEqual([float(x) for x in lower.get('rgba').split()],
                         report['visual_overrides'][0]['rgba'])
        self.assertIsNone(result.find(".//body[@name='leg']/geom[@name='leg_collision']").get('rgba'))
        with self.assertRaisesRegex(ValueError, '#RRGGBB'):
            sim.assemble(self.shell, self.root / 'invalid-color', self.profile,
                         lower_shell_color='red')

    def test_wrong_frame_rejected_without_output(self):
        moved = self.mesh.copy()
        moved.apply_translation([100, 0, 0])
        moved.export(self.shell)
        output = self.root / 'bad-frame'
        with self.assertRaisesRegex(ValueError, 'seam'):
            sim.assemble(self.shell, output, self.profile)
        self.assertFalse(output.exists())

    def test_smoke_pose_respects_authored_nonzero_joint_lower_bound(self):
        baseline = self.profile_root / 'baseline.xml'
        baseline.write_text(baseline.read_text().replace('range="-1 1"', 'range="0.75 1"'),
                            encoding='utf-8')
        before = baseline.read_bytes()
        result = sim.compare_compiled(baseline, baseline)
        self.assertTrue(result['passed'])
        self.assertEqual(result['smoke_pose_corrections']['leg_joint'],
                         {'before': 0.0, 'after': 0.75})
        self.assertEqual(baseline.read_bytes(), before)

    def test_dedicated_shell_link_keeps_lower_body_and_full_robot(self):
        baseline_path = self.profile_root / 'baseline.xml'
        xml = ET.parse(baseline_path).getroot()
        base = xml.find(".//body[@name='base_link']")
        shell_body = ET.SubElement(base, 'body', name='shangke_link', pos='0 0 .03')
        ET.SubElement(shell_body, 'inertial', mass='.1', pos='0 0 .01', diaginertia='.001 .001 .001')
        ET.SubElement(shell_body, 'geom', name='old_upper_visual', type='mesh', mesh='base',
                      contype='0', conaffinity='0')
        ET.SubElement(shell_body, 'geom', name='upper_collision', type='box', size='.08 .08 .01')
        sim.write_xml(baseline_path, xml)
        profile = json.loads(self.profile.read_text())
        profile['parent_link'] = 'shangke_link'
        profile['visual_replacement'] = dict(mode='dedicated_link', geom_name='old_upper_visual')
        profile['cad_mm_to_parent_m'] = profile.pop('cad_mm_to_base_m')
        profile.pop('lower_visual_mesh')
        profile.pop('source_base_visual')
        for record in profile['files']:
            path = self.profile_root / record['path']
            record.update(sha256=sim.sha(path), bytes=path.stat().st_size)
        self.profile.write_text(json.dumps(profile))
        output = self.root / 'dedicated'
        sim.assemble(self.shell, output, self.profile, faces=1000)
        result = ET.parse(output / 'robot.xml').getroot()
        self.assertEqual(result.find(".//geom[@name='base_link_visual']").get('mesh'), 'base')
        self.assertIsNone(result.find(".//geom[@name='old_upper_visual']"))
        self.assertIsNotNone(result.find(".//body[@name='shangke_link']/geom[@name='shellflow_upper_0']"))
        self.assertIsNotNone(result.find(".//geom[@name='upper_collision']"))
        report = json.loads((output / 'simulation-report.json').read_text())
        self.assertEqual(report['whole_robot']['robot_links'], 3)
        self.assertEqual(report['whole_robot']['movable_joints'], 1)
        self.assertEqual(report['whole_robot']['native_actuators'], 0)
        self.assertEqual(report['transform_target_link'], 'shangke_link')

    def test_shell_only_urdf_cannot_pass_whole_robot_contract(self):
        output = self.root / 'full'
        sim.assemble(self.shell, output, self.profile, faces=1000)
        whole = output / 'robot.urdf'
        self.assertTrue(sim.verify_whole_robot(self.profile_root / 'baseline.xml', whole, 'base_link')['passed'])
        tree = ET.parse(whole)
        root = tree.getroot()
        root.remove(root.find("link[@name='leg']"))
        tree.write(whole)
        with self.assertRaisesRegex(ValueError, 'Full-robot'):
            sim.verify_whole_robot(self.profile_root / 'baseline.xml', whole, 'base_link')

    def test_profile_asset_tampering_is_rejected(self):
        (self.profile_root / 'meshes/base.stl').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            sim.verify_profile(self.profile)

    def test_profile_path_cannot_escape(self):
        # Build a synthetic Windows path without storing a machine path literal.
        windows_absolute = 'x:' + chr(92) + 'outside'
        for value in ('../escape', '/absolute', windows_absolute):
            with self.subTest(value=value), self.assertRaises(ValueError):
                sim.relative_file(self.profile_root, value)

    def ams(self, change=False):
        path = self.root / 'ams.3mf'
        vertices = self.mesh.vertices.copy()
        if change:
            vertices[0, 0] += 1
        ns = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
        prod = 'http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
        main = f'<model xmlns="{ns}" xmlns:p="{prod}" unit="millimeter"><resources><object><components><component p:path="/3D/object.model"/></components></object></resources><build><item transform="1 0 0 0 1 0 0 0 1 100 100 -30"/></build></model>'
        obj = f'<model xmlns="{ns}"><resources><object><mesh><vertices>'
        obj += ''.join(f'<vertex x="{x}" y="{y}" z="{z}"/>' for x, y, z in vertices)
        obj += '</vertices><triangles>'
        obj += ''.join(f'<triangle v1="{a}" v2="{b}" v3="{c}" paint_color="4"/>' for a, b, c in self.mesh.faces)
        obj += '</triangles></mesh></object></resources></model>'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('Metadata/project_settings.config', json.dumps({'filament_colour': ['#123456', '#FFFFFF', '#FF0000', '#000000']}))
            archive.writestr('3D/3dmodel.model', main)
            archive.writestr('3D/object.model', obj)
        return path

    def test_color_transfer_uses_cad_geometry_not_build_plate_translation(self):
        colors, palette = sim.colors_from_ams(self.ams(), self.mesh)
        self.assertEqual(len(colors), len(self.mesh.faces))
        self.assertEqual(palette[0], '#123456')
        with self.assertRaisesRegex(ValueError, 'exactly match'):
            sim.colors_from_ams(self.ams(change=True), self.mesh)

    def test_limb_visual_overrides_are_explicit_and_do_not_touch_collision(self):
        xml = ET.fromstring('<mujoco><worldbody><body name="leg"><geom name="visual" contype="0" conaffinity="0" rgba="1 0 0 1"/><geom name="collision" type="box" size="1 1 1"/></body></worldbody></mujoco>')
        collision = ET.tostring(xml.find('.//geom[@name="collision"]'))
        record = dict(link='leg', geom='visual', rgba=[.1, .2, .3, 1.0])
        sim.apply_visual_overrides(xml, [record], 'upper')
        self.assertEqual(xml.find('.//geom[@name="visual"]').get('rgba'), '0.1 0.2 0.3 1.0')
        self.assertEqual(ET.tostring(xml.find('.//geom[@name="collision"]')), collision)
        for bad in ([dict(record, geom='collision')], [dict(record, link='upper')],
                    [dict(record, rgba=[1, 0, 0, .5])], [dict(record, rgba=[float('nan'), 0, 0, 1])],
                    [record, record]):
            with self.subTest(overrides=bad), self.assertRaises(ValueError):
                sim.apply_visual_overrides(xml, bad, 'upper')
