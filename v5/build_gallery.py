#!/usr/bin/env python3
"""Create reproducible status-blinded TEM candidate contact sheet.

Stratified sampling is model-dependent; the resulting labels are NOT a random
sample of all particles and MUST NOT be used as recall estimates.
"""
import argparse,math
from pathlib import Path
import pandas as pd,numpy as np,cv2
from PIL import Image,ImageDraw,ImageFont

STRATA=[('accepted_isolated',6),('accepted_resolved',6),
('review:resplit_from_dense_parent;verify_separation',6),('review:complex_aggregate',6),
('review:irregular_but_contrasting',6),('rejected',6)]

def create(image_path,candidates,outdir,seed=11129):
    d=pd.read_csv(candidates);im=cv2.imread(str(image_path),cv2.IMREAD_GRAYSCALE)
    if im is None:raise FileNotFoundError(image_path)
    rng=np.random.default_rng(seed);items=[]
    for kind,count in STRATA:
        sub=d[(d.status=='review')&(d.reason==kind.split(':',1)[1])] if kind.startswith('review:') else d[d.status==kind]
        for ix in rng.choice(sub.index,min(count,len(sub)),replace=False):
            r=sub.loc[ix].to_dict();r['source_stratum']=kind;items.append(r)
    items=sorted(items,key=lambda x:(x['source_stratum'],int(x['id'])))
    path=Path(outdir);path.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(items).assign(audit_id=list(range(1,len(items)+1))).to_csv(path/'spotcheck_candidates.csv',index=False)
    try:font=ImageFont.truetype('DejaVuSans.ttf',17)
    except OSError:font=ImageFont.load_default()
    col=6;side=138;rows=math.ceil(len(items)/col)
    blind=Image.new('RGB',(col*side,rows*side),'#eeeeee');status=blind.copy()
    for j,r in enumerate(items):
        cx=int(round(r['x_px']));cy=int(round(r['y_px']));pad=19
        crop=np.pad(im,pad,mode='reflect')[cy:cy+2*pad+1,cx:cx+2*pad+1]
        chip=Image.fromarray(crop).resize((120,120),Image.Resampling.NEAREST).convert('RGB')
        x=(j%col)*side+9;y=(j//col)*side+12
        for surface in (blind,status):
            surface.paste(chip,(x,y));p=ImageDraw.Draw(surface)
            p.text((x+5,y-11),f'{j+1:02d}',fill='#111',font=font,stroke_width=1,stroke_fill='white')
            p.line(((x+57,y+60),(x+63,y+60)),fill='#ffcc40',width=1)
            p.line(((x+60,y+57),(x+60,y+63)),fill='#ffcc40',width=1)
        p=ImageDraw.Draw(status)
        color={'accepted_isolated':'#00cc33','accepted_resolved':'#9747f5','rejected':'#dd3333'}.get(r['status'],'#d98a00')
        p.rectangle((x,y,x+120,y+120),outline=color,width=3)
    blind.save(path/'spotcheck_blind.jpg',quality=88)
    status.save(path/'spotcheck_status.jpg',quality=88)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--image',required=True);p.add_argument('--candidates',required=True);p.add_argument('--out',required=True);p.add_argument('--seed',type=int,default=11129)
    a=p.parse_args();create(a.image,a.candidates,a.out,a.seed)