import json
from pathlib import Path
import pytest
from shellflow.release_policy import validate_release_policy
from shellflow.package_io import read_archive, PackageError
ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('ident',['be-home','studio','flat','obstacles','arena'])
def test_unwanted_map_release_is_rejected(ident):
    with pytest.raises(PackageError):validate_release_policy('map',{'id':ident},{})

def example():
    return {'id':'home','source':{'repository':'BE-UNLIMITED/be-unlimited','visualExport':{'method':'executed-web-scene-graph','meshBatches':1,'lineSegments':0}},'world':{'file':'scene.xml'}}, {'scene.xml':b'<mujoco><worldbody><geom name="visual_web_0" type="mesh" contype="0" conaffinity="0" mass="0"/></worldbody></mujoco>'}

def test_physics_only_export_cannot_claim_web_fidelity():
    m,f=example();m['source'].pop('visualExport')
    with pytest.raises(PackageError,match='visual layer'):validate_release_policy('map',m,f)

def test_visual_claim_must_match_actual_assets():
    m,f=example();f['scene.xml']=b'<mujoco><worldbody/></mujoco>'
    with pytest.raises(PackageError,match='must exist'):validate_release_policy('map',m,f)

@pytest.mark.parametrize('before,after',[(b'mass="0"',b'mass="1"'),(b'contype="0"',b'contype="1"')])
def test_visuals_cannot_change_physics(before,after):
    m,f=example();f['scene.xml']=f['scene.xml'].replace(before,after)
    with pytest.raises(PackageError,match='zero mass'):validate_release_policy('map',m,f)

def test_visual_inventory_mismatch_rejected():
    m,f=example();m['source']['visualExport']['meshBatches']=2
    with pytest.raises(PackageError,match='inventory'):validate_release_policy('map',m,f)

def test_current_maps_satisfy_release_policy():
    index=json.loads((ROOT/'library/maps/index.json').read_text(encoding='utf-8'))
    assert {row['id'] for row in index['items']} == {'warehouse', 'narrow-bridge', 'pouring', 'soccer', 'mine', 'shelf-maze', 'switchback-slopes', 'pingpong', 'home', 'park-pump-track', 'plaza', 'litter', 'bedroom'}
    for row in index['items']:
        files=read_archive(ROOT/'library/maps'/row['file'])
        validate_release_policy('map',json.loads(files['scene-package.json']),files)
