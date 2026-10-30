#!/usr/bin/env python3
"""True annotated TEM/SEM nanoparticle benchmarking on EMPS (Yildirim & Cole).

Official train/test split; no test GT leaks into RF training or thresholds.
Reports pixel segmentation AND instance-aware one-to-one IoU matching.
"""
from __future__ import annotations
import argparse,csv,json,math,hashlib
from pathlib import Path
import cv2,numpy as np
from scipy import ndimage as ndi
from scipy.optimize import linear_sum_assignment
from skimage import measure,segmentation,feature
from sklearn.ensemble import RandomForestClassifier
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

RNG=20261030

def read_pairs(root,split):
    root=Path(root)
    rows=[p.strip().replace('.png','') for p in (root/f'{split}.csv').read_text().splitlines() if p.strip()]
    if len(rows)!=len(set(rows)):raise ValueError(f'Duplicate sample in {split}')
    items=[]
    for stem in rows:
        a=root/'images'/f'{stem}.png'; b=root/'segmaps'/f'{stem}.png'
        if not (a.exists() and b.exists()):raise FileNotFoundError(f'Missing aligned pair for {stem}')
        items.append((stem,a,b))
    return items

def prepare_image(path,max_side=512):
    im=cv2.imread(str(path),cv2.IMREAD_UNCHANGED)
    if im is None:raise ValueError(f'Cannot read {path}')
    if im.ndim==3:
        if im.shape[-1]==4:im=cv2.cvtColor(im,cv2.COLOR_BGRA2GRAY)
        else:im=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
    if im.ndim!=2:raise ValueError('not grayscale 2D')
    h,w=im.shape
    scale=min(1.0,max_side/max(h,w))
    if scale<1:im=cv2.resize(im,(max(16,round(w*scale)),max(16,round(h*scale))),interpolation=cv2.INTER_AREA)
    return robust(im), im.shape

def robust(image):
    x=image.astype(np.float32)
    lo,hi=np.percentile(x,[.5,99.5])
    return np.clip((x-lo)/max(float(hi-lo),1e-6),0,1).astype(np.float32)

def prepare_instances(mask_path, target_shape):
    raw=np.array(Image.open(mask_path))
    if raw.ndim!=2:raise ValueError(f'Instance ID image must be single-channel: {mask_path} shape {raw.shape}')
    if np.issubdtype(raw.dtype,np.floating):raise ValueError('Float instance IDs unsupported')
    if int(np.min(raw))<0:raise ValueError('Negative instance IDs')
    if raw.shape!=target_shape:
        raw=cv2.resize(raw.astype('int32'),target_shape[::-1],interpolation=cv2.INTER_NEAREST)
    # A single-particle image legitimately has labels {0,1}; retain ID 1.
    return raw.astype(np.int32)

def features(img):
    img=np.asarray(img,dtype=np.float32)
    # Multiscale local contrast, gradient and texture; NOT brightness clustering.
    p=[img]
    for s in (1.,2.5,5.,10.,18.):
        z=cv2.GaussianBlur(img,(0,0),s)
        p.extend([z,img-z])
    sobel=cv2.Sobel(img,cv2.CV_32F,1,0,ksize=3)**2+cv2.Sobel(img,cv2.CV_32F,0,1,ksize=3)**2
    p.extend([np.sqrt(sobel),cv2.Laplacian(cv2.GaussianBlur(img,(0,0),2),cv2.CV_32F),
              cv2.GaussianBlur(img*img,(0,0),3)-cv2.GaussianBlur(img,(0,0),3)**2])
    return np.stack(p,axis=-1).astype(np.float32)

def fit_model(root,train_items,n=28,pix_per_class=1000,seed=RNG):
    rng=np.random.default_rng(seed)
    if len(train_items)<4:raise ValueError('Too few train images')
    chosen=rng.choice(len(train_items),size=min(len(train_items),n),replace=False)
    xs=[];ys=[];used=[]
    for index in chosen:
        stem,src,msk=train_items[int(index)]
        img,_=prepare_image(src)
        lab=prepare_instances(msk,img.shape)
        y=(lab>0).ravel()
        pos=np.flatnonzero(y);neg=np.flatnonzero(~y)
        if min(len(pos),len(neg))<20:continue
        ids=np.r_[rng.choice(pos,size=min(pix_per_class,len(pos)),replace=False),
                  rng.choice(neg,size=min(pix_per_class,len(neg)),replace=False)]
        x=features(img).reshape(-1,14)
        xs.append(x[ids]);ys.append(y[ids]);used.append(stem)
    if len(used)<4:raise ValueError('Insufficient nonempty training pairs')
    model=RandomForestClassifier(n_estimators=42,max_depth=18,min_samples_leaf=3,n_jobs=1,
                                 class_weight='balanced_subsample',random_state=seed)
    model.fit(np.concatenate(xs),np.concatenate(ys))
    return model,used

def predict(model,img,thr=.52):
    x=features(img)
    probability=model.predict_proba(x.reshape(-1,x.shape[-1]))[:,list(model.classes_).index(True)].reshape(img.shape)
    mask=probability>=thr
    mask=ndi.binary_fill_holes(ndi.binary_opening(mask,iterations=1))
    return mask,probability

def watersplit(mask,typical_distance=9):
    if not mask.any():return np.zeros_like(mask,np.int32)
    dt=ndi.distance_transform_edt(mask)
    peaks=feature.peak_local_max(dt,labels=mask,min_distance=typical_distance,
                                 threshold_abs=1.5,exclude_border=False)
    seeds=np.zeros_like(mask,np.int32)
    for j,(r,c) in enumerate(peaks,1):seeds[r,c]=j
    if not len(peaks):return measure.label(mask).astype(np.int32)
    return segmentation.watershed(-dt,seeds,mask=mask).astype(np.int32)

def pixel_score(pred,gt):
    p=pred>0;g=gt>0
    tp=int(np.count_nonzero(p&g));fp=int(np.count_nonzero(p&~g));fn=int(np.count_nonzero(~p&g))
    return {'dice':2*tp/max(1,2*tp+fp+fn),'iou':tp/max(1,tp+fp+fn),
            'precision':tp/(tp+fp) if tp+fp else 0.,'recall':tp/(tp+fn) if tp+fn else 0.}

def match_instances(pred,gt,threshold=.5, min_pixels=12):
    p=np.asarray(pred,np.int32);g=np.asarray(gt,np.int32)
    if p.shape!=g.shape:raise ValueError('GT and predictions have different shapes')
    # Compress arbitrary positive IDs to contiguous small integers. A large
    # instance value must never allocate an array sized by max(label).
    orig_p,ip,cnt_p=np.unique(p,return_inverse=True,return_counts=True)
    orig_g,ig,cnt_g=np.unique(g,return_inverse=True,return_counts=True)
    valid_p=(orig_p>0)&(cnt_p>=min_pixels)
    valid_g=(orig_g>0)&(cnt_g>=min_pixels)
    pids=orig_p[valid_p];gids=orig_g[valid_g]
    if not len(gids) or not len(pids):
        tp=0;fp=len(pids);fn=len(gids);mae=None
    else:
        mapping_p=np.zeros(len(orig_p),np.int32);mapping_g=np.zeros(len(orig_g),np.int32)
        mapping_p[valid_p]=np.arange(1,len(pids)+1);mapping_g[valid_g]=np.arange(1,len(gids)+1)
        cp=mapping_p[ip].reshape(p.shape);cg=mapping_g[ig].reshape(g.shape)
        overlap=np.bincount((cp.astype(np.int64)*(len(gids)+1)+cg).ravel(),
                            minlength=(len(pids)+1)*(len(gids)+1)).reshape(len(pids)+1,len(gids)+1)
        pp=np.bincount(cp.ravel(),minlength=len(pids)+1)[1:]
        gg=np.bincount(cg.ravel(),minlength=len(gids)+1)[1:]
        inter=overlap[1:,1:];union=pp[:,None]+gg[None,:]-inter
        iou=np.where(union>0,inter/np.maximum(union,1),0.)
        ii,jj=linear_sum_assignment(1-iou)
        ok=iou[ii,jj]>=threshold
        tp=int(ok.sum());fp=len(pids)-tp;fn=len(gids)-tp
        mae=(float(np.mean(np.abs(2*np.sqrt(pp[ii[ok]]/np.pi)-2*np.sqrt(gg[jj[ok]]/np.pi)))) if tp else None)
    return {'gt_instances':int(len(gids)),'pred_instances':int(len(pids)),'tp':int(tp),'fp':int(fp),'fn':int(fn),
            'precision':tp/(tp+fp) if tp+fp else 0., 'recall':tp/(tp+fn) if tp+fn else 0.,
            'diameter_mae_px':mae}

def contours(ax,mask,color,instances=False):
    # Draw every annotated instance separately when GT contains instance IDs.
    if instances:
        labels=np.unique(mask)
        for label in labels[labels>0]:
            one=mask==label
            for c in measure.find_contours(one.astype('float32'),.5):ax.plot(c[:,1],c[:,0],lw=.85,color=color)
    else:
        for c in measure.find_contours((mask>0).astype('float32'),.5):ax.plot(c[:,1],c[:,0],lw=.85,color=color)

def figure(path,img,gt,pred,prob):
    fig,axs=plt.subplots(1,4,figsize=(14.4,4))
    axs[0].imshow(img,cmap='gray');axs[0].set_title('Measured TEM/SEM input')
    axs[1].imshow(img,cmap='gray');contours(axs[1],gt,'#fff042',instances=True);axs[1].set_title('Instance GT (yellow)')
    axs[2].imshow(img,cmap='gray');contours(axs[2],gt,'#fff042',instances=True);contours(axs[2],pred,'#27edff');axs[2].set_title('GT yellow / RF cyan')
    axs[3].imshow(prob,cmap='magma',vmin=0,vmax=1);axs[3].set_title('Supervised RF probability')
    for a in axs:a.axis('off')
    fig.tight_layout();fig.savefig(path,dpi=125);plt.close(fig)

def main(root,out,train_count=28,test_count=8,seed=RNG):
    root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    train=read_pairs(root,'train');test=read_pairs(root,'test')
    if {x[0] for x in train} & {x[0] for x in test}:raise ValueError('Train/test duplicate file names')
    model,used=fit_model(root,train,train_count,seed=seed)
    rng=np.random.default_rng(seed)
    chosen=rng.choice(len(test),size=min(test_count,len(test)),replace=False)
    rows=[]
    for seq,i in enumerate(chosen):
        stem,src,mask_path=test[int(i)]
        img,_=prepare_image(src);gt=prepare_instances(mask_path,img.shape)
        mask,prob=predict(model,img)
        # Compare 1) connected components with 2) watershed for contacts
        contiguous=measure.label(mask).astype(np.int32)
        segmented=watersplit(mask)
        row={'id':stem,'GT_instances':int(np.unique(gt[gt>0]).size),'pixel':pixel_score(mask,gt),
             'instance_connected':match_instances(contiguous,gt),'instance_watershed':match_instances(segmented,gt)}
        rows.append(row)
        if seq<6:figure(out/f'{stem}.jpg',img,gt,segmented,prob)
        print(stem,'Dice',round(row['pixel']['dice'],3),'TP',row['instance_watershed']['tp'],
              'FP',row['instance_watershed']['fp'],'FN',row['instance_watershed']['fn'],flush=True)
    d={'source':'EMPS by256/emps, B. Yildirim & J. Cole (2021)',
       'official_split':'train.csv / test.csv','training_used_test_annotations':False,
       'seed':seed,'train_images':used,'test_files':[r['id'] for r in rows],
       'model':'42-tree multiscale-feature RandomForest, frozen threshold=0.52',
       'metrics':rows,'aggregate':{}}
    for group in ('pixel','instance_connected','instance_watershed'):
        keys=('dice','iou') if group=='pixel' else ('precision','recall')
        d['aggregate'][group]={k:float(np.mean([r[group][k] for r in rows])) for k in keys}
    (out/'metrics.json').write_text(json.dumps(d,indent=2,ensure_ascii=False))
    return d

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset-root',required=True);p.add_argument('--out',default='experiments/v10/results_emps')
    p.add_argument('--train-count',type=int,default=28);p.add_argument('--test-count',type=int,default=8)
    a=p.parse_args();r=main(a.dataset_root,a.out,a.train_count,a.test_count)
    print(json.dumps(r['aggregate'],indent=2))
