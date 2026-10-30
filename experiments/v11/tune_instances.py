#!/usr/bin/env python3
"""Tune instance split parameters ONLY on unused official train images.

The official EMPS test set remains strictly held out. Evaluate both frozen
v10 and validation-tuned watershed on exactly the same test subset.
"""
from __future__ import annotations
import argparse,json,sys,math
from pathlib import Path
import cv2,numpy as np
from scipy import ndimage as ndi
from skimage import measure
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'experiments/v10'))
from benchmark_emps import (read_pairs,prepare_image,prepare_instances,fit_model,predict,
     match_instances,pixel_score,watersplit,contours,RNG)

PARAMS=[(th,sep) for th in (.40,.48,.52,.60) for sep in (3,5,7,9,12)]

def mask_at(prob,thr):
    a=prob>=thr
    return ndi.binary_fill_holes(ndi.binary_opening(a,iterations=1))

def f1(tp,fp,fn):
    return 2*tp/max(1,2*tp+fp+fn)

def score(inst,gt):
    return match_instances(inst,gt)

def fit_valid(root,model,train,used,max_val=6,seed=RNG):
    remaining=[x for x in train if x[0] not in set(used)]
    if len(remaining)<3:raise ValueError('No held-out training validation subset')
    rng=np.random.default_rng(seed+113)
    selected=[remaining[int(i)] for i in rng.choice(len(remaining),min(max_val,len(remaining)),replace=False)]
    val=[]
    for stem,p,q in selected:
        im,_=prepare_image(p);gt=prepare_instances(q,im.shape)
        _,prob=predict(model,im,thr=.52)
        val.append((stem,prob,gt))
    scores=[]
    for th,sep in PARAMS:
        tp=fp=fn=0
        for name,prob,gt in val:
            m=mask_at(prob,th);inst=watersplit(m,typical_distance=sep)
            s=score(inst,gt);tp+=s['tp'];fp+=s['fp'];fn+=s['fn']
        scores.append({'threshold':th,'min_center_distance':sep,'validation_tp':tp,'validation_fp':fp,
                       'validation_fn':fn,'validation_instance_f1':f1(tp,fp,fn)})
    # fixed-order deterministic selection. Never inspect test labels to pick params.
    selected=max(scores,key=lambda x:(x['validation_instance_f1'],-abs(x['threshold']-.52),-abs(x['min_center_distance']-9)))
    return selected,scores,[x[0] for x in val]

def graph(img,gt,baseline,new,output,title):
    fig,axes=plt.subplots(1,4,figsize=(15,4))
    axes[0].imshow(img,cmap='gray');axes[0].set_title('Real TEM/SEM')
    axes[1].imshow(img,cmap='gray');contours(axes[1],gt,'#ffdd33',instances=True);axes[1].set_title('Expert instance GT')
    for ax,m,label in zip(axes[2:],[baseline,new],['v10 fixed watershed','v11 train-val tuned']):
        ax.imshow(img,cmap='gray');contours(ax,gt,'#ffdd33',instances=True)
        contours(ax,m,'#25dfff',instances=True);ax.set_title(label+' (cyan vs GT yellow)')
    for a in axes:a.axis('off')
    fig.suptitle(title,fontsize=10);fig.tight_layout();fig.savefig(output,dpi=125);plt.close(fig)

def run(root,out,train_n=28,valid_n=6,test_n=8):
    root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    tr=read_pairs(root,'train');te=read_pairs(root,'test')
    if {x[0] for x in tr}&{x[0] for x in te}:raise ValueError('train/test identity overlap')
    model,used=fit_model(root,tr,train_n)
    best,grid,valid_names=fit_valid(root,model,tr,used,valid_n)
    rng=np.random.default_rng(RNG)
    selected=rng.choice(len(te),min(test_n,len(te)),replace=False)
    rows=[]
    for n,i in enumerate(selected):
        stem,p,q=te[int(i)]
        img,_=prepare_image(p);gt=prepare_instances(q,img.shape)
        baseline,prob=predict(model,img,thr=.52)
        pred_old=watersplit(baseline,typical_distance=9)
        pred_new=watersplit(mask_at(prob,best['threshold']),typical_distance=best['min_center_distance'])
        row={'id':stem,'gt_instance_n':int(len(np.unique(gt[gt>0]))),
             'v10':score(pred_old,gt),'v11':score(pred_new,gt),
             'pixel_old':pixel_score(baseline,gt),'pixel_new':pixel_score(mask_at(prob,best['threshold']),gt)}
        rows.append(row)
        if n<6:graph(img,gt,pred_old,pred_new,out/f'{stem}.jpg',f'Instance review {stem}')
        print(stem,'v10 TP',row['v10']['tp'],'v11 TP',row['v11']['tp'],flush=True)
    def summarize(key):
        tp=sum(r[key]['tp'] for r in rows);fp=sum(r[key]['fp'] for r in rows);fn=sum(r[key]['fn'] for r in rows)
        return {'tp':tp,'fp':fp,'fn':fn,'micro_precision':tp/max(1,tp+fp),
                'micro_recall':tp/max(1,tp+fn),'micro_f1':f1(tp,fp,fn),
                'macro_precision':float(np.mean([r[key]['precision'] for r in rows])),
                'macro_recall':float(np.mean([r[key]['recall'] for r in rows]))}
    result={'dataset':'EMPS; official train/test', 'train_used':used,'validation_used':valid_names,
      'validation_best':best,'validation_grid':grid,'test_ids':[r['id'] for r in rows],
      'threshold_tuned_using_test_masks':False,
      'baseline':summarize('v10'),'tuned':summarize('v11'),'per_image':rows}
    (out/'metrics.json').write_text(json.dumps(result,indent=2))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset-root',required=True)
    p.add_argument('--out',default='experiments/v11/results');p.add_argument('--train-n',type=int,default=28)
    p.add_argument('--val-n',type=int,default=6);p.add_argument('--test-n',type=int,default=8)
    a=p.parse_args();r=run(a.dataset_root,a.out,a.train_n,a.val_n,a.test_n)
    print(json.dumps({k:r[k] for k in ('validation_best','baseline','tuned')},indent=2))
