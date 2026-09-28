"""Formal libraries publish self-contained files without per-item directories."""
import json
from pathlib import Path
import pytest
from shellflow.content_library import publish
from shellflow.package_io import read_archive, write_archive, file_records, PackageError
ROOT=Path(__file__).resolve().parents[1]
PROFILE=ROOT/'robots/jumper/profile.json'
SKIN=ROOT/'library/skins/jumper-original.skin'

def test_flat_publication_and_embedded_preview(tmp_path):
    result=publish(SKIN,tmp_path,PROFILE)
    root=tmp_path/'skins'
    assert Path(result['file'])==root/'jumper-original.skin'
    assert sorted(p.name for p in root.iterdir())==['index.json','jumper-original.skin']
    index=json.loads((root/'index.json').read_text(encoding='utf-8'))
    assert index['schema']=='shellflow-skin-library/2'
    row=index['items'][0]
    assert row['file']=='jumper-original.skin'
    files=read_archive(root/row['file']);manifest=json.loads(files['skin-package.json'])
    assert row['preview']=={'path':'preview/preview.png',**manifest['files']['preview/preview.png']}
    assert index['embedded_preview_bytes']==len(files[row['preview']['path']])
    assert publish(SKIN,tmp_path,PROFILE)['unchanged']

def test_missing_embedded_preview_cannot_publish(tmp_path):
    files=read_archive(SKIN);manifest=json.loads(files['skin-package.json'])
    files.pop('preview/preview.png')
    manifest['files']=file_records({n:b for n,b in files.items() if n!='skin-package.json'})
    files['skin-package.json']=json.dumps(manifest).encode()
    package=tmp_path/'missing.skin';write_archive(package,files)
    with pytest.raises(PackageError,match='embedded preview'):
        publish(package,tmp_path/'library',PROFILE)
    assert not (tmp_path/'library').exists()

def test_sidecar_cannot_override_package_preview(tmp_path):
    image=tmp_path/'fake.png';image.write_bytes(b'not the embedded image')
    with pytest.raises(PackageError,match='differs'):
        publish(SKIN,tmp_path/'library',PROFILE,preview=image)
    assert not (tmp_path/'library').exists()
