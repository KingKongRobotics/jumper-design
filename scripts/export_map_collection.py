"""Build BE UNLIMITED maps with a complete default robot and review renders."""
from __future__ import annotations

import argparse
import shutil
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
from shellflow.map_package import export_environment, compose_default, MAP_LIMITS
from shellflow.package_io import read_archive
from shellflow.packages import verify_package
from shellflow.content_library import publish
from shellflow.defaults import default_skin_path
from preview_simulation import save_png

ORDER = ['park-pump-track', 'narrow-bridge', 'shelf-maze', 'switchback-slopes']


def render_overview(files: dict[str, bytes], ident: str, output: Path):
    """Render only the environment; the map's bundled robot is never loaded."""
    import mujoco
    manifest = json.loads(files['scene-package.json'])
    assets = {name: content for name, content in files.items()
              if not name.startswith(('robot/', 'preview/')) and not name.endswith('.json')}
    import numpy as np
    import xml.etree.ElementTree as ET
    # Presentation-only lighting/floor treatment; never written into the map.
    world = ET.fromstring(assets[manifest['world']['file']])
    asset = world.find('asset')
    if asset is None:
        asset = ET.SubElement(world, 'asset')
    ET.SubElement(asset, 'texture', name='thumbnail_floor', type='2d',
                  builtin='checker', rgb1='.46 .51 .55', rgb2='.52 .57 .61',
                  width='512', height='512')
    ET.SubElement(asset, 'material', name='thumbnail_floor', texture='thumbnail_floor',
                  texrepeat='2 2', texuniform='true', reflectance='0')
    authored_floor = manifest.get('source', {}).get('authoredGround', False) or any(g.get('name', '').startswith(('visual_soccer_', 'visual_web_')) for g in world.iter('geom'))
    for geom in world.iter('geom'):
        if geom.get('type') == 'plane':
            geom.set('size', '20 20 .1' if authored_floor else '0 0 .1')
        if geom.get('type') == 'plane' and not authored_floor:
            geom.set('rgba', '1 1 1 1')
            geom.set('material', 'thumbnail_floor')
    ET.SubElement(world.find('worldbody'), 'light', pos='-3 -4 8', dir='.2 .3 -1',
                  directional='true', diffuse='.55 .55 .55', ambient='.12 .12 .12',
                  specular='0 0 0', castshadow='true')
    model = mujoco.MjModel.from_xml_string(ET.tostring(world, encoding='unicode'), assets=assets)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    assert mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, 'base_link') == -1
    model.vis.global_.offwidth, model.vis.global_.offheight = 1000, 750
    model.vis.headlight.ambient[:] = [.18, .18, .18]
    model.vis.headlight.diffuse[:] = [.35, .35, .35]
    model.vis.headlight.specular[:] = 0
    # Bound all visible finite geometry in world space, including rotated parts.
    bounds = []
    for i in range(model.ngeom):
        if model.geom_type[i] == mujoco.mjtGeom.mjGEOM_PLANE or model.geom_rgba[i, 3] < .01:
            continue
        center = data.geom_xpos[i]
        extent = np.abs(data.geom_xmat[i].reshape(3, 3)) @ model.geom_size[i]
        if model.geom_type[i] in (mujoco.mjtGeom.mjGEOM_SPHERE, mujoco.mjtGeom.mjGEOM_CAPSULE):
            extent[:] = model.geom_rbound[i]
        bounds.extend([center - extent, center + extent])
    low, high = np.min(bounds, axis=0), np.max(bounds, axis=0)
    camera = mujoco.MjvCamera()
    camera.azimuth, camera.elevation = 135, -50
    camera.lookat[:] = (low + high) / 2
    radius = np.linalg.norm(high - low) / 2
    camera.distance = max(1.5, radius / np.sin(np.radians(model.vis.global_.fovy / 2)) * 1.10)
    with mujoco.Renderer(model, height=750, width=1000) as renderer:
        renderer.update_scene(data, camera)
        save_png(output, renderer.render())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview-dir', type=Path, help='Reviewed be-web/1 PNGs named <map-id>.png; required for standardized maps')
    parser.add_argument('--sources', type=Path, default=ROOT / 'library/map-sources/authored')
    parser.add_argument('--skin', type=Path, default=default_skin_path(ROOT))
    parser.add_argument('--profile', type=Path, default=ROOT / 'robots/jumper/profile.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--library', type=Path, default=ROOT / 'library')
    args = parser.parse_args()
    import mujoco
    rows = []
    args.output.mkdir(parents=True, exist_ok=True)
    for ident in ORDER:
        source = args.sources / ident
        authored = ROOT / 'library/map-sources/authored' / ident
        if args.sources.resolve() == (ROOT / 'library/map-sources/be-unlimited').resolve() and authored.is_dir():
            source = authored
        manifest_bytes = (source / 'scene-package.json').read_bytes()
        manifest = json.loads(manifest_bytes)
        files = {name: (source / name).read_bytes() for name in manifest['files']}
        files['scene-package.json'] = manifest_bytes
        title = manifest['title']
        folder = args.output / ident
        folder.mkdir(exist_ok=True)
        archive = folder / (ident + '.map')
        if 'visual-appearance.json' in files:
            if args.preview_dir is None or not (args.preview_dir / (ident + '.png')).is_file():
                raise ValueError('Web-standard map requires a reviewed Web preview; use --preview-dir')
            shutil.copy2(args.preview_dir / (ident + '.png'), folder / 'overview.png')
        else:
            render_overview(files, ident, folder / 'overview.png')
        if not archive.exists():
            export_environment(files, archive, args.skin, args.profile, preview=folder / 'overview.png')
        else:
            previous = read_archive(archive, limits=MAP_LIMITS)
            packaged = json.loads(previous['scene-package.json'])
            if any(previous.get(name) != content for name, content in files.items()
                   if name != 'scene-package.json') or any(
                    packaged.get(key) != manifest.get(key)
                    for key in manifest if key not in ('schema', 'files')):
                raise ValueError('Existing map differs from source; choose a new output directory')
            skin_files = read_archive(args.skin)
            if any(previous.get('robot/' + name) != content for name, content in skin_files.items()):
                raise ValueError('Existing map default skin changed; choose a new output directory')
        validation = verify_package(archive, platform_profile=args.profile, mujoco=True)
        model, data, composition = compose_default(read_archive(archive, limits=MAP_LIMITS), profile=args.profile)
        assert model.body('base_link').id > 0 and model.joint('floating_base').id >= 0
        assert composition['spawn_applied']
        model.vis.global_.offwidth = 1000
        model.vis.global_.offheight = 750
        model.vis.headlight.ambient[:] = [.5, .5, .5]
        model.vis.headlight.diffuse[:] = [.7, .7, .7]
        robot_position = data.xpos[model.body('base_link').id].copy()
        camera = mujoco.MjvCamera()
        camera.azimuth = 135
        camera.lookat[:] = robot_position + [0, 0, .1]
        camera.distance, camera.elevation = 1.3, -25
        if ident == 'pouring':
            camera.azimuth, camera.elevation = 90, -40
        with mujoco.Renderer(model, height=750, width=1000) as renderer:
            renderer.update_scene(data, camera)
            save_png(folder / 'robot.png', renderer.render())
        published = publish(archive, args.library, args.profile)
        row = {'id': manifest['id'], 'title': title, 'source_id': ident,
               'archive': archive.relative_to(args.output).as_posix(), 'bytes': archive.stat().st_size,
               'validation': validation, 'composition': composition,
               'robot_position': robot_position.tolist(), 'published': published}
        (folder / 'verification.json').write_text(json.dumps(row, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        rows.append(row)
        print(json.dumps({'id':ident,'ok':True,'robot_joints':composition['robot_joints'],
                          'bytes':row['bytes']}, ensure_ascii=False), flush=True)
    (args.output / 'collection.json').write_text(json.dumps({'count':len(rows),'items':rows}, ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    cards = []
    for row in rows:
        ident, title = row['source_id'], html.escape(row['title'])
        cards.append(f'<article><a href="{ident}/overview.png"><img src="{ident}/overview.png" alt="{title}"></a>'
                     f'<h2>{title}</h2><p>Complete Jumper · default Silver Armor Guardian · {row["bytes"]/1e6:.1f} MB</p>'
                     f'<p><a href="{html.escape(row["archive"])}" download>Download .map</a> · '
                     f'<a href="{ident}/robot.png">View robot</a></p></article>')
    page='<!doctype html><html lang="en"><meta charset="utf-8"><title>Challenge maps</title><style>body{font:15px system-ui;background:#f3f1eb;margin:30px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px}article{background:white;padding:12px;border-radius:12px}img{width:100%}h2{font-size:19px}a{color:#234b32}</style><h1>Challenge maps</h1><p>Each .map includes a complete default robot and spawn point. A separate .skin can replace its appearance. Thumbnails show the environment; “View robot” shows the assembled model.</p><main>'+''.join(cards)+'</main></html>'
    (args.output / 'index.html').write_text(page,encoding='utf-8')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
