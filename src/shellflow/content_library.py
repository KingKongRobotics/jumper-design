"""Publish validated current releases into the portable Git content library."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from .package_io import PackageError, read_archive, safe_path
from .packages import verify_package
from .package_preview import validate_preview, PREVIEW_PATH
from .release_policy import validate_release_policy


def sha(path):
    with Path(path).open('rb') as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
        return digest.hexdigest()


def publish(package, library_root, profile, *, preview=None):
    """Fail before writing on invalid packages, duplicate titles, or replacements.

    Existing identical versions are idempotent. A new version must be published
    to a clean candidate library, reviewed, then selected in Git; old releases
    are never silently overwritten by this command.
    """
    package, library_root = Path(package), Path(library_root)
    checked = verify_package(package, platform_profile=Path(profile), mujoco=True)
    kind = checked['kind']
    expected = {'skin': 'kk-skin-package/3', 'map': 'kk-scene-package/2'}
    if checked['schema'] != expected[kind]:
        raise PackageError('Only current display skins and maps with a default robot may be published')
    files = read_archive(package)
    manifest = json.loads(files['skin-package.json' if kind == 'skin' else 'scene-package.json'])
    validate_release_policy(kind, manifest, files)
    validate_preview(manifest, files)
    if PREVIEW_PATH not in files:
        raise PackageError('Formal releases require an embedded preview; export with --preview first')
    image_record = {'path': PREVIEW_PATH, **manifest['files'][PREVIEW_PATH]}
    image_bytes = files[image_record['path']]
    if preview is not None and Path(preview).read_bytes() != image_bytes:
        raise PackageError('External preview differs from the embedded package preview')
    ident, title = manifest['id'], manifest.get('title', '')
    if not title or title != title.strip():
        raise PackageError('A clean display title is required')
    filename = safe_path(ident + '.' + kind)
    if '/' in filename or '/' in safe_path(ident):
        raise PackageError('Library titles and IDs must be single path components')
    root = library_root / ('skins' if kind == 'skin' else 'maps')
    index_path = root / 'index.json'
    index = json.loads(index_path.read_text(encoding='utf-8')) if index_path.exists() else {
        'schema': 'shellflow-' + kind + '-library/2', 'items': []}
    if index['schema'] != 'shellflow-' + kind + '-library/2':
        raise PackageError('Legacy library index requires migration to embedded previews')
    if any(r['id'] != ident and r['title'] == title for r in index['items']):
        raise PackageError('A different library item already uses this title')
    target = root / filename
    existing = next((r for r in index['items'] if r['id'] == ident), None)
    if existing:
        if (existing['sha256'] != checked['sha256'] or existing['title'] != title
                or not (root / existing['file']).is_file()
                or sha(root / existing['file']) != checked['sha256']):
            raise PackageError('Existing release differs; publish to a clean candidate library first')
        return {'ok': True, 'unchanged': True, 'file': str(root / existing['file'])}
    if target.exists():
        raise PackageError('Unindexed destination already exists')
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.publish-', dir=root) as temp:
        stage = Path(temp) / filename
        shutil.copyfile(package, stage)
        if sha(stage) != checked['sha256']:
            raise PackageError('Package changed during library publication')
        row = {'id': ident, 'title': title, 'version': manifest.get('version', '1.0.0'),
               'schema': checked['schema'], 'file': filename,
               'bytes': package.stat().st_size, 'sha256': checked['sha256']}
        if kind == 'skin':
            row.update(platform_id=manifest['platform']['id'],
                       profile_sha256=manifest['platform']['profile_sha256'])
        else:
            row.update(platform_id=manifest['robot']['platformId'],
                       profile_sha256=manifest['robot']['profileSha256'],
                       default_skin_id=manifest['robot']['skinId'])
        row.update(preview=dict(image_record))
        stage.rename(target)
    index['items'].append(row)
    index['count'] = len(index['items'])
    index['total_' + kind + '_bytes'] = sum(r['bytes'] for r in index['items'])
    index['embedded_preview_bytes'] = sum(r['preview']['bytes'] for r in index['items'])
    temporary_index = root / '.index.json.tmp'
    temporary_index.write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary_index.replace(index_path)
    return {'ok': True, 'file': str(target), 'index': str(index_path), 'sha256': checked['sha256']}
