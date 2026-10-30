#!/usr/bin/env python3
"""Polarity-symmetric supervised segmentation vs frozen v13, evaluated on NEW EMPS test IDs.

No test annotation is used for fitting, postprocessing choices, or image selection.
Official TEM/SEM mixture: scores do not establish performance on DM3 HRTEM.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, sys
from pathlib import Path
import numpy as np
from scipy import ndimage as ndi
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT/'v10',ROOT/'v11',ROOT/'v13'):
    sys.path.insert(0,str(path))
from benchmark_emps import (RNG,read_pairs,prepare_image,prepare_instances,fit_model,
                            predict, features, match_instances, contours)
from tune_instances import mask_at
from boundary_model import (boundary_targets, train_boundary,border_prob,split_by_border,metrics_sum)

# Frozen v13 parameters: values selected on official TRAIN validation, never adjusted here.
CORE_THRESHOLD=.52
BORDER_THRESHOLD=.35
MIN_SEED_AREA=45
EROSION=1
PREVIOUS_TEST={"f28b702df5","8136144eaf","c61a50a061","8bf3782470",
               "5f42a8d4a9","bcab6454cf","99eb4bad25","a8e3f32537"}
SEED=20261114


def fresh_test_ids(test, count=20, seed=SEED):
    remaining=[row for row in test if row[0] not in PREVIOUS_TEST]
    if count>len(remaining):
        raise ValueError(f'Requested {count} previously unused samples, only {len(remaining)} available')
    chosen=np.random.default_rng(seed).choice(len(remaining),count,replace=False)
    rows=[remaining[int(i)] for i in chosen]
    assert not ({r[0] for r in rows} & PREVIOUS_TEST)
    return sorted(rows,key=lambda x:x[0])


def augment_training(train, used, seed=RNG, samples_per_class=650):
    """Train paired bright/dark equivalent classifiers; weights are test-blind.

    Each input and its complement have the SAME instance label, reversing all
    brightness-derived image features while preserving geometry.
    """
    chosen=set(used);rng=np.random.default_rng(seed+140)
    semantic_x=[];semantic_y=[];border_x=[];border_y=[]
    seen=[]
    for stem,image_path,mask_path in train:
        if stem not in chosen:continue
        img,_=prepare_image(image_path)
        gt=prepare_instances(mask_path,img.shape)
        truth=gt>0
        target=boundary_targets(gt)
        foreground=np.flatnonzero(truth.ravel());background=np.flatnonzero(~truth.ravel())
        if min(len(foreground),len(background))<20:continue
        a=np.r_[rng.choice(foreground,min(samples_per_class,len(foreground)),replace=False),
                rng.choice(background,min(samples_per_class,len(background)),replace=False)]
        b=[]
        for c in (0,1,2):
            candidates=np.flatnonzero(target.ravel()==c)
            if len(candidates):b.append(rng.choice(candidates,min(samples_per_class,len(candidates)),replace=False))
        if len(b)!=3:continue
        b=np.concatenate(b)
        for x in (img,1-img):
            xf=features(x).reshape(-1,14)
            semantic_x.append(xf[a]);semantic_y.append(truth.ravel()[a])
            border_x.append(xf[b]);border_y.append(target.ravel()[b])
        seen.append(stem)
    if len(seen)<10:raise ValueError('Insufficient paired augmentation training samples')
    semantic=RandomForestClassifier(n_estimators=44,max_depth=18,min_samples_leaf=3,
                                    n_jobs=1,class_weight='balanced_subsample',random_state=seed+140)
    boundary=ExtraTreesClassifier(n_estimators=44,max_depth=19,min_samples_leaf=2,
                                  n_jobs=1,class_weight='balanced_subsample',random_state=seed+141)
    semantic.fit(np.concatenate(semantic_x),np.concatenate(semantic_y))
    boundary.fit(np.concatenate(border_x),np.concatenate(border_y))
    return semantic,boundary,seen


def polarity_probabilities(semantic,boundary,img):
    """Explicit symmetric 2-pass ensemble; mathematically P(img)==P(1-img)."""
    ps=[];bs=[]
    for view in (img,1-img):
        x=features(view).reshape(-1,14)
        p=semantic.predict_proba(x)[:,list(semantic.classes_).index(True)].reshape(img.shape)
        b=boundary.predict_proba(x)[:,list(boundary.classes_).index(2)].reshape(img.shape)
        ps.append(p);bs.append(b)
    return (np.mean(ps,axis=0).astype('float32'),np.mean(bs,axis=0).astype('float32'))


def predict_v13(semantic,boundary,img):
    _,core=predict(semantic,img,thr=CORE_THRESHOLD)
    border=border_prob(boundary,img)
    return split_by_border(mask_at(core,CORE_THRESHOLD),border,BORDER_THRESHOLD,MIN_SEED_AREA,EROSION)


def predict_v14(semantic,boundary,img):
    core,border=polarity_probabilities(semantic,boundary,img)
    return split_by_border(mask_at(core,CORE_THRESHOLD),border,BORDER_THRESHOLD,MIN_SEED_AREA,EROSION)


def foreground_polarity(im,labels):
    """For REPORTING ONLY: ground-truth-defined foreground contrast, not model selection."""
    fg=im[labels>0];bg=im[labels==0]
    if len(fg)<20 or len(bg)<20:return 'uncertain'
    delta=float(np.median(fg)-np.median(bg))
    if delta>.025:return 'bright'
    if delta<-.025:return 'dark'
    return 'low_contrast'


def preview(im,gt,old,new,path,title):
    fig,ax=plt.subplots(1,4,figsize=(16,4.5))
    for a in ax:a.imshow(im,cmap='gray',vmin=0,vmax=1);a.axis('off')
    ax[0].set_title('EMPS measured image')
    contours(ax[1],gt,'#ffe731',instances=True);ax[1].set_title('Human instances (yellow)')
    for axis,pred,label in [(ax[2],old,'v13 frozen'),(ax[3],new,'v14 polarity-symmetric')]:
        contours(axis,gt,'#ffe731',instances=True)
        contours(axis,pred,'#00e5fb',instances=True)
        axis.set_title(label+' / cyan vs GT yellow')
    fig.suptitle(title,fontsize=11);fig.tight_layout()
    fig.savefig(path,dpi=110);plt.close(fig)


def summarize(rows, key):
    m=metrics_sum([r[key] for r in rows])
    diam=[r[key]['diameter_mae_px'] for r in rows if r[key]['diameter_mae_px'] is not None]
    m['mean_matched_diameter_mae_px']=float(np.mean(diam)) if diam else None
    return m


def run(root,out,n=20):
    root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    tr=read_pairs(root,'train');te=read_pairs(root,'test')
    if {x[0] for x in tr}&{x[0] for x in te}:raise ValueError('Official train/test stem overlap')
    chosen=fresh_test_ids(te,count=n)
    old_sem,train_used=fit_model(root,tr,28)
    old_bd,old_bd_used=train_boundary(tr,train_used)
    new_sem,new_bd,new_used=augment_training(tr,train_used)
    if set(new_used)!=set(train_used):raise ValueError('Augmented and baseline training image lists differ')
    rows=[]
    for stem,p,m in chosen:
        im,_=prepare_image(p);gt=prepare_instances(m,im.shape)
        old=predict_v13(old_sem,old_bd,im)
        new=predict_v14(new_sem,new_bd,im)
        row={'id':stem,'gt_count':int(np.unique(gt[gt>0]).size),
             'polarity_for_reporting_only':foreground_polarity(im,gt),
             'v13':match_instances(old,gt),'v14':match_instances(new,gt)}
        rows.append(row)
        if len(rows)<=8:preview(im,gt,old,new,out/f'{stem}.jpg',stem)
        print(f'{stem} polarity={row["polarity_for_reporting_only"]}: v13 {row["v13"]["tp"]} v14 {row["v14"]["tp"]}',flush=True)
    groups={group:{k:summarize([r for r in rows if r['polarity_for_reporting_only']==group],k)
                   for k in ('v13','v14')} for group in ('bright','dark','low_contrast','uncertain')
            if any(r['polarity_for_reporting_only']==group for r in rows)}
    old=summarize(rows,'v13');new=summarize(rows,'v14')
    result={'dataset':'EMPS pinned official train/test, test selected from previously unseen IDs',
            'seed':SEED,'previously_used_test_ids':sorted(PREVIOUS_TEST),'new_test_ids':[r['id'] for r in rows],
            'train_images':train_used, 'training_only_augmentation':True,
            'train_or_validation_used_new_test_labels':False,
            'v13_frozen_params':{'core_threshold':CORE_THRESHOLD,'border_threshold':BORDER_THRESHOLD,
                                 'min_seed_area':MIN_SEED_AREA,'erosion':EROSION},
            'v13':old,'v14':new,'by_polarity':groups,'per_image':rows,
            'go_if_v14_f1_greater_or_equal':new['micro_f1']>=old['micro_f1'],
            'limitations':'Prior 8 test images used during historical model iteration; 20 new test IDs from SAME EMPS dataset; not external DM3 or independent acquisition site.'}
    (out/'metrics.json').write_text(json.dumps(result,indent=2))
    with (out/'per_image.csv').open('w',newline='') as file:
        w=csv.writer(file);w.writerow(['id','polarity','gt_n','v13_tp','v13_fp','v13_fn','v14_tp','v14_fp','v14_fn','v13_diameter_mae_px','v14_diameter_mae_px'])
        for r in rows:
            w.writerow([r['id'],r['polarity_for_reporting_only'],r['gt_count'],
                        *[r[k][m] for k in ('v13','v14') for m in ('tp','fp','fn')],
                        r['v13']['diameter_mae_px'],r['v14']['diameter_mae_px']])
    print(json.dumps({'v13':old,'v14':new,'go':result['go_if_v14_f1_greater_or_equal']},indent=2),flush=True)
    return result

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--dataset-root',required=True);a.add_argument('--out',required=True);a.add_argument('--count',type=int,default=20)
    q=a.parse_args();run(q.dataset_root,q.out,q.count)
