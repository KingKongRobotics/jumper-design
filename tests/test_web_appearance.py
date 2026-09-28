import json
from pathlib import Path
import pytest
from shellflow.web_appearance import appearance_document,validate_appearance
from shellflow.release_policy import require_web_appearance
from shellflow.package_io import PackageError

def fixture():
 material=dict(color='#809060',opacity=1,roughness=.85,metalness=0,emissive='#fff0d0',emissiveIntensity=.2,unlit=False,side='front',flatShading=False)
 a=appearance_document({'wall':material})
 return {'scene-package.json':b'{"world":{"file":"scene.xml"}}','scene.xml':b'<mujoco><asset><material name="wall"/></asset></mujoco>','visual-appearance.json':json.dumps(a).encode()}

def test_web_standard_material_roundtrip():
 f=fixture();assert validate_appearance(f)['materials']['wall']['emissive']=='#fff0d0'

@pytest.mark.parametrize('key,value',[('schema','unknown'),('colorSpace','linear'),('profile','other')])
def test_unknown_visual_semantics_rejected(key,value):
 f=fixture();a=json.loads(f['visual-appearance.json']);a[key]=value;f['visual-appearance.json']=json.dumps(a).encode()
 with pytest.raises(PackageError):validate_appearance(f)

def test_reference_must_exist():
 f=fixture();f['scene.xml']=b'<mujoco/>'
 with pytest.raises(PackageError,match='missing'):validate_appearance(f)

def test_missing_standard_cannot_release():
 with pytest.raises(PackageError,match='requires'):require_web_appearance({})

def test_dimming_cannot_silently_replace_web_standard():
 f=fixture();a=json.loads(f['visual-appearance.json']);a['lighting']['builtInScale']=.6;f['visual-appearance.json']=json.dumps(a).encode()
 with pytest.raises(PackageError,match='lighting'):validate_appearance(f)
