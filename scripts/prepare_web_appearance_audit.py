"""Prepare compiled environment payloads for the real Three importer visual audit."""
from pathlib import Path
import sys,json,shutil,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import numpy as np,mujoco
from export_map_collection import ORDER

def payload(files,include_robot=False):
 manifest=json.loads(files['scene-package.json']);app=json.loads(files['visual-appearance.json'])
 if include_robot:
  from shellflow.map_package import compose_default
  m,d,_=compose_default(files,profile=ROOT/'robots/jumper/profile.json')
 else:
  m=mujoco.MjModel.from_xml_string(files[manifest['world']['file']].decode(),assets=files);d=mujoco.MjData(m);mujoco.mj_forward(m,d)
 q=lambda a:[float(a[1]),float(a[2]),float(a[3]),float(a[0])]
 out=dict(prefix='',appearance=app,bodies=[],nodes=[],materials=[],textures=[],meshes=[],lights=[],flex=[],skipped=[])
 for i in range(m.nbody):out['bodies'].append(dict(name=m.body(i).name,pos=d.xpos[i].tolist(),quat=q(d.xquat[i])))
 for i in range(m.ntex):
  n=int(m.tex_width[i]*m.tex_height[i]*m.tex_nchannel[i]);a=int(m.tex_adr[i]);out['textures'].append(dict(width=int(m.tex_width[i]),height=int(m.tex_height[i]),channels=int(m.tex_nchannel[i]),data=m.tex_data[a:a+n].tolist()))
 for i in range(m.nmat):
  name=m.material(i).name;mat=dict(name=name,rgba=m.mat_rgba[i].tolist(),texrepeat=m.mat_texrepeat[i].tolist(),shininess=float(m.mat_shininess[i]),roughness=float(m.mat_roughness[i]),metalness=float(m.mat_metallic[i]),emission=float(m.mat_emission[i]))
  tex=int(m.mat_texid[i,1])
  if tex>=0:mat['texture']=tex
  local=name.removeprefix('scn_') if include_robot else name
  if local in app['materials']:mat['web']=app['materials'][local]
  out['materials'].append(mat)
 for i in range(m.nmesh):
  f0=int(m.mesh_faceadr[i]);nf=int(m.mesh_facenum[i]);v0=int(m.mesh_vertadr[i]);n0=int(m.mesh_normaladr[i]);t0=int(m.mesh_texcoordadr[i])
  faces=m.mesh_face[f0:f0+nf];normals=m.mesh_facenormal[f0:f0+nf]
  mesh=dict(positions=m.mesh_vert[v0+faces].reshape(-1).tolist(),normals=m.mesh_normal[n0+normals].reshape(-1).tolist())
  if t0>=0:
   uv=m.mesh_texcoord[t0+m.mesh_facetexcoord[f0:f0+nf]].copy();uv[:,:,1]=1-uv[:,:,1];mesh['uvs']=uv.reshape(-1).tolist()
  out['meshes'].append(mesh)
 bounds=[]
 for i in range(m.ngeom):
  g=dict(name=m.geom(i).name,body=int(m.geom_bodyid[i]),type=int(m.geom_type[i]),pos=m.geom_pos[i].tolist(),quat=q(m.geom_quat[i]),size=m.geom_size[i].tolist(),rgba=m.geom_rgba[i].tolist(),group=int(m.geom_group[i]))
  if m.geom_matid[i]>=0:g['material']=int(m.geom_matid[i])
  if m.geom_type[i]==7:g['mesh']=int(m.geom_dataid[i])
  out['nodes'].append(g)
  if m.geom_rgba[i,3]>.01 and m.geom_type[i]!=0 and m.geom_group[i]<3:
   extent=abs(d.geom_xmat[i].reshape(3,3))@m.geom_size[i];bounds.extend([d.geom_xpos[i]-extent,d.geom_xpos[i]+extent])
 # Flex data is dynamic; include reset-state vertices with its material.
 for i in range(m.nflex):
  start=int(m.flex_vertadr[i]);count=int(m.flex_vertnum[i]);a=int(m.flex_elemadr[i]);n=int(m.flex_elemnum[i]);dim=int(m.flex_dim[i]);tri=m.flex_elem[a*(dim+1):(a+n)*(dim+1)]
  f=dict(id=mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_FLEX,i),vertexAddress=start,vertexCount=count,triangles=tri.tolist(),rgba=m.flex_rgba[i].tolist(),vertices=d.flexvert_xpos[start:start+count].reshape(-1).tolist())
  if m.flex_matid[i]>=0:f['material']=int(m.flex_matid[i])
  out['flex'].append(f)
 if include_robot:out['robotPosition']=d.xpos[m.body('base_link').id].tolist()
 out['bounds']=[np.min(bounds,axis=0).tolist(),np.max(bounds,axis=0).tolist()]
 return out
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--robot-library',type=Path);args=parser.parse_args()
 if args.robot_library:
  from shellflow.package_io import read_archive
  from shellflow.map_package import MAP_LIMITS
  dest=ROOT/'outputs/web-appearance-audit/robot-payloads';dest.mkdir(parents=True,exist_ok=True)
  for row in json.loads((args.robot_library/'maps/index.json').read_text(encoding='utf-8'))['items']:
   f=read_archive(args.robot_library/'maps'/row['file'],limits=MAP_LIMITS)
   (dest/(row['id']+'.json')).write_text(json.dumps(payload(f,True),separators=(',',':')),encoding='utf-8')
  raise SystemExit(0)
 dest=ROOT/'outputs/web-appearance-audit';(dest/'payloads').mkdir(parents=True,exist_ok=True)
 for id in ORDER:
  source=ROOT/'library/map-sources/authored'/id
  if not source.exists():source=ROOT/'library/map-sources/be-unlimited'/id
  manifest=json.loads((source/'scene-package.json').read_text(encoding='utf-8'));files={n:(source/n).read_bytes() for n in manifest['files']};files['scene-package.json']=(source/'scene-package.json').read_bytes()
  (dest/'payloads'/f'{id}.json').write_text(json.dumps(payload(files),separators=(',',':')),encoding='utf-8');print(id,flush=True)
