#!/usr/bin/env python3
"""Verify generated package hashes and attach available packages to the library."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--refresh-helper', action='store_true')
    parser.add_argument('--robot-platform', choices=('hexa-v1', 'jumper-v1-6'), default='jumper-v1-6')
    args = parser.parse_args()
    library = ROOT / 'library'
    profile_path = ROOT / 'robots' / args.robot_platform / 'profile.json'
    profile_sha = sha(profile_path)
    package_root = library / 'simulations'
    if args.robot_platform != 'hexa-v1':
        package_root = package_root / args.robot_platform
    catalog = json.loads((library / 'catalog.json').read_text(encoding='utf-8'))
    rows = []
    for item in catalog['items']:
        package = package_root / item['id']
        report_path = package / 'simulation-report.json'
        if not report_path.is_file():
            continue
        report = json.loads(report_path.read_text(encoding='utf-8'))
        if not report['passed'] or not report['urdf_verification']['passed']:
            raise ValueError('Simulation checks failed: ' + item['id'])
        if report['robot_profile_sha256'] != profile_sha:
            raise ValueError('Simulation robot profile differs: ' + item['id'])
        if args.robot_platform != 'hexa-v1' and not report.get('whole_robot', {}).get('passed'):
            raise ValueError('Missing full-robot verification: ' + item['id'])
        for record in report['files']:
            path = (package / record['path']).resolve()
            if not path.is_relative_to(package.resolve()) or not path.is_file() or sha(path) != record['sha256']:
                raise ValueError('Simulation asset changed: ' + item['id'] + '/' + record['path'])
        print_record = next(record for record in item['files'] if record['role'] == 'print_mesh')
        if report['source_shell_sha256'] != print_record['sha256'] or sha(library / print_record['path']) != print_record['sha256']:
            raise ValueError('Simulation and manufacturing source differ: ' + item['id'])
        if args.refresh_helper:
            shutil.copy2(ROOT / 'scripts/preview_simulation.py', package / 'preview.py')
            readme = package / 'README.md'
            text = readme.read_text(encoding='utf-8')
            if '## Standalone runtime' not in text:
                text += ('\n## Standalone runtime\n\nInstall Python and `python -m pip install mujoco`. '
                         'Copy this entire package, including real meshes rather than Git LFS pointer text. '
                         'On macOS use `mjpython preview.py` for interactive viewing. Viewing/rendering needs '
                         'a working graphics/OpenGL environment. Default preview is static; `--simulate` '
                         'starts the preserved baseline dynamics explicitly. The display home pose is not a '
                         'validated standing controller.\n')
                readme.write_text(text, encoding='utf-8')
        if args.render:
            subprocess.run([sys.executable, str(package / 'preview.py'), '--render', str(package / 'preview.png')], check=True)
        if args.render or args.refresh_helper:
            report['post_export_preview_review'] = dict(index_script_sha256=sha(Path(__file__)),
                preview_helper_sha256=sha(package / 'preview.py'), rendered=args.render,
                pose='display_home keyframe; finite pose checks, not stability certification')
            report['files'] = [dict(role='simulation_asset', path=p.relative_to(package).as_posix(), sha256=sha(p), bytes=p.stat().st_size)
                               for p in sorted(package.rglob('*')) if p.is_file() and p != report_path]
            write(report_path, report)
        description = dict(status='assembled_with_baseline_physics', full_robot_urdf_verified=True,
            robot_platform=args.robot_platform, robot_profile_sha256=profile_sha,
            whole_robot=report.get('whole_robot'),
            directory=package.relative_to(library).as_posix(), urdf=(package / 'robot.urdf').relative_to(library).as_posix(),
            mjcf=(package / 'robot.xml').relative_to(library).as_posix(), report_sha256=sha(report_path),
            color_mode=report['colors']['mode'], collision_policy=report['collision_policy'],
            inertia_policy=report['inertia_policy'], physical_dynamics_validated=False,
            scope='Actual file load and finite kinematic/inertial comparison; new shell only replaces the visual geometry')
        item['robot_description'] = description
        item['coordinate_frame']['robot_base_registration_verified'] = bool(report['seam_registration']['passed'])
        item['coordinate_frame']['robot_base_registration_scope'] = report['seam_registration']['scope']
        asset_path = library / 'assets' / item['id'] / 'asset.json'
        asset = json.loads(asset_path.read_text(encoding='utf-8'))
        asset['robot_description'] = description
        asset['coordinate_frame'] = item['coordinate_frame']
        write(asset_path, asset)
        rows.append(dict(id=item['id'], name=item['name'], report_sha256=sha(report_path),
                         package=package.relative_to(library / 'simulations').as_posix(),
                         color=report['colors']['mode'], finite_sample_error_mm=report['simplification']['sampled_max_mm']))
    catalog['simulation_packages'] = len(rows)
    catalog['active_robot_platform'] = args.robot_platform
    write(library / 'catalog.json', catalog)
    colored = sum(row['color'] == 'palette_from_exact_matching_ams' for row in rows)
    monochrome = [row['name'] for row in rows if row['color'] == 'monochrome']
    color_summary = f'{len(rows)} skins total; {colored} retain their color palettes.'
    if monochrome:
        color_summary += ' Monochrome fallbacks: ' + ', '.join(monochrome) + '; see each package validation report.'
    lines = ['# Complete robot URDF / MuJoCo collection', '',
             f'Current robot baseline: `{args.robot_platform}`. Legacy hexa-v1 deliveries remain available; new deliveries are generated separately under `jumper-v1-6/`.', '',
             'Each directory can be copied independently and contains a complete robot with relative meshes. ' + color_summary + ' Original print sources are unchanged.', '',
             'This page confirms only that the display assembly and baseline simulation files load. Each skin retains baseline collision and inertia; new-shell dynamics and full-motion clearance have not been validated.', '',
             '| Robot preview | Skin | Files |', '|---|---|---|']
    for row in rows:
        name = row['package']
        lines.append(f'| <img src="{name}/preview.png" width="240" alt="{row["name"]} complete robot"> | {row["name"]} | [URDF]({name}/robot.urdf) · [MuJoCo]({name}/robot.xml) · [Scene]({name}/scene.xml) · [README]({name}/README.md) · [Report]({name}/simulation-report.json) |')
    (library / 'simulations/README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    write(library / 'simulation-index.json', dict(schema_version=1, packages=len(rows), items=rows,
          robot_platform=args.robot_platform, robot_profile_sha256=profile_sha,
          physical_dynamics_validated=False, verification_scope='Recorded producer checks and current package SHA readback'))
    print(json.dumps(dict(ok=True, packages=len(rows), rendered=args.render), ensure_ascii=False))


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    main()
