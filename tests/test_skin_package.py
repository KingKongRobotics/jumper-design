"""Small full-robot fixtures for the portable .skin contract."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from shellflow import skin_package as skin
from shellflow.package_io import PackageError, read_archive, file_records
from test_package_preview import png
from shellflow.urdf import export_urdf


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


class SkinPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        old_tempdir = tempfile.tempdir
        tempfile.tempdir = self.root
        self.addCleanup(setattr, tempfile, 'tempdir', old_tempdir)
        self.platform = self.root / 'platform'
        (self.platform / 'meshes').mkdir(parents=True)
        (self.platform / 'meshes' / 'base.stl').write_bytes(b'baseline mesh')
        self.shell = self.root / 'shell.stl'
        self.shell.write_bytes(b'original millimeter shell bytes')
        self.baseline = self.platform / 'baseline.xml'
        self.baseline.write_text('''<mujoco model="sample"><compiler angle="radian" meshdir="meshes/"/>
          <asset><mesh name="base" file="base.stl"/></asset>
          <worldbody><body name="base_link"><joint name="floating_base" type="free"/>
            <inertial mass="1" pos="0 0 0" diaginertia=".01 .01 .01"/>
            <geom name="base_link_visual" type="mesh" mesh="base" contype="0" conaffinity="0"/>
            <geom name="base_collision" type="box" size=".1 .1 .01"/>
            <body name="leg" pos=".1 0 0"><joint name="leg_joint" axis="0 1 0" range="-1 1" actuatorfrcrange="-2 2"/>
              <inertial mass=".1" pos="0 0 0" diaginertia=".001 .001 .001"/>
              <geom name="leg_visual" type="box" size=".01 .01 .04" contype="0" conaffinity="0"/>
              <geom name="leg_collision" type="box" size=".01 .01 .04"/></body>
            <body name="shangke_link" pos="0 0 .02">
              <inertial mass=".1" pos="0 0 0" diaginertia=".001 .001 .001"/>
              <geom name="old_upper_visual" type="mesh" mesh="base" contype="0" conaffinity="0"/>
              <geom name="upper_collision" type="box" size=".08 .08 .01"/></body>
          </body></worldbody><sensor><framepos name="pose" objtype="body" objname="leg"/></sensor></mujoco>''', encoding='utf-8')
        profile = {'schema_version': 1, 'id': 'jumper-v1-6',
                   'mechanical_platform': 'original-robot-v1',
                   'source_step_sha256': 'a' * 64, 'baseline_mjcf': 'baseline.xml',
                   'parent_link': 'shangke_link',
                   'visual_replacement': {'mode': 'dedicated_link', 'geom_name': 'old_upper_visual'},
                   'cad_mm_to_parent_m': {'scale': .001, 'rotation_matrix': [[1, 0, 0], [0, 1, 0], [0, 0, 1]], 'translation_m': [0, 0, 0]},
                   'collision_policy': 'baseline_preserved', 'inertia_policy': 'baseline_preserved',
                   'files': []}
        for name in ('baseline.xml', 'meshes/base.stl'):
            data = (self.platform / name).read_bytes()
            profile['files'].append({'path': name, 'bytes': len(data), 'sha256': sha(data)})
        self.profile = self.platform / 'profile.json'
        self.profile.write_bytes(encoded(profile))
        self.simulation = self.root / 'simulation'
        (self.simulation / 'meshes').mkdir(parents=True)
        (self.simulation / 'meshes' / 'base.stl').write_bytes((self.platform / 'meshes/base.stl').read_bytes())
        (self.simulation / 'meshes' / 'upper_shell_0.stl').write_bytes(b'visual shell mesh')
        assembled = ET.parse(self.baseline).getroot()
        parent = assembled.find(".//body[@name='shangke_link']")
        parent.remove(parent.find("geom[@name='old_upper_visual']"))
        ET.SubElement(assembled.find('asset'), 'mesh', name='shellflow_upper_0', file='upper_shell_0.stl')
        ET.SubElement(parent, 'geom', name='shellflow_upper_0', type='mesh', mesh='shellflow_upper_0',
                      contype='0', conaffinity='0', density='0', group='2', rgba='.5 .5 .5 1')
        ET.ElementTree(assembled).write(self.simulation / 'robot.xml', encoding='utf-8')
        export_urdf(self.simulation / 'robot.xml', self.simulation / 'robot.urdf')
        (self.simulation / 'scene.xml').write_text('<mujoco><include file="robot.xml"/></mujoco>')
        simulation_files = []
        for path in self.simulation.rglob('*'):
            if path.is_file():
                data = path.read_bytes()
                simulation_files.append({'path': path.relative_to(self.simulation).as_posix(),
                                         'bytes': len(data), 'sha256': sha(data)})
        report = {'schema_version': 1, 'passed': True, 'files': simulation_files,
                  'source_shell_sha256': sha(self.shell.read_bytes()),
                  'source_shell_frame': 'original-robot-v1 CAD millimeters Z-up',
                  'robot_profile_sha256': sha(self.profile.read_bytes()),
                  'source_step_sha256': 'a' * 64,
                  'source_baseline_mjcf_sha256': sha(self.baseline.read_bytes()),
                  'robot_profile_id': 'jumper-v1-6', 'transform_target_link': 'shangke_link',
                  'visual_replacement_mode': 'dedicated_link',
                  'transform': profile['cad_mm_to_parent_m'],
                  'whole_robot': {'scope': 'full_robot', 'robot_links': 3,
                                  'movable_joints': 1, 'shell_parent_link': 'shangke_link'},
                  'collision_policy': 'baseline_preserved', 'inertia_policy': 'baseline_preserved',
                  'physical_fit_tested': False, 'physical_dynamics_validated': False,
                  'producer_code_sha256': {'simulation.py': 'b' * 64}}
        (self.simulation / 'simulation-report.json').write_bytes(encoded(report))
        self.output = self.root / 'sample.skin'

    def package(self):
        result = skin.export_skin(self.simulation, self.profile, self.shell, self.output,
                                  package_id='sample', title='Sample robot skin')
        self.assertTrue(result['ok'])
        return read_archive(self.output)

    def legacy_package(self, files, version):
        manifest = json.loads(files[skin.MANIFEST])
        report_path = 'assembled/jumper-v1-6/simulation-report.json'
        report = json.loads(files[report_path])
        if version == 1:
            report.pop('visual_overrides')
            manifest.pop('visual_overrides')
        files[report_path] = encoded(report)
        manifest['source']['report_sha256'] = sha(files[report_path])
        manifest['schema'] = skin.SCHEMA if version == 1 else skin.SCHEMA_V2
        files['print/shell.stl'] = self.shell.read_bytes()
        manifest['manufacturing'] = {'status': 'source_provided_unverified',
                                     'shell_path': 'print/shell.stl', 'ams_path': None,
                                     'preview_path': None}
        manifest['files'] = file_records({k: v for k, v in files.items() if k != skin.MANIFEST})
        files[skin.MANIFEST] = encoded(manifest)
        return files

    def resign(self, files):
        manifest = json.loads(files[skin.MANIFEST])
        manifest['files'] = file_records({k: v for k, v in files.items() if k != skin.MANIFEST})
        files[skin.MANIFEST] = encoded(manifest)

    def resign_model(self, files, changed):
        report_path = 'assembled/jumper-v1-6/simulation-report.json'
        report = json.loads(files[report_path])
        relative = changed.removeprefix('assembled/jumper-v1-6/')
        record = next(r for r in report['files'] if r['path'] == relative)
        record.update(bytes=len(files[changed]), sha256=sha(files[changed]))
        files[report_path] = encoded(report)
        manifest = json.loads(files[skin.MANIFEST])
        manifest['source']['report_sha256'] = sha(files[report_path])
        manifest['files'] = file_records({k: v for k, v in files.items() if k != skin.MANIFEST})
        files[skin.MANIFEST] = encoded(manifest)

    def test_deterministic_roundtrip_and_trusted_profile(self):
        files = self.package()
        self.assertEqual(skin.validate(files, platform_profile=self.profile)['whole_robot']['robot_links'], 3)
        self.assertFalse(skin.validate(files)['trusted_platform_profile'])
        other = self.root / 'same.skin'
        skin.export_skin(self.simulation, self.profile, self.shell, other,
                         package_id='sample', title='Sample robot skin')
        self.assertEqual(self.output.read_bytes(), other.read_bytes())

    def test_export_embeds_preview_and_rejects_missing_preview(self):
        preview = self.root / 'thumbnail.png'
        preview.write_bytes(png())
        skin.export_skin(self.simulation, self.profile, self.shell, self.output,
                         package_id='sample', title='Sample robot skin', preview=preview)
        files = read_archive(self.output)
        manifest = json.loads(files[skin.MANIFEST])
        self.assertNotIn('preview', manifest)
        self.assertEqual(files['preview/preview.png'], png())
        self.assertEqual(manifest['files']['preview/preview.png']['sha256'], sha(png()))
        skin.validate(files, platform_profile=self.profile)
        del files['preview/preview.png']
        with self.assertRaises(PackageError):
            skin.validate(files, platform_profile=self.profile)

    def recolored_package(self):
        declaration = [{'link': 'base_link', 'geom': 'base_link_visual',
                        'rgba': [18 / 255, 52 / 255, 86 / 255, 1.0]}]
        robot_path = self.simulation / 'robot.xml'
        robot = ET.parse(robot_path)
        robot.find(".//body[@name='base_link']/geom[@name='base_link_visual']").set(
            'rgba', ' '.join(map(str, declaration[0]['rgba'])))
        robot.write(robot_path, encoding='utf-8')
        (self.simulation / 'robot.urdf').unlink()
        export_urdf(robot_path, self.simulation / 'robot.urdf')
        report_path = self.simulation / 'simulation-report.json'
        report = json.loads(report_path.read_bytes())
        report['visual_overrides'] = declaration
        for rec in report['files']:
            if rec['path'] in {'robot.xml', 'robot.urdf'}:
                data = (self.simulation / rec['path']).read_bytes()
                rec.update(bytes=len(data), sha256=sha(data))
        report_path.write_bytes(encoded(report))
        return self.package()

    def test_v3_recolor_roundtrip_and_trusted_profile(self):
        from shellflow.packages import verify_package, import_package, repack_package

        files = self.recolored_package()
        manifest = json.loads(files[skin.MANIFEST])
        self.assertEqual(manifest['schema'], skin.SCHEMA_V3)
        self.assertEqual(manifest['visual_overrides'][0]['geom'], 'base_link_visual')
        schema = json.loads((Path(__file__).resolve().parents[1] /
                             'schemas/skin-package-v3.schema.json').read_text(encoding='utf-8'))
        try:
            import jsonschema
        except ImportError:
            pass
        else:
            jsonschema.validate(manifest, schema)
        verified = verify_package(self.output, platform_profile=self.profile)
        self.assertEqual(verified['schema'], skin.SCHEMA_V3)
        destination = self.root / 'v3-imported'
        import_package(self.output, destination, platform_profile=self.profile)
        self.assertFalse((destination / 'print').exists())
        other = self.root / 'v3-returned.skin'
        repack_package(self.output, other, platform_profile=self.profile)
        self.assertEqual(other.read_bytes(), self.output.read_bytes())

    def test_v3_multiple_visual_parts_and_display_only(self):
        declaration = [
            {'link': 'base_link', 'geom': 'base_link_visual', 'rgba': [.1, .2, .3, 1]},
            {'link': 'leg', 'geom': 'leg_visual', 'rgba': [.8, .1, .2, 1]},
        ]
        robot_path = self.simulation / 'robot.xml'
        robot = ET.parse(robot_path)
        for entry in declaration:
            target = robot.find(f".//body[@name='{entry['link']}']/geom[@name='{entry['geom']}']")
            target.set('rgba', ' '.join(map(str, entry['rgba'])))
        robot.write(robot_path, encoding='utf-8')
        (self.simulation / 'robot.urdf').unlink()
        export_urdf(robot_path, self.simulation / 'robot.urdf')
        report_path = self.simulation / 'simulation-report.json'
        report = json.loads(report_path.read_bytes())
        report['visual_overrides'] = declaration
        for rec in report['files']:
            if rec['path'] in {'robot.xml', 'robot.urdf'}:
                data = (self.simulation / rec['path']).read_bytes()
                rec.update(bytes=len(data), sha256=sha(data))
        report_path.write_bytes(encoded(report))
        files = self.package()
        self.assertEqual(json.loads(files[skin.MANIFEST])['visual_overrides'], declaration)
        self.assertFalse(any(name.startswith('print/') for name in files))
        self.assertEqual(skin.validate(files, platform_profile=self.profile)['schema'], skin.SCHEMA_V3)
        files['print/ams.3mf'] = b'print content'
        self.resign(files)
        with self.assertRaisesRegex(PackageError, 'unsupported path'):
            skin.validate(files)

    def test_v3_works_without_print_input_and_checks_optional_shell(self):
        skin.export_skin(self.simulation, self.profile, None, self.output,
                         package_id='sample', title='Sample robot skin')
        files = read_archive(self.output)
        self.assertEqual(json.loads(files[skin.MANIFEST])['source']['shell_sha256'],
                         sha(self.shell.read_bytes()))
        wrong_shell = self.root / 'wrong.stl'
        wrong_shell.write_bytes(b'wrong')
        with self.assertRaisesRegex(PackageError, 'Supplied shell differs'):
            skin.export_skin(self.simulation, self.profile, wrong_shell,
                             self.root / 'wrong.skin', package_id='sample', title='Sample')

    def test_v3_rejects_print_file_disguised_as_unreferenced_mesh(self):
        files = self.package()
        path = 'assembled/jumper-v1-6/meshes/print-shell.stl'
        files[path] = b'full resolution print source'
        report_path = 'assembled/jumper-v1-6/simulation-report.json'
        report = json.loads(files[report_path])
        report['files'].append({'path': 'meshes/print-shell.stl',
                                'bytes': len(files[path]), 'sha256': sha(files[path])})
        files[report_path] = encoded(report)
        manifest = json.loads(files[skin.MANIFEST])
        manifest['source']['report_sha256'] = sha(files[report_path])
        manifest['files'] = file_records({name: data for name, data in files.items()
                                         if name != skin.MANIFEST})
        files[skin.MANIFEST] = encoded(manifest)
        with self.assertRaisesRegex(PackageError, 'Unreferenced mesh or print asset'):
            skin.validate(files, platform_profile=self.profile)

    def test_v3_rejects_collision_upper_and_duplicate_override_targets(self):
        baseline = ET.parse(self.baseline).getroot()
        robot = ET.parse(self.simulation / 'robot.xml').getroot()
        valid = {'link': 'leg', 'geom': 'leg_visual', 'rgba': [.2, .3, .4, 1]}
        robot.find(".//body[@name='leg']/geom[@name='leg_visual']").set('rgba', '.2 .3 .4 1')
        for declaration, message in (
            ([valid, valid], 'duplicated'),
            ([{'link': 'leg', 'geom': 'leg_collision', 'rgba': [.2, .3, .4, 1]}], 'not a visual'),
            ([{'link': 'shangke_link', 'geom': 'old_upper_visual', 'rgba': [.2, .3, .4, 1]}],
             'upper shell'),
            ([{'link': 'leg', 'geom': 'leg_visual', 'rgba': [.2, .3, .4, 0]}], 'opaque alpha'),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(PackageError, message):
                skin._check_visual_overrides(declaration, baseline, robot,
                                             parent_link='shangke_link', schema=skin.SCHEMA_V3)
        baseline.find(".//body[@name='leg']/geom[@name='leg_visual']").set('class', 'visual')
        baseline.find(".//body[@name='leg']/geom[@name='leg_visual']").set('contype', '1')
        with self.assertRaisesRegex(PackageError, 'not a visual geom'):
            skin._check_visual_overrides([valid], baseline, robot,
                                         parent_link='shangke_link', schema=skin.SCHEMA_V3)

    def test_v3_split_base_lower_visual_may_share_upper_parent_link(self):
        baseline = ET.fromstring('''<mujoco><worldbody><body name="base_link">
            <geom name="shell" class="visual" contype="0" conaffinity="0"/>
            </body></worldbody></mujoco>''')
        robot = copy.deepcopy(baseline)
        robot.find('.//geom').set('rgba', '.1 .2 .3 1')
        skin._check_visual_overrides(
            [{'link': 'base_link', 'geom': 'shell', 'rgba': [.1, .2, .3, 1]}],
            baseline, robot, parent_link='base_link', schema=skin.SCHEMA_V3,
            upper_slot={'mode': 'split_base', 'geom_name': 'shell'})
        self.assertNotIn('rgba', robot.find('.//geom').attrib)

    def test_legacy_v1_and_v2_remain_readable(self):
        original = self.package()
        self.assertEqual(skin.validate(self.legacy_package(original, 1),
                                       platform_profile=self.profile)['schema'], skin.SCHEMA)
        self.output.unlink()
        recolored = self.recolored_package()
        self.assertEqual(skin.validate(self.legacy_package(recolored, 2),
                                       platform_profile=self.profile)['schema'], skin.SCHEMA_V2)

    def test_v3_rejects_undeclared_or_forged_changes(self):
        files = self.recolored_package()
        manifest = json.loads(files[skin.MANIFEST])
        manifest['visual_overrides'][0]['geom'] = 'leg_collision'
        files[skin.MANIFEST] = encoded(manifest)
        with self.assertRaisesRegex(PackageError, 'Visual override'):
            skin.validate(files, platform_profile=self.profile)
        files = read_archive(self.output)
        manifest = json.loads(files[skin.MANIFEST])
        manifest['visual_overrides'][0]['rgba'][0] = 2.0
        files[skin.MANIFEST] = encoded(manifest)
        with self.assertRaisesRegex(PackageError, 'Visual override'):
            skin.validate(files, platform_profile=self.profile)
        files = read_archive(self.output)
        path = 'assembled/jumper-v1-6/robot.xml'
        robot = ET.fromstring(files[path])
        robot.find(".//body[@name='leg']/geom[@name='leg_collision']").set('rgba', '1 0 0 1')
        files[path] = ET.tostring(robot)
        self.resign_model(files, path)
        with self.assertRaisesRegex(PackageError, 'undeclared joints, inertias'):
            skin.validate(files, platform_profile=self.profile)
        files = read_archive(self.output)
        manifest = json.loads(files[skin.MANIFEST])
        del manifest['visual_overrides']
        files[skin.MANIFEST] = encoded(manifest)
        with self.assertRaisesRegex(PackageError, 'manifest field'):
            skin.validate(files)

    def test_nested_mesh_directory_stays_within_packaged_assets(self):
        for directory in ('meshes', 'meshes/', 'meshes/visual/'):
            skin._check_xml_safety(ET.fromstring(
                f'<mujoco><compiler meshdir="{directory}"/></mujoco>'))
        for directory in ('../meshes', 'meshes/../outside', 'assets/meshes', '/meshes'):
            with self.subTest(directory=directory), self.assertRaises(PackageError):
                skin._check_xml_safety(ET.fromstring(
                    f'<mujoco><compiler meshdir="{directory}"/></mujoco>'))

    def test_file_tamper_and_source_report_mismatch(self):
        files = self.package()
        files['assembled/jumper-v1-6/meshes/upper_shell_0.stl'] += b'!'
        with self.assertRaisesRegex(PackageError, 'SHA256'):
            skin.validate(files)
        self.resign(files)
        with self.assertRaisesRegex(PackageError, 'inventory'):
            skin.validate(files)

    def test_missing_resource_and_shell_only_urdf(self):
        files = self.package()
        del files['assembled/jumper-v1-6/meshes/base.stl']
        self.resign(files)
        with self.assertRaisesRegex(PackageError, 'baseline mesh|resource'):
            skin.validate(files, platform_profile=self.profile)
        files = read_archive(self.output)
        path = 'assembled/jumper-v1-6/robot.urdf'
        urdf = ET.fromstring(files[path])
        urdf.remove(urdf.find("link[@name='leg']"))
        files[path] = ET.tostring(urdf)
        self.resign_model(files, path)
        with self.assertRaisesRegex(PackageError, 'Full-robot URDF'):
            skin.validate(files)

    def test_rejects_undeclared_physical_changes_even_when_resigned(self):
        files = self.package()
        path = 'assembled/jumper-v1-6/robot.xml'
        robot = ET.fromstring(files[path])
        robot.find(".//body[@name='leg']/inertial").set('mass', '9')
        files[path] = ET.tostring(robot)
        self.resign_model(files, path)
        with self.assertRaisesRegex(PackageError, 'undeclared joints, inertias'):
            skin.validate(files)

    def test_unsupported_profile_and_policy(self):
        files = self.package()
        manifest = json.loads(files[skin.MANIFEST])
        manifest['platform']['id'] = 'other-v1'
        files[skin.MANIFEST] = encoded(manifest)
        with self.assertRaisesRegex(PackageError, 'unsupported path'):
            skin.validate(files)
        files = read_archive(self.output)
        with self.assertRaisesRegex(PackageError, 'capability'):
            skin.validate(files, capabilities={'hexa-v1'})
        manifest = json.loads(files[skin.MANIFEST])
        manifest['physical_fit_tested'] = True
        files[skin.MANIFEST] = encoded(manifest)
        with self.assertRaisesRegex(PackageError, 'certification'):
            skin.validate(files)

    def test_wrong_trusted_platform_profile_is_rejected(self):
        files = self.package()
        wrong = self.platform / 'wrong-profile.json'
        value = json.loads(self.profile.read_bytes())
        value['id'] = 'other-robot-v1'
        wrong.write_bytes(encoded(value))
        with self.assertRaisesRegex(PackageError, 'trusted robot profile'):
            skin.validate(files, platform_profile=wrong)

    def test_data_only_namespaces_and_xml_references(self):
        files = self.package()
        files['evil.py'] = b'print(1)'
        self.resign(files)
        with self.assertRaisesRegex(PackageError, 'unsupported path'):
            skin.validate(files)
        files = read_archive(self.output)
        path = 'assembled/jumper-v1-6/scene.xml'
        scene = ET.fromstring(files[path])
        ET.SubElement(scene, 'extension')
        files[path] = ET.tostring(scene)
        self.resign_model(files, path)
        with self.assertRaisesRegex(PackageError, 'unsupported model or extension|plugins/extensions'):
            skin.validate(files)
        with self.assertRaisesRegex(PackageError, 'includes/plugins/extensions'):
            skin._check_xml_safety(ET.fromstring('<mujoco><include file="outside.xml"/></mujoco>'))

    def test_preview_script_omission_is_explicit(self):
        (self.simulation / 'preview.py').write_text('print(1)')
        report_path = self.simulation / 'simulation-report.json'
        report = json.loads(report_path.read_bytes())
        data = (self.simulation / 'preview.py').read_bytes()
        report['files'].append({'path': 'preview.py', 'bytes': len(data), 'sha256': sha(data)})
        report_path.write_bytes(encoded(report))
        files = self.package()
        self.assertNotIn('assembled/jumper-v1-6/preview.py', files)
        manifest = json.loads(files[skin.MANIFEST])
        self.assertEqual(manifest['source']['omitted_source_files'], ['preview.py'])

    def test_public_verify_import_repack_and_schema(self):
        from shellflow.packages import verify_package, import_package, repack_package

        files = self.package()
        manifest = json.loads(files[skin.MANIFEST])
        schema = json.loads((Path(__file__).resolve().parents[1] /
                             'schemas/skin-package-v3.schema.json').read_text(encoding='utf-8'))
        try:
            import jsonschema
        except ImportError:
            pass  # Runtime stays stdlib-only; CI dev extras validate JSON Schema.
        else:
            jsonschema.validate(manifest, schema)
        verified = verify_package(self.output, platform_profile=self.profile,
                                  capabilities={'jumper-v1-6'})
        self.assertEqual((verified['kind'], verified['schema'], verified['id']),
                         ('skin', skin.SCHEMA_V3, 'sample'))
        destination = self.root / 'imported'
        imported = import_package(self.output, destination, platform_profile=self.profile)
        self.assertEqual(imported['kind'], 'skin')
        self.assertFalse((destination / 'print').exists())
        other = self.root / 'repacked.skin'
        repacked = repack_package(self.output, other, platform_profile=self.profile)
        self.assertEqual(repacked['sha256'], verified['sha256'])
        self.assertEqual(other.read_bytes(), self.output.read_bytes())


if __name__ == '__main__':
    unittest.main()
