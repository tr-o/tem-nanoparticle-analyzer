#!/usr/bin/env python3
"""Supervised particle-center seeds from true instance IDs; test set remains blind.

Separate mask-RF and center-RF, with validation-only selection of center
threshold and spacing. This is experimental and must beat v11 on held-out GT.
"""
from __future__ import annotations
import argparse,json,sys,math
from pathlib import Path
import numpy as np,cv2
from scipy import ndimage as ndi
from skimage import feature,segmentation,measure
from sklearn.ensemble import RandomForestClassifier
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'v10'))
sys.path.insert(0,str(ROOT/'v11'))
from benchmark_emps import (read_pairs,prepare_image,prepare_instances,fit_model,predict,features,
                           match_instances,pixel_score,contours,RNG)
from tune_instances import mask_at,f1,watersplit

CENTER_GRID=[(thr,d) for thr in (.20,.35,.50,.65) for d in (4,6,9,12)]

def centroid_pixels(ids,radius=2):
    out=np.zeros(ids.shape,bool)
    for obj in measure.regionprops(ids):
        if obj.area<12:continue
        cy,cx=obj.centroid
        coords=obj.coords
        ix=np.argmin((coords[:,0]-cy)**2+(coords[:,1]-cx)**2)
        y,x=coords[ix]
        for dy in range(-radius,radius+1):
            for dx in range(-radius,radius+1):
                yy=y+dy;xx=x+dx
                if 0<=yy<ids.shape[0] and 0<=xx<ids.shape[1] and (dx*dx+dy*dy)<=radius*radius and ids[yy,xx]==obj.label:
                    out[yy,xx]=True
    return out

def train_center(train_items,used,pix_per_type=850):
    m={x[0]:x for x in train_items};rng=np.random.default_rng(RNG+8)
    xs=[];ys=[];centers_count=0
    for stem in used:
        _,path,gtpath=m[stem]
        img,_=prepare_image(path);gt=prepare_instances(gtpath,img.shape)
        y=centroid_pixels(gt)
        p=np.flatnonzero(y);neg_obj=np.flatnonzero((gt>0)&~y);neg_bg=np.flatnonzero(gt==0)
        if min(len(p),len(neg_obj),len(neg_bg))==0:continue
        a=rng.choice(p,size=min(pix_per_type,len(p)),replace=False)
        b=rng.choice(neg_obj,size=min(pix_per_type,len(neg_obj)),replace=False)
        c=rng.choice(neg_bg,size=min(pix_per_type,len(neg_bg)),replace=False)
        ii=np.r_[a,b,c]
        f=features(img).reshape(-1,14)
        xs.append(f[ii]);ys.append(y.ravel()[ii]);centers_count+=len(np.unique(gt[gt>0]))
    if len(xs)<4:raise ValueError('Insufficient training for center detection')
    model=RandomForestClassifier(n_estimators=46,max_depth=18,min_samples_leaf=2,n_jobs=1,
                                 class_weight='balanced_subsample',random_state=RNG+12)
    model.fit(np.concatenate(xs),np.concatenate(ys))
    return model,centers_count

def center_probability(model,img):
    f=features(img)
    return model.predict_proba(f.reshape(-1,f.shape[-1]))[:,list(model.classes_).index(True)].reshape(img.shape)

def seeded_watershed(mask,center_prob,threshold,spacing):
    if not mask.any():return np.zeros(mask.shape,np.int32)
    smooth=ndi.gaussian_filter(center_prob,1.2)
    pts=feature.peak_local_max(smooth,min_distance=spacing,threshold_abs=threshold,
                                labels=mask.astype('uint8'),exclude_border=False)
    seeds=np.zeros(mask.shape,np.int32)
    for i,(y,x) in enumerate(pts,1):seeds[y,x]=i
    if len(pts)==0:return np.zeros(mask.shape,np.int32)
    dt=ndi.distance_transform_edt(mask)
    return segmentation.watershed(-dt,seeds,mask=mask).astype(np.int32)

def tune_center(model,maskmodel,train_items,used,count=6):
    remaining=[x for x in train_items if x[0] not in set(used)]
    if len(remaining)<count:raise ValueError('Not enough unused train images for validation')
    rng=np.random.default_rng(RNG+113)
    chosen=[remaining[int(i)] for i in rng.choice(len(remaining),count,replace=False)]
    cache=[]
    for stem,p,q in chosen:
        x,_=prepare_image(p);gt=prepare_instances(q,x.shape)
        mask,_=predict(maskmodel,x,.52)
        prob=center_probability(model,x)
        cache.append((stem,mask,prob,gt))
    results=[]
    for th,spacing in CENTER_GRID:
        tp=fp=fn=0
        for stem,mask,prob,gt in cache:
            inst=seeded_watershed(mask,prob,th,spacing)
            score=match_instances(inst,gt)
            tp+=score['tp'];fp+=score['fp'];fn+=score['fn']
        results.append(dict(center_threshold=th,min_center_distance=spacing,
                            val_tp=tp,val_fp=fp,val_fn=fn,val_f1=f1(tp,fp,fn)))
    best=max(results,key=lambda r:(r['val_f1'],-abs(r['center_threshold']-.35),-abs(r['min_center_distance']-6)))
    return best,results,[x[0] for x in cache]

def draw(img,gt,mask,w11,w12,prob,out,id):
    fig,axes=plt.subplots(1,5,figsize=(18.5,4.2))
    axes[0].imshow(img,cmap='gray');axes[0].set_title('Real TEM/SEM')
    axes[1].imshow(img,cmap='gray');contours(axes[1],gt,'#ffdf3a',instances=True);axes[1].set_title('Expert instance GT')
    for a,inst,t in zip(axes[2:4],[w11,w12],['v11 EDT seeds','v12 supervised centers']):
        a.imshow(img,cmap='gray');contours(a,gt,'#ffdf3a',instances=True)
        contours(a,inst,'#12e5ff',instances=True);a.set_title(t)
    axes[4].imshow(prob,cmap='magma',vmin=0,vmax=1);axes[4].set_title('Center probability')
    for a in axes:a.axis('off')
    fig.suptitle(f'{id}: yellow=GT, cyan=prediction');fig.tight_layout();fig.savefig(out,dpi=120);plt.close(fig)

def summarize(rows,key):
    tp=sum(r[key]['tp'] for r in rows);fp=sum(r[key]['fp'] for r in rows);fn=sum(r[key]['fn'] for r in rows)
    return dict(tp=tp,fp=fp,fn=fn,micro_f1=f1(tp,fp,fn),
        micro_precision=tp/(tp+fp) if tp+fp else 0.,micro_recall=tp/(tp+fn) if tp+fn else 0.,
        macro_recall=float(np.mean([r[key]['recall'] for r in rows])))

def evaluate(dataset,out,train_n=28,val_n=6,test_n=8):
    dataset=Path(dataset);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    train=read_pairs(dataset,'train');test=read_pairs(dataset,'test')
    if set(x[0] for x in train)&set(x[0] for x in test):raise ValueError('train/test contamination')
    maskmodel,used=fit_model(dataset,train,train_n)
    center,centers=train_center(train,used)
    best,grid,valid=tune_center(center,maskmodel,train,used,val_n)
    # Frozen v11 reference settings; test never used to select these.
    old_threshold=.52;old_spacing=12
    rng=np.random.default_rng(RNG)
    rows=[]
    for seq,i in enumerate(rng.choice(len(test),min(test_n,len(test)),replace=False)):
        stem,p,q=test[int(i)]
        im,_=prepare_image(p);gt=prepare_instances(q,im.shape)
        mask,prob=predict(maskmodel,im,.52)
        old=watersplit(mask_at(prob,old_threshold),typical_distance=old_spacing)
        centermap=center_probability(center,im)
        new=seeded_watershed(mask,centermap,best['center_threshold'],best['min_center_distance'])
        row=dict(id=stem,GT_instances=len(np.unique(gt[gt>0])),v11=match_instances(old,gt),v12=match_instances(new,gt))
        rows.append(row)
        if seq<6:draw(im,gt,mask,old,new,centermap,out/f'{stem}.jpg',stem)
        print(stem, 'expert', row['GT_instances'],'v11',row['v11']['tp'],'v12',row['v12']['tp'],flush=True)
    result=dict(dataset='EMPS (Yildirim & Cole 2021)',train_ids=used,train_center_instance_n=centers,
        validation_ids=valid, validation_best=best,validation_grid=grid,
        test_ids=[x['id'] for x in rows],test_used_for_tuning=False,
        old=summarize(rows,'v11'),new=summarize(rows,'v12'),per_image=rows)
    (out/'metrics.json').write_text(json.dumps(result,indent=2))
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset-root',required=True)
    p.add_argument('--out',default='v12/results')
    a=p.parse_args();x=evaluate(a.dataset_root,a.out)
    print(json.dumps({k:x[k] for k in ('validation_best','old','new')},indent=2))
