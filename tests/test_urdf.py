"""Conversion tests pin kinematics and the inertial-orientation import trap."""
from pathlib import Path
import math
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from shellflow.urdf import UrdfConversionError, export_urdf, verify_urdf

try:
    import mujoco
    import numpy as np
except ImportError:
    mujoco = None


SOURCE = """<mujoco model="conversion_fixture">
<compiler angle="radian" meshdir="meshes"/>
<default><default class="robot">
  <default class="motor"><joint damping="0.017" frictionloss="0.011" armature="0.0015"/></default>
  <default class="visual"><geom contype="0" conaffinity="0"/></default>
  <default class="collision"><geom friction="1 0.01 0.01"/></default>
</default></default>
<worldbody><body name="base_link" pos="0.1 0.2 0.3" childclass="robot">
  <inertial pos="0.01 0.02 0.03" quat="0.9238795325112867 0.3826834323650898 0 0" mass="1" diaginertia="0.02 0.03 0.04"/>
  <joint name="floating_base" type="free"/>
  <geom name="base_visual" class="visual" type="sphere" size="0.02" rgba="0.1 0.2 0.3 1"/>
  <geom name="base_collision" class="collision" type="box" size="0.02 0.03 0.04"/>
  <body name="arm" pos="0.2 0.1 0.05" quat="0.9238795325112867 0 0 0.3826834323650898">
    <inertial pos="0.01 0 0" mass="0.2" diaginertia="0.001 0.002 0.0025"/>
    <joint name="hinge" class="motor" pos="0 0 0" axis="0 1 0" range="-1 2" actuatorfrcrange="-2 2"/>
    <geom name="arm_visual" class="visual" type="cylinder" size="0.01 0.03" pos="0.01 0.02 0.03" quat="0.9238795325112867 0.3826834323650898 0 0"/>
    <body name="tip" pos="0.1 0 0">
      <inertial pos="0 0 0" mass="0.05" diaginertia="0.0001 0.0001 0.0001"/>
      <geom name="tip_collision" class="collision" type="sphere" size="0.01"/>
    </body>
  </body>
</body></worldbody>
<actuator><motor name="drive" joint="hinge"/></actuator>
</mujoco>"""


class UrdfTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.source = self.directory / "model.xml"
        self.output = self.directory / "robot.urdf"

    def export(self, text=SOURCE, **kwargs):
        self.source.write_text(text, encoding="utf-8")
        return export_urdf(self.source, self.output, **kwargs)

    def test_tree_free_root_and_inherited_joint_parameters(self):
        report = self.export()
        tree = ET.parse(self.output)
        self.assertEqual(report["counts"]["body_links"], 3)
        self.assertEqual(report["counts"]["fixed_joints"], 1)
        self.assertEqual(report["counts"]["movable_joints"], 1)
        self.assertEqual(report["counts"]["floating_joints"], 1)
        free = tree.find("joint[@name='floating_base']")
        self.assertEqual(free.get("type"), "floating")
        self.assertEqual(free.find("parent").get("link"), "world")
        hinge = tree.find("joint[@name='hinge']")
        self.assertEqual(hinge.find("axis").get("xyz"), "0 1 0")
        self.assertEqual(float(hinge.find("dynamics").get("damping")), .017)
        self.assertEqual(float(hinge.find("limit").get("effort")), 2)
        self.assertFalse(report["physics_equivalent"])
        self.assertEqual(report["actuators_in_source"], 1)

    def test_primitive_half_sizes_and_global_diffuse_materials(self):
        self.export()
        tree = ET.parse(self.output)
        self.assertEqual(tree.find("link[@name='base_link']/collision/geometry/box").get("size"), "0.040000000000000001 0.059999999999999998 0.080000000000000002")
        cylinder = tree.find("link[@name='arm']/visual/geometry/cylinder")
        self.assertAlmostEqual(float(cylinder.get("length")), .06)
        material = tree.find("link[@name='base_link']/visual/material").get("name")
        self.assertIsNotNone(tree.find(f"material[@name='{material}']/color"))
        self.assertEqual(tree.find("mujoco/compiler").get("discardvisual"), "false")

    def test_inertial_rotation_baked_into_full_tensor(self):
        self.export()
        inertial = ET.parse(self.output).find("link[@name='base_link']/inertial")
        self.assertEqual(inertial.find("origin").get("rpy"), "0 0 0")
        matrix = inertial.find("inertia")
        self.assertAlmostEqual(float(matrix.get("iyy")), .035)
        self.assertAlmostEqual(float(matrix.get("izz")), .035)
        self.assertAlmostEqual(float(matrix.get("iyz")), -.005)

    def test_velocity_import_ceiling_is_explicit_and_configurable(self):
        report = self.export(default_velocity_limit=12.5)
        self.assertEqual(report["velocity_assumptions"][0]["velocity"], 12.5)
        self.assertIn("not_measured", report["velocity_assumptions"][0]["basis"])
        self.assertEqual(ET.parse(self.output).find("joint[@name='hinge']/limit").get("velocity"), "12.5")

    def test_missing_effort_requires_explicit_caller_default(self):
        text = SOURCE.replace(' actuatorfrcrange="-2 2"', "")
        with self.assertRaisesRegex(UrdfConversionError, "No effort limit"):
            self.export(text)
        self.assertFalse(self.output.exists())
        report = self.export(text, default_effort_limit=3)
        self.assertEqual(report["effort_sources"][0]["basis"], "caller_placeholder")

    def test_source_joint_identity_limits_order_and_revision_are_preserved(self):
        metadata = {
            "arm": {"name": "hinge", "type": "revolute", "velocity": "42", "effort": "2"},
            "tip": {"name": "original_tip_joint", "type": "fixed"},
        }
        comment = "<!--\n  model_revision: fixture\n-->"
        report = self.export(SOURCE.replace('angle="radian"', 'angle="radian" balanceinertia="false"'),
                             joint_metadata=metadata,
                             joint_order=["original_tip_joint", "hinge"],
                             source_revision_comment=comment)
        tree = ET.parse(self.output)
        self.assertEqual(tree.find("mujoco/compiler").get("balanceinertia"), "false")
        self.assertEqual([j.get("name") for j in tree.findall("joint")],
                         ["floating_base", "original_tip_joint", "hinge"])
        self.assertEqual(tree.find("joint[@name='hinge']/limit").get("velocity"), "42")
        self.assertEqual(report["velocity_assumptions"][0]["basis"], "source_urdf")
        self.assertIn(comment, self.output.read_text(encoding="utf-8"))

    def test_source_metadata_cannot_change_native_control_or_tree(self):
        for update in ({"name": "different"}, {"effort": "3"},
                       {"velocity": "0"}, {"type": "continuous"}):
            metadata = {
                "arm": {"name": "hinge", "type": "revolute", "velocity": "42", "effort": "2", **update},
                "tip": {"name": "tip_joint", "type": "fixed"},
            }
            with self.subTest(update=update), self.assertRaises(UrdfConversionError):
                self.export(joint_metadata=metadata)
            self.assertFalse(self.output.exists())
        with self.assertRaises(UrdfConversionError):
            self.export(joint_metadata={})
        with self.assertRaises(UrdfConversionError):
            self.export(source_revision_comment="<!--bad--comment-->")

    def test_degree_angles_convert_limits_and_body_orientation(self):
        text = SOURCE.replace('angle="radian"', 'angle="degree"').replace('range="-1 2"', 'range="-90 90"')
        text = text.replace('quat="0.9238795325112867 0 0 0.3826834323650898"', 'euler="0 0 90"')
        self.export(text)
        joint = ET.parse(self.output).find("joint[@name='hinge']")
        self.assertAlmostEqual(float(joint.find("limit").get("lower")), -math.pi/2)
        self.assertAlmostEqual(float(joint.find("origin").get("rpy").split()[2]), math.pi/2)

    def test_mesh_paths_stay_relative_and_keep_scale(self):
        text = SOURCE.replace('<worldbody>', '<asset><mesh name="shape" file="shape.stl" scale="0.001 0.001 0.001"/></asset><worldbody>')
        text = text.replace('type="sphere" size="0.02"', 'type="mesh" mesh="shape"')
        self.export(text)
        mesh = ET.parse(self.output).find("link[@name='base_link']/visual/geometry/mesh")
        self.assertEqual(mesh.get("filename"), "meshes/shape.stl")
        self.assertEqual([float(v) for v in mesh.get("scale").split()], [.001]*3)

    def test_reject_nonzero_joint_anchor_and_multiple_joints(self):
        variants = [SOURCE.replace('pos="0 0 0" axis=', 'pos="0.01 0 0" axis='),
                    SOURCE.replace('<joint name="floating_base"', '<joint name="extra"/><joint name="floating_base"')]
        for text in variants:
            with self.subTest(text=text), self.assertRaises(UrdfConversionError):
                self.export(text)
        self.assertFalse(self.output.exists())

    def test_reject_unsupported_geom_and_joint_types(self):
        for text in (SOURCE.replace('type="cylinder"', 'type="capsule"'),
                     SOURCE.replace('name="hinge" class=', 'name="hinge" type="ball" class=')):
            with self.subTest(text=text), self.assertRaises(UrdfConversionError):
                self.export(text)

    def test_reject_include_traversal_and_missing_inertial(self):
        variants = [SOURCE.replace('<worldbody>', '<include file="part.xml"/><worldbody>'),
                    SOURCE.replace('meshdir="meshes"', 'meshdir="../outside"'),
                    SOURCE.replace('<inertial pos="0 0 0" mass="0.05" diaginertia="0.0001 0.0001 0.0001"/>', '')]
        for text in variants:
            with self.subTest(text=text), self.assertRaises(UrdfConversionError):
                self.export(text)

    def test_output_is_not_overwritten(self):
        self.export()
        first = self.output.read_bytes()
        with self.assertRaises(FileExistsError):
            self.export()
        self.assertEqual(self.output.read_bytes(), first)

    @unittest.skipIf(mujoco is None, "Optional MuJoCo package is not installed")
    def test_independent_shell_and_sensor_frames_survive_actuator_free_model(self):
        # The newer robot gives the shell and sensors their own fixed bodies.
        # Use tiny primitives here so this regression needs no historical meshes.
        root = ET.fromstring(SOURCE)
        root.remove(root.find("actuator"))
        base = root.find("worldbody/body")
        for name, position, mass in (
            ("shangke_link", "-0.007 0 0.0315", "0.11"),
            ("ToF_link", "0.0865 0 0.0168", "0.0015"),
            ("shexiangtou_link", "0.0875 0.014 0.0168", "0.002"),
        ):
            body = ET.SubElement(base, "body", name=name, pos=position)
            ET.SubElement(body, "inertial", pos="0.001 0.002 0.003", mass=mass,
                          quat="0.9238795325112867 0.3826834323650898 0 0",
                          diaginertia="0.000001 0.0000015 0.000002")
            ET.SubElement(body, "geom", name=name + "_visual", type="sphere",
                          size="0.003", **{"class": "visual"})
            ET.SubElement(body, "geom", name=name + "_collision", type="sphere",
                          size="0.003", **{"class": "collision"})
        ET.SubElement(base, "site", name="imu", pos="0.005 0 0")
        ET.SubElement(base.find("body[@name='shexiangtou_link']"), "camera",
                      name="onboard", pos="0.007 0 0")
        ET.SubElement(ET.SubElement(root, "sensor"), "gyro", name="imu_gyro", site="imu")
        report = self.export(ET.tostring(root, encoding="unicode"))
        self.assertEqual(report["counts"]["body_links"], 6)
        self.assertEqual(report["counts"]["fixed_joints"], 4)
        self.assertEqual(report["actuators_in_source"], 0)
        self.assertEqual(report["effort_sources"][0]["basis"], "joint.actuatorfrcrange")
        tree = ET.parse(self.output)
        for name in ("shangke_link", "ToF_link", "shexiangtou_link"):
            fixed = tree.find(f"joint[@name='{name}_fixed_joint']")
            self.assertEqual(fixed.get("type"), "fixed")
            self.assertEqual(fixed.find("parent").get("link"), "base_link")
            self.assertIsNotNone(tree.find(f"link[@name='{name}']/inertial"))
        result = verify_urdf(self.source, self.output, poses=10)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["source"]["bodies_with_world"], 7)
        self.assertEqual(result["urdf"]["bodies_with_world"], 7)
        self.assertLessEqual(result["max_absolute_errors"]["fk_body_position_m"], 1e-10)
        self.assertLessEqual(result["max_absolute_errors"]["body_inertia_tensor_kg_m2"], 1e-9)
        self.assertFalse(result["physics_equivalent"])

    @unittest.skipIf(mujoco is None, "Optional MuJoCo package is not installed")
    def test_native_joint_dispatch_uses_numeric_enum_identity(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        class IntegerConvertibleEnum:
            # Native enum bindings need not compare equal to NumPy scalar IDs.
            def __init__(self, value):
                self.value = int(value)

            def __int__(self):
                return self.value

            def __eq__(self, other):
                return False

        joint_types = SimpleNamespace(**{
            name: IntegerConvertibleEnum(getattr(mujoco.mjtJoint, name))
            for name in ("mjJNT_FREE", "mjJNT_BALL", "mjJNT_SLIDE", "mjJNT_HINGE")
        })
        for kind in ("hinge", "slide"):
            with self.subTest(kind=kind):
                self.output = self.directory / (kind + ".urdf")
                self.export(SOURCE.replace('name="hinge" class=',
                                           'name="hinge" type="' + kind + '" class='))
                with patch.object(mujoco, "mjtJoint", joint_types):
                    result = verify_urdf(self.source, self.output, poses=3)
                self.assertTrue(result["passed"], result)

    def test_sensor_frame_without_authored_inertial_is_not_given_invented_mass(self):
        root = ET.fromstring(SOURCE)
        sensor = ET.SubElement(root.find("worldbody/body"), "body", name="sensor_frame")
        ET.SubElement(sensor, "site", name="imu")
        with self.assertRaisesRegex(UrdfConversionError, "Explicit inertial required.*sensor_frame"):
            self.export(ET.tostring(root, encoding="unicode"))
        self.assertFalse(self.output.exists())

    @unittest.skipIf(mujoco is None, "Optional MuJoCo package is not installed")
    def test_verifier_rejects_actual_file_mass_and_axis_changes(self):
        self.export()
        good = verify_urdf(self.source, self.output, poses=3)
        self.assertTrue(good["passed"], good)
        corrupt = ET.parse(self.output)
        corrupt.find("link[@name='arm']/inertial/mass").set("value", "0.25")
        corrupt.find("joint[@name='hinge']/axis").set("xyz", "1 0 0")
        corrupt.write(self.output, encoding="utf-8", xml_declaration=True)
        failed = verify_urdf(self.source, self.output, poses=3)
        self.assertFalse(failed["passed"])
        failures = {item["check"] for item in failed["failures"]}
        self.assertIn("body_mass", failures)
        self.assertIn("jnt_axis", failures)

    @unittest.skipIf(mujoco is None, "Optional MuJoCo package is not installed")
    def test_mujoco_roundtrip_preserves_fk_mass_inertia_and_joint_limits(self):
        self.export()
        before = mujoco.MjModel.from_xml_string(SOURCE)
        after = mujoco.MjModel.from_xml_string(self.output.read_text(encoding="utf-8"))
        self.assertEqual((before.nbody, before.njnt, before.nq, before.nv),
                         (after.nbody, after.njnt, after.nq, after.nv))
        for attribute in ("body_mass", "body_ipos", "jnt_axis", "jnt_range", "jnt_type", "dof_damping", "dof_frictionloss"):
            np.testing.assert_allclose(getattr(before, attribute), getattr(after, attribute), atol=1e-12)
        def tensors(model):
            result = []
            for q, diagonal in zip(model.body_iquat, model.body_inertia):
                r = np.empty(9)
                mujoco.mju_quat2Mat(r, q)
                r = r.reshape(3, 3)
                result.append(r @ np.diag(diagonal) @ r.T)
            return np.array(result)
        np.testing.assert_allclose(tensors(before), tensors(after), atol=1e-9, rtol=1e-7)
        data1, data2 = mujoco.MjData(before), mujoco.MjData(after)
        for angle in (-.7, .0, .9):
            data1.qpos[-1] = data2.qpos[-1] = angle
            mujoco.mj_forward(before, data1)
            mujoco.mj_forward(after, data2)
            np.testing.assert_allclose(data1.xpos, data2.xpos, atol=1e-12)
            np.testing.assert_allclose(data1.xmat, data2.xmat, atol=1e-12)
        # A deliberately wrong diagonal-only export would pass mass/FK checks
        # but lose the inertial orientation. This control proves sensitivity.
        corrupted = ET.parse(self.output)
        inertial = corrupted.find("link[@name='base_link']/inertial/inertia")
        inertial.set("iyy", ".03")
        inertial.set("izz", ".04")
        inertial.set("iyz", "0")
        bad = mujoco.MjModel.from_xml_string(ET.tostring(corrupted.getroot(), encoding="unicode"))
        self.assertGreater(float(np.max(np.abs(tensors(before)-tensors(bad)))), .004)


if __name__ == "__main__":
    unittest.main()
