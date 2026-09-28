"""Build static galleries using only embedded package thumbnails."""
import argparse, base64, hashlib, html, json, shutil, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from shellflow.package_io import read_archive
from shellflow.package_preview import validate_preview, PREVIEW_PATH

def build(library,output):
    output.mkdir(parents=True,exist_ok=True)
    for kind in ('skin','map'):
        category=kind+'s'; root=library/category
        index=json.loads((root/'index.json').read_text(encoding='utf-8'))
        cards=[]
        for row in index['items']:
            package=root/row['file']; payload=package.read_bytes()
            if hashlib.sha256(payload).hexdigest()!=row['sha256']:raise ValueError('Package hash mismatch')
            files=read_archive(package)
            manifest=json.loads(files['skin-package.json' if kind=='skin' else 'scene-package.json'])
            validate_preview(manifest,files)
            if {'path':PREVIEW_PATH,**manifest['files'][PREVIEW_PATH]}!=row['preview']:raise ValueError('Index preview mismatch')
            uri='data:image/png;base64,'+base64.b64encode(files[PREVIEW_PATH]).decode()
            dest=output/'downloads'/category/Path(row['file']).name;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(package,dest)
            title=html.escape(row['title']);link=html.escape(dest.relative_to(output).as_posix())
            detail=''
            if kind=='map' and (output/row['id']/'robot.png').is_file():
                detail=f' · <a href="{row["id"]}/robot.png">View robot</a>'
            cards.append(f'<article><img src="{uri}" alt="{title}"><h2>{title}</h2><p>{row["bytes"]/1e6:.2f} MB</p><a href="{link}" download>Download .{kind}</a>{detail}</article>')
        title='Challenge maps' if kind=='map' else 'Robot skins'
        note='Thumbnails show the environment only. Each map includes a complete default robot and spawn point.' if kind=='map' else 'Display-only complete robot skins; print files are distributed separately.'
        page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+title+'</title><style>body{font:15px system-ui;background:#f3f1eb;margin:30px;color:#212721}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px}article{background:white;padding:12px;border-radius:12px}img{width:100%;aspect-ratio:4/3;object-fit:contain}h2{font-size:19px}a{color:#234b32}</style><nav><a href="index.html">Maps</a> · <a href="skins.html">Skins</a></nav><h1>'+str(len(cards))+' '+title+'</h1><p>'+note+' All thumbnails are embedded in their download packages.</p><main>'+''.join(cards)+'</main></html>'
        (output/('index.html' if kind=='map' else 'skins.html')).write_text(page,encoding='utf-8')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--library',type=Path,default=ROOT/'library');p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.library,a.output)
