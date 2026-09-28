"""Guard the current Jumper revision against the former LM_J0 limit typo."""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from shellflow.package_io import PackageError
from shellflow.robot_import import _map_preview_pose, convert_urdf, import_jumper


SOURCE = Path(__file__).resolve().parents[1] / 'robots/jumper/urdf/jumper.urdf'


def test_current_source_limits_are_transcribed_without_changing_other_joints():
    source = ET.fromstring(SOURCE.read_bytes())
    native_bytes, report = convert_urdf(SOURCE.read_bytes())
    native = ET.fromstring(native_bytes)
    source_limits = {
        joint.get('name'): (float(joint.find('limit').get('lower')),
                            float(joint.find('limit').get('upper')))
        for joint in source.findall('joint') if joint.get('type') == 'revolute'
    }
    assert len(source_limits) == 22
    assert source_limits['LM_J0_joint'] == (-0.75, 1.0)
    for joint_name, limits in source_limits.items():
        native_joint = native.find(f".//joint[@name='{joint_name}']")
        assert native_joint is not None
        assert tuple(map(float, native_joint.get('range').split())) == limits
        metadata = next(entry for entry in report['source_joint_metadata'].values()
                        if entry['name'] == joint_name)
        assert (float(metadata['lower']), float(metadata['upper'])) == limits


def test_import_rejects_outdated_positive_lm_lower_before_writing(tmp_path):
    local_scratch = tmp_path
    source = local_scratch / 'source'
    (source / 'urdf').mkdir(parents=True)
    root = ET.fromstring(SOURCE.read_bytes())
    joint = root.find("joint[@name='LM_J0_joint']")
    joint.find('limit').set('lower', '0.75')
    (source / 'urdf/jumper.urdf').write_bytes(ET.tostring(root))
    destination = local_scratch / 'destination'
    with pytest.raises(PackageError, match='LM_J0_joint source limit must be'):
        import_jumper(source, destination)
    assert not destination.exists()


def test_preview_recomputed_from_legacy_raw_value_with_correct_limit(tmp_path):
    local_scratch = tmp_path
    legacy = local_scratch / 'legacy'
    legacy.mkdir()
    (legacy / 'pose.json').write_text(json.dumps({
        'base_height_m': 0.2, 'joints': {'old_lm': 0.0012}}), encoding='utf-8')
    (legacy / 'baseline.xml').write_text(
        '<mujoco><worldbody><body name="old_hip">'
        '<joint name="old_lm"/></body></worldbody></mujoco>', encoding='utf-8')
    profile = legacy / 'profile.json'
    profile.write_text('{}', encoding='utf-8')
    audit_bytes = b'current source audit'
    source_root = ET.fromstring(
        '<robot><joint name="LM_J0_joint" type="revolute"/></robot>')
    report = {'source_joint_metadata': {'LM_hip_link': {
        'name': 'LM_J0_joint', 'type': 'revolute', 'lower': '-0.75', 'upper': '1'}}}
    pose, mapping = _map_preview_pose(
        profile, {'preview_pose': 'pose.json', 'baseline_mjcf': 'baseline.xml'},
        report, {'comparison': {'old_to_new_links': {'old_hip': 'LM_hip_link'}}},
        audit_bytes, source_root)
    assert pose['joints']['LM_J0_joint'] == 0.0012
    assert pose['corrections'] == {}
    assert mapping['mapped_joints']['old_lm']['source_limit_rad'] == [-0.75, 1.0]
