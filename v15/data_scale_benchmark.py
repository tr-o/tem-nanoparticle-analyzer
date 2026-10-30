#!/usr/bin/env python3
"""v15: freeze v13 method, scale official TRAIN coverage 28 -> 96 images.

Evaluate once on fresh official test IDs excluding every v10-v14 test image.
All segmentation settings remain frozen from v13 train validation.
"""
from __future__ import annotations
import argparse,csv,json,sys
from pathlib import Path
import numpy as np
from skimage import measure
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
for p in ('v10','v11','v13','v14'):sys.path.insert(0,str(ROOT/p))
from benchmark_emps import (RNG,read_pairs,prepare_image,prepare_instances,fit_model,
                            predict,match_instances,contours)
from boundary_model import train_boundary,border_prob,split_by_border,metrics_sum,boundary_targets
from tune_instances import mask_at
from polarity_benchmark import (PREVIOUS_TEST,SEED as OLD_SEED,CORE_THRESHOLD,
                                BORDER_THRESHOLD,MIN_SEED_AREA,EROSION,foreground_polarity)

SEED=20261115

def unseen_test(test,seen,count=20):
    items=[r for r in test if r[0] not in set(seen)]
    if count>len(items):raise ValueError(f'Only {len(items)} unobserved test cases; cannot choose {count}')
    ix=np.random.default_rng(SEED).choice(len(items),size=count,replace=False)
    result=sorted((items[int(i)] for i in ix),key=lambda r:r[0])
    if set(r[0] for r in result)&set(seen):raise AssertionError('Test reuse')
    return result

def load_prior_test(root):
    path=root/'v14/results/metrics.json'
    if not path.exists():raise FileNotFoundError('Prior v14 test manifest required, refusing unverified reuse')
    past=json.loads(path.read_text())
    old=set(past['new_test_ids'])|set(PREVIOUS_TEST)
    if len(old)!=len(past['new_test_ids'])+len(PREVIOUS_TEST):
        raise ValueError('Historical test record overlaps unexpectedly')
    return old

def choose_superset_training(train, prior_stems, additional=68):
    """Deterministic superset of v13's 28 train images, never any official test.

    Screen ONLY official training GT so the 96-image condition truly counts
    valid core/border training examples rather than silently skipping blanks.
    """
    base={row[0] for row in train if row[0] in set(prior_stems)}
    if base!=set(prior_stems):raise ValueError('Missing v13 training images')
    extra=[row for row in train if row[0] not in base]
    rng=np.random.default_rng(SEED+35)
    selected=[]
    for j in rng.permutation(len(extra)):
        row=extra[int(j)]
        img,_=prepare_image(row[1]); gt=prepare_instances(row[2],img.shape)
        n_pos=np.count_nonzero(gt);n_bg=np.count_nonzero(gt==0)
        if min(n_pos,n_bg)<20:continue
        y=boundary_targets(gt)
        if set(np.unique(y))!={0,1,2}:continue
        selected.append(row)
        if len(selected)==additional:break
    if len(selected)!=additional:raise ValueError('Insufficient usable extra train images')
    return [row for row in train if row[0] in base]+selected


def predict_instances(sem,border,im):
    _,p=predict(sem,im,thr=CORE_THRESHOLD)
    bp=border_prob(border,im)
    return split_by_border(mask_at(p,CORE_THRESHOLD),bp,BORDER_THRESHOLD,MIN_SEED_AREA,EROSION)

def draw(img,gt,p28,p96,out,stem):
    fig,ax=plt.subplots(1,4,figsize=(16,4.4))
    for a in ax:a.imshow(img,cmap='gray',vmin=0,vmax=1);a.axis('off')
    ax[0].set_title('Measured EMPS')
    contours(ax[1],gt,'#ffe034',True);ax[1].set_title('Human instance GT')
    for a,p,name in ((ax[2],p28,'28 training images'),(ax[3],p96,'96 training images')):
        contours(a,gt,'#ffe034',True);contours(a,p,'#00e9ed',True);a.set_title(name+' / cyan vs GT yellow')
    fig.suptitle(stem);fig.tight_layout();fig.savefig(out,dpi=110);plt.close(fig)

def aggregate(rows,key):
    d=metrics_sum([r[key] for r in rows]);maes=[r[key]['diameter_mae_px'] for r in rows if r[key]['diameter_mae_px'] is not None]
    d['mean_matched_diameter_mae_px']=float(np.mean(maes)) if maes else None
    return d

def run(dataset,out,count=20):
    root=Path(ROOT);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    data=Path(dataset);train=read_pairs(data,'train');test=read_pairs(data,'test')
    seen=load_prior_test(root)
    if {r[0] for r in train}&{r[0] for r in test}:raise ValueError('Train/test identity conflict')
    held=unseen_test(test,seen,count)
    sem28,used28=fit_model(data,train,28);bd28,used28b=train_boundary(train,used28)
    extra_items=choose_superset_training(train,used28,68)
    sem96,used96=fit_model(data,extra_items,96);bd96,used96b=train_boundary(train,used96)
    if len(set(used96))!=96 or not set(used28).issubset(set(used96)):
        raise ValueError('96 examples must include all 28 original training cases')
    # Controls: baseline must use exactly the historical 28-image selection.
    old=json.loads((root/'v13/results/metrics.json').read_text())
    if set(used28)!=set(old['train_used']):raise ValueError('Frozen v13 training IDs unexpectedly changed')
    if set(used28b)!=set(used28) or set(used96b)!=set(used96):raise ValueError('Boundary/core image training sets differ')
    rows=[]
    for stem,image,mask in held:
        im,_=prepare_image(image);gt=prepare_instances(mask,im.shape)
        p28=predict_instances(sem28,bd28,im);p96=predict_instances(sem96,bd96,im)
        row={'id':stem,'gt_count':int(np.unique(gt[gt>0]).size),
             'polarity_for_reporting_only':foreground_polarity(im,gt),
             'v13_28':match_instances(p28,gt),'v15_96':match_instances(p96,gt)}
        rows.append(row)
        if len(rows)<=8:draw(im,gt,p28,p96,out/f'{stem}.jpg',stem)
        print(stem,'v13 TP',row['v13_28']['tp'],'v15 TP',row['v15_96']['tp'],flush=True)
    old=aggregate(rows,'v13_28');new=aggregate(rows,'v15_96')
    by_polarity={group:{k:aggregate([r for r in rows if r['polarity_for_reporting_only']==group],k) for k in ('v13_28','v15_96')} for group in ('bright','dark','low_contrast','uncertain') if any(r['polarity_for_reporting_only']==group for r in rows)}
    obj={'source':'EMPS official train/test at pinned revision, new subset not previously evaluated',
         'historical_test_ids':sorted(seen),'test_ids':[r['id'] for r in rows],
         'v13_train_ids':used28,'v15_train_ids':used96,'frozen_model_hyperparams':True,
         'frozen_prediction_thresholds':{'core':CORE_THRESHOLD,'border':BORDER_THRESHOLD,
                                        'marker_area':MIN_SEED_AREA,'erosion':EROSION},
         'v13_28':old,'v15_96':new,'by_polarity':by_polarity,'per_image':rows,
         'go_if_improved':new['micro_f1']>old['micro_f1'],
         'note':'20 additional official test images, same EMPS family, NOT external TEM microscope data.'}
    (out/'metrics.json').write_text(json.dumps(obj,indent=2)+'\n')
    with (out/'per_image.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['id','polarity','gt','v13_tp','v15_tp','v13_fp','v15_fp','v13_fn','v15_fn'])
        for r in rows:w.writerow([r['id'],r['polarity_for_reporting_only'],r['gt_count'],r['v13_28']['tp'],r['v15_96']['tp'],r['v13_28']['fp'],r['v15_96']['fp'],r['v13_28']['fn'],r['v15_96']['fn']])
    print(json.dumps({'v13_28':old,'v15_96':new,'go_if_improved':obj['go_if_improved']},indent=2),flush=True)
    return obj

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset-root',required=True);p.add_argument('--out',required=True);p.add_argument('--count',type=int,default=20)
    a=p.parse_args();run(a.dataset_root,a.out,a.count)
