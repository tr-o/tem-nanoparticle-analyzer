#!/usr/bin/env python3
"""EMPS boundary-supervised separator. No official test labels for tuning.

A second per-pixel classifier predicts BG / particle-core / particle-border
from manually assigned instance IDs in official TRAIN only. Predicted borders
are candidate ridges, not expert labels on test. Baseline v11 remains frozen.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import cv2
import numpy as np
from scipy import ndimage as ndi
from skimage import measure, segmentation, morphology
from sklearn.ensemble import ExtraTreesClassifier
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'v10'));sys.path.insert(0,str(ROOT/'v11'))
from benchmark_emps import (read_pairs,prepare_image,prepare_instances,fit_model,predict,features,
                             match_instances,contours,watersplit,RNG)
from tune_instances import fit_valid,mask_at,f1


def boundary_targets(labels):
    """0 background, 1 core, 2 boundary; retain real instance interfaces."""
    lab=np.asarray(labels,dtype=np.int32)
    if lab.ndim!=2:raise ValueError('Expect 2D instance IDs')
    nonzero=lab>0
    boundary=nonzero & (ndi.maximum_filter(lab,size=3)!=ndi.minimum_filter(lab,size=3))
    y=np.zeros(lab.shape,np.uint8);y[nonzero]=1;y[boundary]=2
    return y


def train_boundary(train,used,seed=RNG,per_class=750):
    rng=np.random.default_rng(seed+101)
    xs=[];ys=[];seen=[]
    used=set(used)
    for stem,img_path,mask_path in train:
        if stem not in used:continue
        im,_=prepare_image(img_path)
        labels=prepare_instances(mask_path,im.shape)
        target=boundary_targets(labels).ravel()
        f=features(im).reshape(-1,14)
        sel=[]
        for cl in (0,1,2):
            loc=np.flatnonzero(target==cl)
            if len(loc):sel.append(rng.choice(loc,min(per_class,len(loc)),replace=False))
        if len(sel)!=3:continue
        sel=np.concatenate(sel);xs.append(f[sel]);ys.append(target[sel]);seen.append(stem)
    if len(seen)<4:raise ValueError('Not enough training images for border classifier')
    clf=ExtraTreesClassifier(n_estimators=44,max_depth=19,min_samples_leaf=2,
                             n_jobs=1,class_weight='balanced_subsample',random_state=seed+101)
    clf.fit(np.concatenate(xs),np.concatenate(ys))
    return clf,seen


def border_prob(model,img):
    f=features(img);p=model.predict_proba(f.reshape(-1,14))
    i=list(model.classes_).index(2)
    return p[:,i].reshape(img.shape).astype(np.float32)


def split_by_border(mask,border,threshold=.40,min_seed_area=16,post_erode=0):
    mask=np.asarray(mask,bool);border=np.asarray(border,np.float32)
    if mask.shape!=border.shape:raise ValueError('Boundary and mask geometry mismatch')
    if not mask.any():return np.zeros(mask.shape,np.int32)
    interior=mask & (border<threshold)
    if post_erode:interior=ndi.binary_erosion(interior,iterations=post_erode)
    seeds=measure.label(interior).astype(np.int32)
    keep=np.zeros(mask.shape,np.int32);i=0
    for reg in measure.regionprops(seeds):
        if reg.area < min_seed_area:continue
        i+=1;keep[seeds==reg.label]=i
    if i==0:return np.zeros(mask.shape,np.int32)
    # True border probability supplies energy ridges; EDT resolves ambiguous interiors.
    edt=ndi.distance_transform_edt(mask).astype(np.float32)
    elevation=2.0*border-0.07*edt/(max(float(edt.max()),1))
    return segmentation.watershed(elevation,keep,mask=mask).astype(np.int32)


def metrics_sum(scores):
    tp=sum(x['tp'] for x in scores);fp=sum(x['fp'] for x in scores);fn=sum(x['fn'] for x in scores)
    return dict(tp=int(tp),fp=int(fp),fn=int(fn),micro_f1=f1(tp,fp,fn),
                micro_precision=tp/max(tp+fp,1),micro_recall=tp/max(tp+fn,1),
                macro_precision=float(np.mean([x['precision'] for x in scores])),
                macro_recall=float(np.mean([x['recall'] for x in scores])))


def preview(img,gt,base,pred,bprob,path,stem):
    fig,ax=plt.subplots(1,5,figsize=(17,4))
    ax[0].imshow(img,cmap='gray');ax[0].set_title('Measured EM image')
    ax[1].imshow(img,cmap='gray');contours(ax[1],gt,'#ffee22',instances=True);ax[1].set_title('Human instance GT')
    for subplot,seg,label in [(ax[2],base,'v11 DT watershed'),(ax[3],pred,'v13 learned boundaries')]:
        subplot.imshow(img,cmap='gray');contours(subplot,gt,'#ffee22',instances=True)
        contours(subplot,seg,'#00eaff',instances=True);subplot.set_title(label+' (cyan / yellow GT)')
    ax[4].imshow(bprob,cmap='magma',vmin=0,vmax=1);ax[4].set_title('Learned border probability')
    for a in ax:a.axis('off')
    fig.suptitle(stem);fig.tight_layout();fig.savefig(path,dpi=120);plt.close(fig)


def run(root,out,train_n=28,valid_n=6,test_n=8):
    root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    train=read_pairs(root,'train');test=read_pairs(root,'test')
    if {x[0] for x in train}&{x[0] for x in test}:raise ValueError('Train/test overlap')
    semantic,used=fit_model(root,train,train_n)
    border,bd_train=train_boundary(train,used)
    best_baseline,_,validation=fit_valid(root,semantic,train,used,valid_n)
    validation_set=[x for x in train if x[0] in set(validation)]
    cached=[]
    for stem,p,q in validation_set:
        im,_=prepare_image(p);gt=prepare_instances(q,im.shape)
        _,prob=predict(semantic,im);bd=border_prob(border,im)
        cached.append((stem,gt,prob,bd))
    grid=[]
    for threshold in (.20,.35,.50,.65):
        for area in (12,24,45):
            for erosion in (0,1):
                scores=[]
                for stem,gt,prob,bd in cached:
                    mask=mask_at(prob,best_baseline['threshold'])
                    pred=split_by_border(mask,bd,threshold,area,erosion)
                    scores.append(match_instances(pred,gt))
                summary=metrics_sum(scores)
                grid.append(dict(threshold=threshold,min_seed_area=area,erosion=erosion,
                                 val_f1=summary['micro_f1'],val_tp=summary['tp'],
                                 val_fp=summary['fp'],val_fn=summary['fn']))
    chosen=max(grid,key=lambda x:(x['val_f1'],-x['erosion'],-abs(x['threshold']-.35)))
    rng=np.random.default_rng(RNG)
    chosen_test=rng.choice(len(test),size=min(test_n,len(test)),replace=False)
    rows=[]
    for index in chosen_test:
        stem,p,q=test[int(index)]
        img,_=prepare_image(p);gt=prepare_instances(q,img.shape)
        _,prob=predict(semantic,img);bd=border_prob(border,img)
        baseline_mask=mask_at(prob,best_baseline['threshold'])
        old=watersplit(baseline_mask,typical_distance=best_baseline['min_center_distance'])
        new=split_by_border(baseline_mask,bd,chosen['threshold'],chosen['min_seed_area'],chosen['erosion'])
        scores={'id':stem,'gt_count':int(len(np.unique(gt[gt>0]))),'v11':match_instances(old,gt),
                'v13':match_instances(new,gt)}
        rows.append(scores)
        if len(rows)<=6:preview(img,gt,old,new,bd,out/f'{stem}.jpg',stem)
        print(stem,'v11 TP',scores['v11']['tp'],'v13 TP',scores['v13']['tp'],flush=True)
    res={'source':'EMPS pinned official train/test', 'train_used':used,'boundary_train_used':bd_train,
         'validation_used':validation,'test_ids':[r['id'] for r in rows],
         'test_not_used_for_tuning':True,'baseline_validation':best_baseline,
         'border_validation_best':chosen,'border_grid':grid,
         'v11':metrics_sum([r['v11'] for r in rows]),
         'v13':metrics_sum([r['v13'] for r in rows]),'per_image':rows}
    (out/'metrics.json').write_text(json.dumps(res,indent=2))
    print(json.dumps({k:res[k] for k in ('border_validation_best','v11','v13')},indent=2),flush=True)
    return res

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset-root',required=True);p.add_argument('--out',required=True)
    args=p.parse_args();run(args.dataset_root,args.out)
