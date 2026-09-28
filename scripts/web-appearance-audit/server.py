from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
import json,base64
root=Path(__file__).resolve().parent
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(root),**kwargs)
 def do_POST(self):
  if self.path!='/save':self.send_error(404);return
  try:
   data=json.loads(self.rfile.read(int(self.headers['Content-Length'])));id=data['id']
   assert id in ['home','bedroom','soccer','plaza','warehouse','pingpong','pouring','mine','litter','narrow-bridge','shelf-maze','switchback-slopes']
   dest=root/('robot-renders' if data.get('kind')=='robot' else 'renders');dest.mkdir(exist_ok=True);image=base64.b64decode(data['image'].split(',',1)[1]);assert image.startswith(b'\x89PNG')
   (dest/(id+'.png')).write_bytes(image);(dest/(id+'.json')).write_text(json.dumps(data['report'],indent=2),encoding='utf-8');self.send_response(200);self.end_headers();self.wfile.write(b'ok')
  except Exception as e:self.send_error(400,str(e))
import argparse
p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8881);args=p.parse_args()
ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
