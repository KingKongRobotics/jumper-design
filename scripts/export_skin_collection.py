"""Build an indexed collection of complete robot skins from frozen catalog assets."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import html
import json
from pathlib import Path
import sys
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(data)
    return value.hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def checked_source(record):
    path = (ROOT / record['path']).resolve()
    if not path.is_relative_to(ROOT) or digest(path) != record['sha256']:
        raise ValueError('Source path or SHA mismatch: ' + record['path'])
    return path


def body_overrides(item, profile_path):
    """Resolve semantic limb groups to exact baseline visual names."""
    profile = json.loads(profile_path.read_text(encoding='utf-8'))
    baseline = ET.parse(profile_path.parent / profile['baseline_mjcf']).getroot()
    records = []
    palette = item['body_palette']
    for body in baseline.iter('body'):
        name = body.get('name', '')
        if name == 'base_link':
            color = item['lower_shell_color']
        elif name.startswith(('LF_', 'RF_', 'LM_', 'RM_', 'LR_', 'RR_')):
            role = ('accent' if any(part in name for part in ('pad_', 'tip_', 'insert_'))
                    else 'secondary' if any(part in name for part in ('forearm_', 'thigh_'))
                    else 'primary')
            color = palette[role]
        else:
            continue
        rgba = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)] + [1.0]
        for geom in body.findall('geom'):
            if geom.get('contype') == '0' and geom.get('conaffinity') == '0':
                records.append(dict(link=name, geom=geom.get('name'), rgba=rgba))
    if not records or not any(r['link'].startswith('LF_') for r in records):
        raise ValueError('Body palette requires the declared Jumper limb topology')
    return records


def render_views(assembly, destination):
    import mujoco
    from preview_simulation import load_package, save_png
    model = load_package(assembly)
    data = mujoco.MjData(model)
    if model.nkey:
        mujoco.mj_resetDataKeyframe(model, data, 0)
    mujoco.mj_forward(model, data)
    destination.mkdir(parents=True, exist_ok=True)
    with mujoco.Renderer(model, height=600, width=800) as renderer:
        for view, azimuth in [('three-quarter', 145), ('front', 180), ('side', 90), ('back', 0), ('bottom', 145), ('bottom-gray', 145)]:
            camera = mujoco.MjvCamera()
            camera.lookat[:] = [0, 0, .16]
            camera.distance, camera.elevation, camera.azimuth = .85, -22, azimuth
            options = mujoco.MjvOption()
            if view.startswith('bottom'):
                camera.elevation = 45
                options.geomgroup[0] = False
                options.geomgroup[3] = False
            if view == 'bottom-gray':
                model.geom_rgba[model.geom_group == 2, :3] = .65
            renderer.update_scene(data, camera, scene_option=options)
            save_png(destination / (view + '.png'), renderer.render())


def build_item(item, profile_name, output_name, version, faces):
    from shellflow.simulation import assemble
    from shellflow.skin_package import export_skin
    from shellflow.packages import verify_package
    profile, output = Path(profile_name), Path(output_name)
    shell, ams = checked_source(item['shell']), checked_source(item['ams'])
    assembly = output / 'models' / item['id']
    preview = output / 'previews' / item['id']
    filename = item['id'] + '.skin'
    if (not isinstance(filename, str) or Path(filename).name != filename
            or any(c in filename for c in '/\\:') or not filename.endswith('.skin')):
        raise ValueError('Unsafe skin filename')
    archive = output / 'skins' / filename
    checkpoint = output / 'checks' / (item['id'] + '.json')
    overrides = body_overrides(item, profile)
    if checkpoint.exists():
        previous = json.loads(checkpoint.read_text(encoding='utf-8'))
        if (previous['recipe'] != item or previous['profile_sha256'] != digest(profile)
                or previous.get('version') != version or previous.get('faces') != faces):
            raise ValueError('Resume recipe/profile differs: ' + item['id'])
        if digest(archive) != previous['archive_sha256']:
            raise ValueError('Resume archive changed: ' + item['id'])
        verify_package(archive, platform_profile=profile, mujoco=True)
        return previous
    if not assembly.exists():
        assemble(shell, assembly, profile, ams3mf=ams, faces=faces,
                 visual_overrides=overrides)
    report = json.loads((assembly / 'simulation-report.json').read_text(encoding='utf-8'))
    if (report['source_shell_sha256'] != item['shell']['sha256']
            or report['robot_profile_sha256'] != digest(profile)
            or report.get('visual_overrides') != overrides):
        raise ValueError('Assembly differs from requested inputs: ' + item['id'])
    if item.get('require_upper_color') and report['colors']['mode'] == 'monochrome':
        raise ValueError('Required upper-shell colors unavailable: ' + item['id'])
    if not archive.exists():
        render_views(assembly, preview)
        export_skin(assembly, profile, shell, archive, package_id=item['id'],
                    title=item['title'], version=version, ams=ams,
                    preview=preview / 'three-quarter.png')
    validation = verify_package(archive, platform_profile=profile, mujoco=True)
    # Display archives must never contain manufacturing payloads.
    with zipfile.ZipFile(archive) as package:
        if any(name.startswith('print/') or Path(name).suffix.lower() in ('.3mf', '.gcode', '.step', '.stp')
               for name in package.namelist()):
            raise ValueError('Display-only .skin contains manufacturing data')
    checked_source(item['shell'])
    checked_source(item['ams'])
    result = dict(id=item['id'], title=item['title'], recipe=item, version=version, faces=faces,
                  profile_sha256=digest(profile), archive=archive.relative_to(output).as_posix(),
                  archive_sha256=digest(archive), archive_bytes=archive.stat().st_size,
                  preview=(preview / 'three-quarter.png').relative_to(output).as_posix(),
                  model=assembly.relative_to(output).as_posix(), validation=validation,
                  upper_color=report['colors'], seam_registration=report['seam_registration'],
                  lower_shell_color=item['lower_shell_color'], lower_color_name=item['lower_color_name'],
                  body_palette=item['body_palette'], visual_overrides=overrides,
                  manufacturing_files_included=False, original_sources_unchanged=True, physical_fit_tested=False,
                  physical_dynamics_validated=False)
    write_json(checkpoint, result)
    return result


def gallery(output, rows):
    cards = []
    for row in rows:
        esc = html.escape
        fallback = row['upper_color']['mode'] == 'monochrome'
        note = '<p class="note">The upper shell uses the declared monochrome fallback; the original AMS source is retained.</p>' if fallback else ''
        views = ''.join(f'<a href="previews/{esc(row["id"])}/{v}.png">{t}</a>'
                        for v, t in [('front', 'Front'), ('side', 'Side'), ('back', 'Back'), ('bottom', 'Bottom')])
        cards.append(f'<article><a href="{esc(row["preview"])}"><img src="{esc(row["preview"])}" alt="{esc(row["title"])}"></a>'
                     f'<div class="body"><h2>{esc(row["title"])}</h2><p><i style="background:{row["lower_shell_color"]}"></i>'
                     f'Lower shell: {esc(row["lower_color_name"])} <code>{row["lower_shell_color"]}</code></p>'
                     f'<p>Limbs: {esc(row["body_palette"]["name"])} · {row["archive_bytes"]/1e6:.1f} MB</p>{note}'
                     f'<nav><a class="download" href="{esc(row["archive"])}" download>Download .skin</a>{views}'
                     f'<a href="{esc(row["model"])}/robot.urdf">Complete robot URDF</a></nav></div></article>')
    markup = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jumper skin collection</title><style>*{box-sizing:border-box}body{margin:0;background:#f3f1eb;color:#212721;font:15px/1.6 system-ui,sans-serif}header,main,footer{max-width:1440px;margin:auto;padding:32px}header{padding-bottom:12px}h1{font-size:34px;margin:0}header p{color:#565e55;max-width:920px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:18px}article{background:#fff;border:1px solid #dcded6;border-radius:14px;overflow:hidden}img{display:block;width:100%;aspect-ratio:4/3;object-fit:cover}.body{padding:16px}h2{font-size:18px;margin:0}i{display:inline-block;width:18px;height:18px;border:1px solid #aaa;border-radius:50%;vertical-align:middle;margin-right:7px}code{font-size:12px;color:#667064}nav{display:flex;flex-wrap:wrap;gap:12px;align-items:center}a{color:#234b32}.download{background:#234b32;color:white;padding:6px 12px;border-radius:7px;text-decoration:none}.note{color:#865422;font-size:13px}footer{color:#61695f;font-size:13px}</style>
<header><h1>Jumper · 15 robot skins</h1><p>Each display-only .skin contains the complete current Jumper robot with coordinated colors for the upper shell, lower shell, and limbs. STL print sources, AMS, and G-code are distributed separately. Select an image to view the actual model render.</p><p><a href="all-skins.zip">Download all .skin packages</a> · <a href="collection.json">View file manifest</a></p></header><main class="grid">'''
    markup += ''.join(cards) + '</main><footer>Successful model and file loading does not establish physical fit. Print sources are unchanged; the six-hole mount still needs review and physical trial assembly. New-shell collision, inertia, and controller behavior have not been revalidated.</footer></html>'
    (output / 'index.html').write_text(markup, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipes', type=Path, default=ROOT / 'library/skin-recipes.json')
    parser.add_argument('--profile', type=Path, default=ROOT / 'robots/jumper/profile.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--faces', type=int, default=100000)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error('--workers must be 1 through 4')
    output = args.output.resolve()
    recipes = json.loads(args.recipes.read_text(encoding='utf-8'))
    items = recipes['items']
    if len({i['id'] for i in items}) != len(items):
        raise ValueError('Repeated collection IDs')
    from shellflow.skin_package import IDENT
    if any(not IDENT.fullmatch(i['id']) for i in items):
        raise ValueError('Unsafe collection ID')
    for directory in ('models', 'previews', 'skins', 'checks'):
        (output / directory).mkdir(parents=True, exist_ok=True)
    profile = args.profile.resolve()
    profile_sha = digest(profile)
    results, failures = {}, []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(build_item, item, str(profile), str(output), recipes['version'], args.faces): item['id'] for item in items}
        for job in as_completed(jobs):
            name = jobs[job]
            try:
                result = job.result()
                results[name] = result
                print(json.dumps(dict(id=name, ok=True, completed=len(results), total=len(items),
                                      upper_color=result['upper_color']['mode']), ensure_ascii=False), flush=True)
            except Exception as error:
                failures.append(dict(id=name, error=str(error)))
                print(json.dumps(dict(id=name, ok=False, error=str(error)), ensure_ascii=False), flush=True)
    write_json(output / 'batch-status.json', dict(completed=list(results), failures=failures))
    if failures:
        raise RuntimeError('Collection incomplete; see batch-status.json. Successful items can resume.')
    if digest(profile) != profile_sha:
        raise ValueError('Robot profile changed during batch')
    rows = [results[item['id']] for item in items]
    write_json(output / 'collection.json', dict(schema='shellflow-skin-collection/1', count=len(rows),
               profile_sha256=profile_sha, version=recipes['version'], items=rows,
               physical_fit_tested=False, physical_dynamics_validated=False))
    gallery(output, rows)
    archive = output / 'all-skins.zip'
    if archive.exists():
        raise FileExistsError('Collection already published; choose a new output directory')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_STORED, allowZip64=True) as package:
        for row in rows:
            package.write(output / row['archive'], Path(row['archive']).name)
        summary = dict(schema='shellflow-skin-collection/1', count=len(rows), version=recipes['version'],
                       profile_sha256=profile_sha, physical_fit_tested=False,
                       items=[dict(id=row['id'], title=row['title'], file=Path(row['archive']).name,
                                   sha256=row['archive_sha256'], lower_shell_color=row['lower_shell_color'])
                              for row in rows])
        package.writestr('collection.json', json.dumps(summary, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(archive) as package:
        if package.testzip() is not None:
            raise ValueError('Collection ZIP CRC check failed')
    print(json.dumps(dict(ok=True, count=len(rows), output=str(output), zip_sha256=digest(archive)), ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
