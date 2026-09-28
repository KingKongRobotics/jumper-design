"""Versioned Web appearance data, separate from the native MJCF approximation."""
import json,math,re,xml.etree.ElementTree as ET
from .package_io import PackageError,file_records
NAME='visual-appearance.json'
def appearance_document(materials):
 return dict(schema='kk-web-appearance/1',profile='be-web/1',colorSpace='srgb',materials=materials,lighting=dict(mode='web-default',builtInScale=1),renderer=dict(toneMapping='aces-filmic',exposure=.95,outputColorSpace='srgb',background='#eef1ed',fog=dict(near=6,far=16,color='#eef1ed')))
def validate_appearance(files):
 if NAME not in files:return
 if len(files[NAME])>512*1024:raise PackageError("Web appearance exceeds 512 KB")
 try:a=json.loads(files[NAME])
 except Exception as e:raise PackageError('Invalid visual appearance JSON') from e
 if not isinstance(a,dict) or a.get('schema')!='kk-web-appearance/1' or a.get('profile')!='be-web/1' or a.get('colorSpace')!='srgb':raise PackageError('Unsupported visual appearance profile')
 expected=appearance_document({})
 for key in ('lighting','renderer'):
  if a.get(key)!=expected[key]:raise PackageError('Web appearance must use the be-web/1 renderer and lighting')
 if not isinstance(a.get('materials'),dict) or not a['materials']:raise PackageError('Missing appearance materials')
 for name,m in a['materials'].items():
  if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.:-]*',name) or not isinstance(m,dict):raise PackageError('Invalid appearance material')
  for key in ('color','emissive'):
   if not isinstance(m.get(key),str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',m[key]):raise PackageError('Invalid appearance color')
  for key in ('opacity','roughness','metalness','emissiveIntensity'):
   v=m.get(key)
   if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 or (key!='emissiveIntensity' and v>1):raise PackageError('Invalid appearance material range')
  if m.get('side') not in ('front','back','double') or not isinstance(m.get('unlit'),bool) or not isinstance(m.get('flatShading'),bool):raise PackageError('Invalid appearance flags')
 manifest=json.loads(files['scene-package.json']);root=ET.fromstring(files[manifest['world']['file']]);names={m.get('name') for m in root.iter('material')}
 if set(a['materials'])-names:raise PackageError('Appearance references missing MJCF material')
 return a

def complete_appearance(files,*,linear=False):
 """Give every visible geom a named material. Physical attributes are untouched."""
 result=dict(files);manifest=json.loads(result['scene-package.json']);root=ET.fromstring(result[manifest['world']['file']]);asset=root.find('asset')
 if asset is None:asset=ET.SubElement(root,'asset')
 appearance=json.loads(result[NAME]) if NAME in result else appearance_document({})
 materials={m.get('name'):m for m in asset.findall('material')}
 def color(rgb):
  def encode(v):return 12.92*v if v<=.0031308 else 1.055*v**(1/2.4)-.055
  return '#'+''.join(f'{round(max(0,min(1,encode(x) if linear else x))*255):02x}' for x in rgb)
 for g in root.iter('geom'):
  rgba=list(map(float,g.get('rgba','1 1 1 1').split()))
  if rgba[3]==0:continue
  name=g.get('material')
  if not name:
   name='appearance_'+g.get('name',str(len(materials)))
   m=ET.SubElement(asset,'material',name=name,rgba=' '.join(map(str,rgba)),roughness='.9',metallic='0');materials[name]=m;g.set('material',name)
  if name not in appearance['materials']:
   m=materials[name];rgba=list(map(float,m.get('rgba','1 1 1 1').split()));c=color(rgba[:3]);emission=float(m.get('emission','0'))
   appearance['materials'][name]=dict(color=c,opacity=rgba[3],roughness=float(m.get('roughness','.9')),metalness=float(m.get('metallic','0')),emissive=c if emission else '#000000',emissiveIntensity=emission,unlit=False,side='front',flatShading=False)
 # Retain only actual referenced material assets (adapted maps remove some props).
 appearance['materials']={n:m for n,m in appearance['materials'].items() if n in materials}
 result[NAME]=(json.dumps(appearance,ensure_ascii=False,indent=2)+'\n').encode()
 result[manifest['world']['file']]=ET.tostring(root,encoding='utf-8',xml_declaration=True)+b'\n'
 manifest['world']['counts']['materials']=len(materials)
 manifest['files']=file_records({n:b for n,b in result.items() if n!='scene-package.json'})
 result['scene-package.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
 validate_appearance(result)
 return result
