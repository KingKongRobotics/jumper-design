"""Migrate library/1 sidecar previews to library/2 embedded thumbnails."""
from pathlib import Path
import argparse, hashlib, json, shutil, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src')]
from shellflow.package_io import read_archive,write_archive,file_records
from shellflow.package_preview import add_preview
from shellflow.content_library import publish
from shellflow.map_package import MAP_LIMITS

def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    candidate=out/'library'; profile=ROOT/'robots/jumper/profile.json'
    results=[]; migrated_skin=None
    for kind in ('skin','map'):
        category=kind+'s'; root=ROOT/'library'/category
        index=json.loads((root/'index.json').read_text(encoding='utf-8'))
        if index['schema'] != 'shellflow-'+kind+'-library/1':
            raise ValueError('Migration requires a library/1 source')
        for row in index['items']:
            source=root/row['file']; old=read_archive(source)
            assert hashlib.sha256(source.read_bytes()).hexdigest()==row['sha256']
            files=dict(old); name='skin-package.json' if kind=='skin' else 'scene-package.json'
            manifest=json.loads(files[name]); ident=manifest['id']
            if kind=='skin':
                parts=manifest['version'].split('.')
                manifest['version']='.'.join(parts[:-1]+[str(int(parts[-1])+1)])
            else:
                manifest['id']=ident.removeprefix('be-'); manifest['version']='1.0.1'
                assert migrated_skin is not None
                files={n:b for n,b in files.items() if not n.startswith('robot/')}
                files.update({'robot/'+n:b for n,b in migrated_skin.items()})
            image=(root/row['preview']).read_bytes()
            files.pop("preview/preview.png", None)
            add_preview(manifest,files,image)
            manifest['files']=file_records({n:b for n,b in files.items() if n!=name})
            files[name]=(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
            # Mechanical, visual, and world payload bytes are preserved exactly.
            changed={name,'preview/preview.png','robot/skin-package.json','robot/preview/preview.png'}
            assert all(files.get(n)==b for n,b in old.items() if n not in changed)
            archive=out/(manifest['id']+'.'+kind)
            if kind=='map':write_archive(archive,files,limits=MAP_LIMITS)
            else:write_archive(archive,files)
            result=publish(archive,candidate,profile)
            assert read_archive(archive)==files
            if kind=='skin' and ident=='mecha-tripo-v3':migrated_skin=files
            results.append({'kind':kind,'old_id':ident,'id':manifest['id'],'old_sha256':row['sha256'],
                            'sha256':result['sha256'],'model_bytes_unchanged':True})
            print(kind+' '+manifest['id']+': native validation and payload comparison passed',flush=True)
    dump(out/'migration-report.json',{'count':len(results),'items':results})
if __name__=='__main__':main()
