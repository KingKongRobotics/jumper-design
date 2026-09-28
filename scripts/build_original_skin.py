"""Build Jumper Original from the trusted stock visual, without changing physics."""
from pathlib import Path
import argparse
import copy
import json
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def build(output):
    import numpy as np
    import trimesh
    from shellflow.simulation import (assemble, verify_profile, sha, write_xml,
                                     write_json, compare_compiled, verify_whole_robot)
    from shellflow.urdf import export_urdf, verify_urdf
    from shellflow.skin_package import export_skin
    from shellflow.packages import verify_package
    from export_skin_collection import render_views

    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    profile_path = ROOT / 'robots/jumper/profile.json'
    profile = verify_profile(profile_path)
    baseline = profile_path.parent / profile['baseline_mjcf']
    xml = ET.parse(baseline).getroot()
    slot = profile['visual_replacement']
    assert slot['mode'] == 'dedicated_link'
    original = xml.find(".//geom[@name='" + slot['geom_name'] + "']")
    asset = xml.find("asset/mesh[@name='" + original.get('mesh') + "']")
    assert original.get('pos', '0 0 0') == '0 0 0'
    assert original.get('quat', '1 0 0 0') == '1 0 0 0'
    assert asset.get('scale', '1 1 1') == '1 1 1'
    meshdir = Path(xml.find('compiler').get('meshdir'))
    source = profile_path.parent / meshdir / asset.get('file')
    output.mkdir(parents=True)
    # Invert the registered CAD transform only for the assembler's seam check.
    transform = profile['cad_mm_to_parent_m']
    mesh = trimesh.load_mesh(source, process=False)
    mesh.vertices = ((mesh.vertices - np.asarray(transform['translation_m']))
                     @ np.asarray(transform['rotation_matrix'])) / transform['scale']
    cad = output / 'original-upper-cad-mm.stl'
    mesh.export(cad)
    model = output / 'assembly'
    assemble(cad, model, profile_path, faces=len(mesh.faces))
    assembled = ET.parse(model / 'robot.xml').getroot()
    parent = assembled.find(".//body[@name='" + profile['parent_link'] + "']")
    generated = parent.find("geom[@name='shellflow_upper_0']")
    generated.attrib.clear()
    generated.attrib.update(copy.deepcopy(original.attrib))
    generated.set('name', 'shellflow_upper_0')
    generated.set('mesh', 'shellflow_upper_0')
    # Preserve original vertex bytes, transforms and RGBA exactly.
    shutil.copyfile(source, model / meshdir / 'upper_shell_0.stl')
    write_xml(model / 'robot.xml', assembled)
    report_path = model / 'simulation-report.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    report['urdf_conversion'] = export_urdf(model / 'robot.xml', model / 'original.urdf',
        default_velocity_limit=profile.get('robot_velocity_limit_fallback_rad_s', 100.0),
        joint_metadata=profile.get('urdf_joint_metadata'),
        joint_order=profile.get('source_joint_order'),
        source_revision_comment=profile.get('source_revision_comment'))
    (model / 'original.urdf').replace(model / 'robot.urdf')
    report['urdf_verification'] = verify_urdf(model / 'robot.xml', model / 'robot.urdf')
    assert report['urdf_verification']['passed']
    report['native_mujoco'] = compare_compiled(baseline, model / 'robot.xml')
    report['whole_robot'] = verify_whole_robot(baseline, model / 'robot.urdf', profile['parent_link'])
    report['colors'] = {'mode': 'original_baseline', 'rgba': original.get('rgba')}
    report['simplification'] = {'mode': 'original_mesh_bytes', 'faces': len(mesh.faces),
                                'decimation_applied': False}
    report['limitations'] = ['Static display and digital model validation only; no physical trial or policy validation']
    report['original_visual'] = {'source': (meshdir / source.name).as_posix(), 'sha256': sha(source),
                                 'byte_identical': sha(source) == sha(model / meshdir / 'upper_shell_0.stl')}
    report['producer_code_sha256'][Path(__file__).name] = sha(Path(__file__))
    (model / 'README.md').write_text('# Jumper Original\n\nComplete original red Jumper appearance. '
        'Original display meshes and colors are preserved. The upper visual is renamed only for '
        'the skin exchange slot. No print files are included. Use robot.urdf or robot.xml with '
        'their relative meshes; scene.xml contains the static display pose. '
        'Collision, inertia and joints retain the trusted baseline.\n', encoding='utf-8')
    report['files'] = [dict(role='simulation_asset', path=p.relative_to(model).as_posix(),
        sha256=sha(p), bytes=p.stat().st_size) for p in sorted(model.rglob('*'))
        if p.is_file() and p != report_path]
    write_json(report_path, report)
    render_views(model, output / 'previews')
    archive = output / 'jumper-original.skin'
    export_skin(model, profile_path, cad, archive, package_id='jumper-original',
                title='Jumper Original', preview=output / 'previews/three-quarter.png')
    result = verify_package(archive, platform_profile=profile_path, mujoco=True)
    write_json(output / 'validation.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
