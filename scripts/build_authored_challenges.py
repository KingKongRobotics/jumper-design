"""Reproducible authored challenges. Static task descriptions do not execute APP logic."""
from pathlib import Path
import sys,json,xml.etree.ElementTree as E
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from shellflow.package_io import file_records,read_archive
from shellflow.map_package import export_environment,compose_default,MAP_LIMITS
from shellflow.packages import verify_package
from export_map_collection import render_overview
from preview_simulation import save_png
import mujoco

def vec(v): return ' '.join(str(x) for x in v)
class Scene:
 def __init__(self,ident,title,spawn,ground=0):
  self.ident,self.title,self.spawn=ident,title,spawn
  self.root=E.Element('mujoco',model=ident)
  E.SubElement(self.root,'compiler',angle='radian')
  self.asset=E.SubElement(self.root,'asset');self.world=E.SubElement(self.root,'worldbody');self.files={}
  E.SubElement(self.world,'geom',name='ground',type='plane',pos=f'0 0 {ground}',size='20 20 .1',rgba='.24 .29 .28 1',friction='1 .005 .0001')
  E.SubElement(self.world,'light',name='sun',pos='0 0 7',dir='0 0 -1',directional='true',diffuse='.25 .25 .25')
 def box(self,name,pos,size,color,visual=False,parent=None):
  a=dict(name=name,type='box',pos=vec(pos),size=vec(size),rgba=vec(color),friction='1 .005 .0001')
  if visual:a.update(contype='0',conaffinity='0',mass='0')
  return E.SubElement(parent if parent is not None else self.world,'geom',**a)
 def marker(self,name,x,y,z,color):
  self.box(name+'_paint',(x,y,z+.001),(.22,.22,.001),color,True)
  E.SubElement(self.world,'site',name=name,pos=vec((x,y,z+.005)),size='.20 .20 .005',type='box',rgba='0 0 0 0')
 def finish(self,readme):
  self.files['scene.xml']=E.tostring(self.root,encoding='utf-8',xml_declaration=True)
  self.files['README.md']=readme.encode('utf-8')
  props=[]
  for b in self.world.iter('body'):
   f=b.find('freejoint')
   if f is not None:props.append(dict(name=b.get('name'),body=b.get('name'),freeJoint=True,freeJointName=f.get('name'),geoms=[g.get('name') for g in b.iter('geom')],position=list(map(float,b.get('pos').split()))))
  counts={k:len(list((self.asset if k in ('textures','materials','meshes') else self.world).iter(t))) for k,t in [('geoms','geom'),('bodies','body'),('lights','light'),('textures','texture'),('materials','material'),('meshes','mesh')]}
  manifest=dict(schema='kk-scene-package/1',id=self.ident,title=self.title,version='1.1.0',use='watching',exportedBy=dict(repo='robot-shell-workflow',tool='scripts/build_authored_challenges.py'),source=dict(repository='robot-shell-workflow',authoredGround=True),requiredCapabilities=['rigid'],world=dict(file='scene.xml',assetDir='',terrainType='none',ground=dict(geom='ground'),counts=counts,attach=dict(prefix='scn_')),props=props,flex=[],lights=[dict(name='sun')],cameras=[],spawn=dict(position=self.spawn,yaw=0),files=file_records(self.files))
  self.files['scene-package.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
  from shellflow.web_appearance import complete_appearance
  self.files=complete_appearance(self.files)
  source=ROOT/'library/map-sources/authored'/self.ident
  for n,data in self.files.items():
   p=source/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
  return self

def bridge():
 s=Scene('narrow-bridge','Narrow Bridge',[-1.95,0,0],-.16)
 s.box('basin',(0,0,-.173),(2.8,1.15,.015),(.13,.35,.40,1))
 for x,n,c in [(-1.95,'start',(.35,.48,.37,1)),(1.95,'exit',(.38,.53,.4,1))]:
  s.box(n+'_platform',(x,0,-.08),(.55,.60,.08),c);s.marker(n,x,0,0,(.9,.74,.21,1))
 s.box('bridge_deck',(0,0,-.025),(1.4,.215,.025),(.45,.28,.13,1))
 for i in range(28):s.box(f'plank_{i}',(-1.35+i*.1,0,.0005),(.048,.211,.0005),(.64 if i%2 else .56,.39,.19,1),True)
 for y in [-.208,.208]:s.box('edge_'+str(y),(0,y,.002),(1.4,.007,.002),(.97,.77,.2,1),True)
 return s.finish('# Narrow Bridge\n\nUnits are meters; X points forward and Z points up. The bridge is 2.8 m long and 0.43 m wide, without railings, above a 0.16 m drop. Jumper has a 0.3848 m collision-envelope width in its preview pose, leaving approximately 22.6 mm of static clearance per side when centered. This does not validate dynamic gait.\n\nChallenge: enter from start and remain on the deck until exit. The app decides whether touching the basin below counts as failure. This package contains no controller or automatic scoring.\n')

def maze():
 s=Scene('shelf-maze','Shelf Maze',[-2.05,-2.05,0],-.03)
 s.box('floor',(0,0,-.025),(2.6,2.6,.025),(.58,.61,.57,1))
 # Alternating barriers leave 0.85 m end passages; central aisles are 1.1 m.
 shelves=[(-1.3,-.425,.10,1.925),(0,.425,.10,1.925),(1.3,-.425,.10,1.925)]
 for i,(x,y,hx,hy) in enumerate(shelves):
  s.box(f'shelf_{i}_plinth',(x,y,.14),(hx,hy,.14),(.24,.30,.34,1))
  for z in [.3,.55,.8]:s.box(f'shelf_{i}_level_{z}',(x,y,z),(hx+.035,hy,.022),(.38,.45,.49,1))
  for j,yy in enumerate([y-hy+.045,y,y+hy-.045]):
   s.box(f'shelf_{i}_post_{j}',(x,yy,.4),(.035,.035,.4),(.18,.24,.28,1))
   for k,z in enumerate([.4,.65]):s.box(f'shelf_{i}_stock_{j}_{k}',(x,yy,z),(.08,.12,.075),(.64,.48+.06*k,.29,1),True)
 for y in [-2.45,2.45]:s.box('boundary_y'+str(y),(0,y,.12),(2.5,.05,.12),(.34,.4,.4,1))
 for x in [-2.45,2.45]:s.box('boundary_x'+str(x),(x,0,.12),(.05,2.45,.12),(.34,.4,.4,1))
 tasks=[('red',(-2.02,-1.4),(-.65,1.35),(.84,.16,.13,1)),('blue',(-.65,.6),(.65,-1.3),(.13,.37,.83,1)),('yellow',(.65,-.55),(2.02,1.3),(.92,.71,.10,1))]
 for name,p,t,c in tasks:
  b=E.SubElement(s.world,'body',name='prop:'+name,pos=vec((*p,.036)))
  E.SubElement(b,'freejoint',name='prop:'+name+':free')
  g=s.box(name+'_cube',(0,0,0),(.035,.035,.035),c,parent=b);g.set('mass','.04')
  # Outlined drop region leaves the floor visible and is not a physical step.
  for dx,dy,hx,hy in [(-.22,0,.012,.23),(.22,0,.012,.23),(0,-.22,.23,.012),(0,.22,.23,.012)]:s.box(name+f'_target_{dx}_{dy}',(t[0]+dx,t[1]+dy,.002),(hx,hy,.002),c,True)
  E.SubElement(s.world,'site',name='target_'+name,pos=vec((*t,.04)),size='.2 .2 .08',type='box',rgba='0 0 0 0')
 s.marker('start',-2.05,-2.05,0,(.7,.85,.69,1));s.marker('exit',2.02,2.03,0,(.7,.85,.69,1))
 return s.finish('# Shelf Maze\n\nThe 5.2 × 5.2 m field has three alternating shelf barriers that form four winding aisles. Straight aisles have at least 1.0 m clear width; end passages have 0.775 m clear width, allowing for a 0.385 m static robot width and turning clearance. Shelf bases have solid collision geometry, so the robot cannot cut through them.\n\nComplete these stages in order:\n1. Move prop:red from (-2.02,-1.4) to target_red (-0.65,1.35).\n2. Move prop:blue from (-0.65,0.6) to target_blue (0.65,-1.3).\n3. Move prop:yellow from (0.65,-0.55) to target_yellow (2.02,1.3), then reach exit.\n\nEach cube is 7 cm wide and weighs 40 g; the target region is about 0.42 m across. The app may mark a stage complete after the cube center enters the target region, rests on the ground, and stays at low speed for one second. The app implements ordering, timing, and resets. This package provides named objects and target sites, without scoring logic or a validated grasp strategy. Coordinates are map-local meters; composed names have the scn_ prefix.\n')

def slopes():
 s=Scene('switchback-slopes','Switchback Slopes',[-2.22,-1.1,0],-.04)
 s.box('foundation',(0,0,-.035),(2.8,1.65,.03),(.43,.47,.44,1))
 faces=[(1,3,2),(1,4,3),(5,6,7),(5,7,8),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,4,8),(3,8,7),(4,1,5),(4,5,8)]
 for i,y in enumerate([-1.1,0,1.1]):
  z0,z1=[(.0,.45),(.9,.45),(.9,1.35)][i]
  vertices=[(-1.8,-.35,-.04),(1.8,-.35,-.04),(1.8,.35,-.04),(-1.8,.35,-.04),(-1.8,-.35,z0),(1.8,-.35,z1),(1.8,.35,z1),(-1.8,.35,z0)]
  name=f'ramp_{i}';path=f'assets/{name}.obj'
  s.files[path]=(''.join('v '+vec(v)+'\n' for v in vertices)+''.join('f '+vec(f)+'\n' for f in faces)).encode()
  E.SubElement(s.asset,'mesh',name=name,file=path)
  E.SubElement(s.world,'geom',name=name,type='mesh',mesh=name,pos=f'0 {y} 0',rgba=vec([(.38,.57,.59,1),(.52,.62,.47,1),(.70,.55,.36,1)][i]),friction='1 .005 .0001')
  import math
  angle=-math.atan2(z1-z0,3.6)
  for edge in [-.335,.335]:
   g=s.box(f'edge_{i}_{edge}',(0,y+edge,(z0+z1)/2+.003),(math.hypot(3.6,.45)/2,.009,.003),(.94,.85,.57,1),True);g.set('euler',f'0 {angle} 0')
 for name,x,y,z,hy in [('start',-2.22,-1.1,0,.35),('turn_1',2.22,-.55,.45,.90),('turn_2',-2.22,.55,.9,.90),('exit',2.22,1.1,1.35,.35)]:
  s.box(name+'_platform',(x,y,(z-.04)/2),(.42,hy,(z+.04)/2),(.53,.56,.49,1))
  s.marker(name,x,y,z,(.90,.77,.27,1))
 return s.finish('# Switchback Slopes\n\nThree ramps are each 0.70 m wide and 3.60 m long horizontally. Each rises 0.45 m at about 7.13°, reaching 1.35 m at the end. Each ramp is a solid convex wedge with collision. Platforms meet the ramp edges and are 0.84 m wide, allowing turns between alternating ramps.\n\nRoute: start → ramp_0 east → turn_1 → ramp_1 west → turn_2 → ramp_2 east → exit. The app checks waypoint order, falls, and timing. This map does not provide a validated gait.\n')

def build(scene,output,preview_dir):
 folder=output/scene.ident;folder.mkdir(parents=True,exist_ok=True)
 import shutil
 shutil.copy2(preview_dir/(scene.ident+'.png'),folder/'overview.png')
 archive=folder/(scene.ident+'.map')
 profile=ROOT/'robots/jumper/profile.json'
 from shellflow.defaults import default_skin_path
 export_environment(scene.files,archive,default_skin_path(ROOT),profile,preview=folder/'overview.png')
 verification=verify_package(archive,platform_profile=profile,mujoco=True)
 m,d,composition=compose_default(read_archive(archive,limits=MAP_LIMITS),profile=profile)
 m.vis.global_.offwidth=1000;m.vis.global_.offheight=750
 c=mujoco.MjvCamera();c.lookat[:]=d.xpos[m.body('base_link').id]+[.25,0,.1];c.distance=1.8;c.azimuth=135;c.elevation=-35
 with mujoco.Renderer(m,height=750,width=1000) as r:r.update_scene(d,c);save_png(folder/'robot.png',r.render())
 (folder/'verification.json').write_text(json.dumps(dict(validation=verification,composition=composition),ensure_ascii=False,indent=2),encoding='utf-8')
 print(scene.ident,archive.stat().st_size,flush=True)
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--preview-dir',type=Path,help='Reviewed Web standard thumbnail directory')
 parser.add_argument('--output',type=Path,help='New candidate directory; existing archives are never overwritten')
 parser.add_argument('--sources-only',action='store_true',help='Generate sources before Web preview acceptance')
 args=parser.parse_args()
 scenes=[bridge(),maze(),slopes()]
 if not args.sources_only:
  if args.output is None or args.preview_dir is None:parser.error('--output and --preview-dir are required unless --sources-only')
  for scene in scenes:build(scene,args.output,args.preview_dir)
