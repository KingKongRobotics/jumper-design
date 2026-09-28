// Execute the actual Web renderer's static scene graph, then serialize geometry.
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const be=path.resolve(process.argv[2]);const out=path.resolve(process.argv[3]);
const req=createRequire(path.join(be,'package.json'));const ts=req('typescript');const THREE=req('three');
const rounded=await import(pathToFileURL(req.resolve('three/examples/jsm/geometries/RoundedBoxGeometry.js')).href);
const cache=new Map();
function load(file){
 file=path.resolve(file);if(!path.extname(file))file+='.ts';
 if(cache.has(file))return cache.get(file).exports;
 const module={exports:{}};cache.set(file,module);
 const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const local=(name)=>name==='three'?THREE:name.includes('RoundedBoxGeometry')?rounded:name.startsWith('@/')?load(path.join(be,'src',name.slice(2))):name.startsWith('.')?load(path.resolve(path.dirname(file),name)):req(name);
 new Function('require','module','exports',code)(local,module,module.exports);return module.exports;
}
// Refuse silent drift between the frozen profile and the source Web renderer.
const canvasSource=fs.readFileSync(path.join(be,'src/components/simulator-canvas.tsx'),'utf8').replace(/\s+/g,'');
for(const required of ['renderer.toneMapping=THREE.ACESFilmicToneMapping','renderer.toneMappingExposure=0.95','renderer.outputColorSpace=THREE.SRGBColorSpace','newTHREE.HemisphereLight(0xffffff,0x90988b,1.7)','newTHREE.DirectionalLight(0xfff8ed,2.4)','sun.position.set(1.5,-2,4)']){
 if(!canvasSource.includes(required))throw Error('Web renderer no longer matches be-web/1; review and version the appearance profile: '+required);
}
const {buildSimulatorEnvironment}=load(path.join(be,'src/components/simulator-environment.ts'));
fs.mkdirSync(out,{recursive:true});
for(const id of ['home','soccer','plaza','warehouse','pingpong','pouring','mine','litter']){
 const root=buildSimulatorEnvironment(id);root.updateMatrixWorld(true);
 const describe=(m,color=m.color.getHexString())=>({color:'#'+color,opacity:m.opacity,roughness:m.roughness??.9,metalness:m.metalness??0,emissive:'#'+(m.emissive?.getHexString()??'000000'),emissiveIntensity:m.emissiveIntensity??0,unlit:!!(m.isMeshBasicMaterial||m.isLineBasicMaterial),side:m.side===THREE.DoubleSide?'double':m.side===THREE.BackSide?'back':'front',flatShading:!!m.flatShading});
 const props=root.userData.props;const records=[];const inverse=new THREE.Matrix4();
 const propRoots=new Map([...props].map(([id,obj])=>[obj,id]));
 const walk=(obj,owner=null)=>{
  if(!obj.visible)return;
  if(propRoots.has(obj))owner=propRoots.get(obj);
  if(obj.isMesh||obj.isLineSegments){
   if(obj.name==='ground'){records.push({name:'ground',color:obj.material.color.getHexString(),material:describe(obj.material)});}
   else{
    const geometry=obj.geometry;const positions=geometry.getAttribute('position');const colors=geometry.getAttribute('color');const indices=geometry.index;const normals=geometry.getAttribute('normal');
    const count=obj.isInstancedMesh?obj.count:1;
    for(let instance=0;instance<count;instance++){
     const matrix=obj.matrixWorld.clone();if(obj.isInstancedMesh){const im=new THREE.Matrix4();obj.getMatrixAt(instance,im);matrix.multiply(im);}
     if(owner){inverse.copy(props.get(owner).matrixWorld).invert();matrix.premultiply(inverse);}
     const mats=Array.isArray(obj.material)?obj.material:[obj.material];
     const groups=geometry.groups.length?geometry.groups:[{start:0,count:indices?indices.count:positions.count,materialIndex:0}];
     for(const group of groups){
      const material=mats[Array.isArray(obj.material)?(group.materialIndex??0):0];if(!material||!material.visible||material.opacity===0)continue;
      if(material.map)throw Error(`Unhandled texture ${id}/${obj.name}`);
      const stride=obj.isLineSegments?2:3;const buckets=new Map();const normalBuckets=new Map();const normalMatrix=new THREE.Matrix3().getNormalMatrix(matrix);
      for(let i=group.start;i<group.start+group.count;i+=stride){
       const vertices=[];const faceNormals=[];let color=material.color.clone();
       for(let j=0;j<stride;j++){const k=indices?indices.getX(i+j):i+j;vertices.push(new THREE.Vector3().fromBufferAttribute(positions,k).applyMatrix4(matrix).toArray());if(normals)faceNormals.push(new THREE.Vector3().fromBufferAttribute(normals,k).applyNormalMatrix(normalMatrix).toArray());if(j===0&&colors&&material.vertexColors)color.multiply(new THREE.Color().fromBufferAttribute(colors,k));}
       const key=color.getHexString();if(!buckets.has(key))buckets.set(key,[]);buckets.get(key).push(vertices);if(!normalBuckets.has(key))normalBuckets.set(key,[]);normalBuckets.get(key).push(faceNormals);
      }
      for(const [color,faces] of buckets)records.push({name:obj.name||obj.type,owner,color,material:describe(material,color),opacity:material.opacity,mode:obj.isLineSegments?'lines':'triangles',faces,normals:normalBuckets.get(color)});
     }
    }
   }
  }
  for(const child of obj.children)walk(child,owner);
 };
 walk(root);root.traverse(o=>{if(o.geometry){o.geometry=new THREE.BufferGeometry().copy(o.geometry);delete o.geometry.parameters;o.geometry.type='BufferGeometry';}});fs.mkdirSync(path.join(out,'reference'),{recursive:true});fs.writeFileSync(path.join(out,'reference',id+'.json'),JSON.stringify(root.toJSON()));fs.writeFileSync(path.join(out,id+'.json'),JSON.stringify(records));
 console.log(id,records.length);
}
