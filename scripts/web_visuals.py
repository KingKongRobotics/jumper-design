"""Add Web-authored static and prop-local visuals without changing physics."""
from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET
import numpy as np

def apply_visuals(files, records):
    result=dict(files);root=ET.fromstring(files['scene.xml']);world=root.find('worldbody')
    for parent in root.iter():
        for child in list(parent):
            if child.tag=='geom' and child.get('name','').startswith(('visual_soccer_','visual_web_')):parent.remove(child)
    asset=root.find('asset')
    if asset is None:asset=ET.SubElement(root,'asset')
    for g in world.iter('geom'):
        if g.get('type')!='plane':
            rgba=g.get('rgba','1 1 1 1').split();rgba[-1]='0';g.set('rgba',' '.join(rgba))
    batches={};normal_batches={};lines=[];appearance={};owners={b.get('name'):b for b in world.iter('body')}
    for r in records:
        if r['name']=='ground':
            color=r['color'];ground=world.find("geom[@name='ground']");ground.set('rgba',' '.join(str(int(color[i:i+2],16)/255) for i in (0,2,4))+' 1');ground.set('material','visual_web_ground');ground.set('size','20 20 .1');appearance['visual_web_ground']=r['material'];ET.SubElement(asset,'material',name='visual_web_ground',rgba=ground.get('rgba'),roughness=str(r['material']['roughness']),metallic=str(r['material']['metalness']));continue
        if r['mode']=='lines':lines.append(r);continue
        key=(r.get('owner'),r['color'],r['opacity'],json.dumps(r['material'],sort_keys=True));batches.setdefault(key,[]).extend(r['faces']);normal_batches.setdefault(key,[]).extend(r.get('normals',[]))
    for i,((owner,color,alpha,material_json),faces) in enumerate(batches.items()):
        triangles=np.array(faces,dtype=float)
        normals=np.array(normal_batches[(owner,color,alpha,material_json)],dtype=float)
        keep=np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]),axis=1)>1e-13
        triangles=triangles[keep];normals=normals[keep]
        points=triangles.reshape(-1,3)
        # MuJoCo requires a volume even for a purely visual planar mesh.
        _,singular,axes=np.linalg.svd(points-points.mean(axis=0),full_matrices=False)
        if singular[-1]<1e-7:
            triangles=np.concatenate([triangles,triangles[:,::-1,:]-axes[-1]*.00001]);normals=np.concatenate([normals,-normals[:,::-1,:]])
        vertices=[];lookup={};indices=[]
        for tri in triangles:
            face=[]
            for vertex in tri:
                key=tuple(round(float(v),9) for v in vertex)
                if key not in lookup:lookup[key]=len(vertices)+1;vertices.append(key)
                face.append(lookup[key])
            indices.append(face)
        name=f'visual_web_{i}';path=f'assets/web/{name}.obj'
        obj='\n'.join(['v '+' '.join(map(str,v)) for v in vertices]+['vn '+' '.join(map(str,n)) for tri in normals for n in tri]+['f '+' '.join(f'{v}//{i*3+j+1}' for j,v in enumerate(f)) for i,f in enumerate(indices)])+'\n';result[path]=obj.encode()
        ET.SubElement(asset,'mesh',name=name,file=path)
        material=json.loads(material_json);matname=f'visual_web_mat_{i}';appearance[matname]=material
        ET.SubElement(asset,'material',name=matname,rgba=' '.join(str(int(color[j:j+2],16)/255) for j in (0,2,4))+f' {alpha}',roughness=str(material['roughness']),metallic=str(material['metalness']),shininess=str(1-material['roughness']),emission=str(min(1,material['emissiveIntensity']) if material['emissive']!='#000000' else 0))
        parent=world if owner is None else owners['prop:'+owner]
        ET.SubElement(parent,'geom',name=name,type='mesh',mesh=name,material=matname,rgba=' '.join(str(int(color[j:j+2],16)/255) for j in (0,2,4))+f' {alpha}',contype='0',conaffinity='0',mass='0',group='2')
    count=0
    for record in lines:
        parent=world if record.get('owner') is None else owners['prop:'+record['owner']]
        color=record['color']
        matname='visual_web_line_mat_'+str(count);appearance[matname]=record['material']
        ET.SubElement(asset,'material',name=matname,rgba=' '.join(str(int(color[j:j+2],16)/255) for j in (0,2,4))+f' {record["opacity"]}')
        for a,b in record['faces']:
            if np.linalg.norm(np.array(a)-b)<1e-8:continue
            ET.SubElement(parent,'geom',name=f'visual_web_line_{count}',type='capsule',material=matname,fromto=' '.join(map(str,a+b)),size='.0015',rgba=' '.join(str(int(color[j:j+2],16)/255) for j in (0,2,4))+f' {record["opacity"]}',contype='0',conaffinity='0',mass='0',group='2');count+=1
    ET.indent(root);result['scene.xml']=ET.tostring(root,encoding='utf-8',xml_declaration=True)+b'\n'
    manifest=json.loads(result['scene-package.json']);manifest['version']='1.2.0';manifest['world']['counts']['materials']=len(list(asset.iter('material')));manifest['world']['counts']['geoms']=len(list(world.iter('geom')));manifest['world']['counts']['meshes']=len(list(asset.iter('mesh')))
    for prop in manifest['props']:prop['geoms']=[g.get('name') for g in owners[prop['body']].iter('geom')]
    manifest['source']['visualExport']={'method':'executed-web-scene-graph','meshBatches':len(batches),'lineSegments':count,'dynamicVisuals':'initial-pose; application-driven animations not included'}
    from shellflow.web_appearance import appearance_document
    result['visual-appearance.json']=(json.dumps(appearance_document(appearance),ensure_ascii=False,indent=2)+'\n').encode()
    from shellflow.package_io import file_records
    manifest['files']=file_records({n:b for n,b in result.items() if n!='scene-package.json'})
    result['scene-package.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    return result
