"""Portable soccer visual details matching BE's simulator-scene-details.ts.

These geoms are visual only: the original ground/goals retain collisions.
"""
import math
import xml.etree.ElementTree as ET

def add_soccer_visuals(root):
    world=root.find('worldbody')
    if world.find("geom[@name='visual_soccer_grass_0']") is not None:
        return
    ground=world.find("geom[@name='ground']")
    ground.set('rgba','0.447058824 0.549019608 0.388235294 1')
    def color(value):
        return ' '.join(str(int(value[i:i+2],16)/255) for i in (1,3,5))+' 1'
    def box(name,pos,size,hexcolor,rotation=0):
        ET.SubElement(world,'geom',name='visual_soccer_'+name,type='box',
            pos=' '.join(map(str,pos)),size=' '.join(str(n/2) for n in size),
            euler=f'0 0 {rotation}',rgba=color(hexcolor),contype='0',conaffinity='0',group='2',mass='0')
    def line(name,a,b,width,hexcolor,z=.0008):
        box(name,[(a[0]+b[0])/2,(a[1]+b[1])/2,z],
            [math.dist(a,b),width,.0004],hexcolor,math.atan2(b[1]-a[1],b[0]-a[0]))
    def outline(name,x,y,hx,hy):
        for i,(a,b) in enumerate([([x-hx,y-hy],[x+hx,y-hy]),([x-hx,y+hy],[x+hx,y+hy]),([x-hx,y-hy],[x-hx,y+hy]),([x+hx,y-hy],[x+hx,y+hy])]):
            line(name+str(i),a,b,.025,'#f4f1da')
    def circle(name,x,y,radius,width):
        if radius==width:
            ET.SubElement(world,'geom',name='visual_soccer_'+name,type='cylinder',pos=f'{x} {y} .0011',size=f'{radius} .0002',rgba=color('#f4f1da'),contype='0',conaffinity='0',group='2',mass='0')
        else:
            r=radius-width/2
            for i in range(80):
                a=i*math.tau/80;b=(i+1)*math.tau/80
                line(name+str(i),[x+r*math.cos(a),y+r*math.sin(a)],[x+r*math.cos(b),y+r*math.sin(b)],width,'#f4f1da',.0011)
    for i in range(12):box('grass_'+str(i),[-3.025+i*.55,0,.00015],[.55,4.4,.0002],'#6f9564' if i%2 else '#789f6c')
    outline('touchline',0,0,2.85,1.95)
    line('halfway',[0,-1.95],[0,1.95],.027,'#f4f1da')
    circle('centre_circle',0,0,.52,.025);circle('centre_spot',0,0,.034,.034)
    for side in (-1,1):
        outline('penalty_area'+str(side),side*2.45,0,.4,1.02)
        outline('goal_area'+str(side),side*2.685,0,.165,.76)
        circle('penalty_spot'+str(side),side*2.18,0,.025,.025)
        box('goal_end'+str(side),[side*3.04,0,.00035],[.35,1.27,.0002],'#8caeb4' if side<0 else '#c99b79')
    for geom in list(world.findall('geom')):
        if not geom.get('name','').startswith('goal_') or float(geom.get('rgba','1 1 1 1').split()[-1])!=0:continue
        x,y,z=map(float,geom.get('pos').split());hx,hy,hz=map(float,geom.get('size').split());across= hx<hy;half=hy if across else hx
        def point(u,v):return [x,y+u,z+v] if across else [x+u,y,z+v]
        segments=[];cols=math.ceil(half*2/.075);rows=math.ceil(hz*2/.065)
        for i in range(cols+1):
            u=-half+2*half*i/cols;segments.append((point(u,-hz),point(u,hz)))
        for i in range(rows+1):
            v=-hz+2*hz*i/rows;segments.append((point(-half,v),point(half,v)))
        for i,(a,b) in enumerate(segments):
            ET.SubElement(world,'geom',name='visual_soccer_net_'+geom.get('name')+'_'+str(i),type='capsule',fromto=' '.join(map(str,a+b)),size='.0015',rgba=color('#eceddf').rsplit(' ',1)[0]+' .68',contype='0',conaffinity='0',group='2',mass='0')
