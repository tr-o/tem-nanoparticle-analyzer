#!/usr/bin/env python3
"""Object-center diagnostic on held-out *synthetic* labels.
Not real-microscopy model validation and not an instance-mask metric.
"""
from pathlib import Path
import csv,json,sys
import numpy as np
from scipy.optimize import linear_sum_assignment
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'experiments/v4'));sys.path.insert(0,str(ROOT/'experiments/v2'))
from tem_v4 import run as run_v4
from tem_v2 import run as run_v3,MODEL

def score(gt, pred):
    centers=np.asarray([[x[0],x[1]] for x in gt],float)
    radii=np.asarray([x[2] for x in gt],float)
    pts=np.asarray([[float(x['y_px']),float(x['x_px'])] for x in pred],float)
    if not len(pts):return dict(tp=0,fp=0,fn=len(gt),precision=0.,recall=0.)
    dist=np.linalg.norm(centers[:,None,:]-pts[None,:,:],axis=2)
    cost=np.where(dist<=np.maximum(4.5,radii[:,None]*.75),dist,1e4)
    r,c=linear_sum_assignment(cost)
    tp=int((cost[r,c]<1e4).sum());fp=len(pts)-tp;fn=len(gt)-tp
    return dict(tp=tp,fp=fp,fn=fn,precision=tp/len(pts),recall=tp/len(gt))

def rows(path):
    with Path(path).open() as f:return list(csv.DictReader(f))

if __name__=='__main__':
    result=[]
    for idx in range(4):
        name=f'test_{idx:02d}';img=ROOT/'demo_data/test/images'/f'{name}.png'
        gt=json.loads((ROOT/'demo_data/test/instances'/f'{name}.json').read_text())
        v3out=ROOT/'experiments/v4/benchmarks'/name/'v3';v4out=ROOT/'experiments/v4/benchmarks'/name/'v4'
        run_v3(str(img),model_path=str(MODEL),outdir=str(v3out),auto_scale=False)
        run_v4(str(img),str(v4out),model_path=str(MODEL))
        v3pred=rows(v3out/'particles_accepted.csv');v4pred=rows(v4out/'particles_accepted.csv')
        result.append(dict(image=name,n_gt=len(gt),v3=score(gt,v3pred),v4=score(gt,v4pred)))
    summary={k:{key:sum(row[k][key] for row in result) for key in ['tp','fp','fn']} for k in ['v3','v4']}
    for stats in summary.values():
        stats['precision']=stats['tp']/(stats['tp']+stats['fp']) if stats['tp']+stats['fp'] else 0
        stats['recall']=stats['tp']/(stats['tp']+stats['fn']) if stats['tp']+stats['fn'] else 0
    data=dict(method='Hungarian center matching ≤ max(4.5px,0.75 × synthetic radius); synthetic ground truth only',results=result,aggregated=summary)
    (ROOT/'experiments/v4/synthetic_center_benchmark.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
