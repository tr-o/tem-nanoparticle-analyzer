#!/usr/bin/env python3
"""HRTEM GT benchmark; pixel and component matching (never training on holdout).

Requires exact 'images' and 'labels' HDF5 keys. Refuses ambiguous tensor
layouts rather than risk a high score on misaligned images.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,sys
from pathlib import Path
import cv2,h5py,numpy as np
from scipy import ndimage as ndi
from scipy.optimize import linear_sum_assignment
from skimage import measure,morphology
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
# Frozen v8/v9 baselines are intentionally self-contained: no GT may influence thresholds.
from scipy import ndimage as ndi

def normalize(im):
    x=np.asarray(im,dtype=np.float32)
    lo,hi=np.percentile(x,[.5,99.5])
    return np.clip((x-lo)/(hi-lo),0,1) if hi>lo else np.zeros_like(x)

def gabor_coherence(im):
    features=[]
    for wavelength in (3.8,5.4,7.2):
        for theta in (0.,np.pi/4,np.pi/2,3*np.pi/4):
            k=cv2.getGaborKernel((23,23),3.2,theta,wavelength,.75,0,cv2.CV_32F)
            q=cv2.getGaborKernel((23,23),3.2,theta,wavelength,.75,np.pi/2,cv2.CV_32F)
            k-=k.mean();q-=q.mean()
            a=cv2.filter2D(im,-1,k);b=cv2.filter2D(im,-1,q)
            features.append(ndi.gaussian_filter(a*a+b*b,3))
    stack=np.sort(np.stack(features),axis=0)
    lead=np.mean(stack[-2:],axis=0);typ=np.median(stack,axis=0)
    c=np.maximum(lead-typ,0)
    return np.clip(c/max(float(np.percentile(c,99)),1e-8),0,1)

def v8_mask(image):
    x=normalize(image)
    dark=np.maximum(ndi.gaussian_filter(x,28)-ndi.gaussian_filter(x,4.2),0)
    m=(dark>.025)&(gabor_coherence(x)>.12)
    m=ndi.binary_fill_holes(ndi.binary_closing(m,iterations=4))
    return morphology.remove_small_objects(m,min_size=16)

def v9_mask(image):
    x=normalize(image)
    dark=np.maximum(ndi.gaussian_filter(x,28)-ndi.gaussian_filter(x,4.2),0)
    m=(dark>.029)&(gabor_coherence(x)>.19)
    m=ndi.binary_fill_holes(ndi.binary_closing(m,iterations=3))
    lab=measure.label(m);keep=np.zeros_like(m,bool)
    for obj in measure.regionprops(lab):
        if obj.area<95:continue
        circ=4*np.pi*obj.area/max(obj.perimeter_crofton**2,1)
        if circ<.55 or obj.solidity<.80:continue
        r0,c0,r1,c1=obj.bbox
        if r0==0 or c0==0 or r1==image.shape[0] or c1==image.shape[1]:continue
        keep[lab==obj.label]=True
    return keep


def tensor_layout(shape):
    """Support (N,512,512), (512,512,N), (N,512,512,1) and (N,1,512,512).

    Dataset metadata states source patches are 512x512. Reject ambiguity.
    """
    sh=tuple(shape)
    if len(sh)==3:
        if sh[1:]==(512,512) and sh[0]!=512:return 'nhw',sh[0]
        if sh[:2]==(512,512) and sh[2]!=512:return 'hwn',sh[2]
    if len(sh)==4:
        if sh[1:]==(512,512,1):return 'nhwc',sh[0]
        if sh[1:]==(1,512,512):return 'nchw',sh[0]
    raise ValueError(f"Unrecognized/ambiguous HDF5 tensor layout {sh}; inspect manually")


def get_slice(ds,mode,i):
    if mode=='nhw':return np.asarray(ds[i,:,:])
    if mode=='hwn':return np.asarray(ds[:,:,i])
    if mode=='nhwc':return np.asarray(ds[i,:,:,0])
    if mode=='nchw':return np.asarray(ds[i,0,:,:])
    raise ValueError(mode)


def read_pair(images,labels,index):
    im=get_slice(images['images'],images['mode'],index)
    gt=get_slice(labels['labels'],labels['mode'],index)
    if im.shape!=(512,512) or im.shape!=gt.shape:raise ValueError("Image/GT not aligned")
    if not np.isfinite(im).all():raise ValueError("nonfinite image")
    u=np.unique(gt)
    if not np.issubdtype(gt.dtype,np.integer) and (len(u)>2 or min(u)<0):
        raise ValueError("Ambiguous probability-valued ground truth")
    if len(u)>512:raise ValueError("Too many GT labels; verify encoding")
    if len(u)==1: binary=np.zeros_like(gt,dtype=bool) if u[0]==0 else np.ones_like(gt,dtype=bool)
    elif len(u)==2:
        if min(u)<0:raise ValueError("Negative GT class ID")
        binary=gt==u.max()
    elif np.issubdtype(gt.dtype,np.integer) and u[0]>=0:
        binary=gt>0
    else:raise ValueError("Unsupported GT encoding")
    return im,binary


def pixel_metrics(p,g):
    if p.shape!=g.shape:raise ValueError("pixel label size mismatch")
    tp=int((p&g).sum());fp=int((p&~g).sum());fn=int((~p&g).sum())
    dice=2*tp/(2*tp+fp+fn) if (2*tp+fp+fn) else 1.0
    iou=tp/(tp+fp+fn) if (tp+fp+fn) else 1.0
    return dict(dice=dice,iou=iou,precision=tp/(tp+fp) if tp+fp else (1. if not g.any() else 0.),
                recall=tp/(tp+fn) if tp+fn else 1.,fp_pixels=fp,fn_pixels=fn)


def instance_metrics(pred,gt,iou_threshold=.5,min_area=12):
    """Connected-component proxy; merged contacts require instance GT to resolve."""
    pa=measure.label(pred,connectivity=2);ga=measure.label(gt,connectivity=2)
    p=[x for x in measure.regionprops(pa) if x.area>=min_area]
    g=[x for x in measure.regionprops(ga) if x.area>=min_area]
    matched=[]
    if p and g:
        pidx={obj.label:i for i,obj in enumerate(p)};gidx={obj.label:i for i,obj in enumerate(g)}
        flat=pa.ravel().astype(np.int64)*(ga.max()+1)+ga.ravel()
        intersections=np.bincount(flat,minlength=(pa.max()+1)*(ga.max()+1)).reshape(pa.max()+1,ga.max()+1)
        iou=np.zeros((len(p),len(g)))
        for i,x in enumerate(p):
            for j,y in enumerate(g):
                inter=intersections[x.label,y.label]
                if inter: iou[i,j]=inter/(x.area+y.area-inter)
        rr,cc=linear_sum_assignment(1-iou)
        matched=[(p[i],g[j],iou[i,j]) for i,j in zip(rr,cc) if iou[i,j]>=iou_threshold]
    tp=len(matched);fp=len(p)-tp;fn=len(g)-tp
    dia_mae=float(np.mean([abs(2*math.sqrt(x.area/math.pi)-2*math.sqrt(y.area/math.pi)) for x,y,_ in matched])) if matched else None
    return dict(gt_components=len(g),pred_components=len(p),matched=tp,
                precision=tp/(tp+fp) if tp+fp else (1. if not g else 0.),
                recall=tp/(tp+fn) if tp+fn else 1.,diameter_mae_px=dia_mae,
                interpretation="component proxy only; GT may merge touching particles")


def contours(ax,mask,color,lw=1.1):
    for c in measure.find_contours(mask.astype('float32'),.5):
        ax.plot(c[:,1],c[:,0],color=color,lw=lw)


def make_figure(img,gt,masks,path,title):
    lo,hi=np.percentile(img,[.5,99.5]);vis=np.clip((img-lo)/max(hi-lo,1e-7),0,1)
    fig,axs=plt.subplots(1,4,figsize=(15.5,4.2))
    axs[0].imshow(vis,cmap='gray');axs[0].set_title('Source HRTEM')
    axs[1].imshow(vis,cmap='gray');contours(axs[1],gt,'#f0c82d');axs[1].set_title('Human GT: yellow')
    for ax,(k,v) in zip(axs[2:],masks.items()):
        ax.imshow(vis,cmap='gray');contours(ax,gt,'#f0c82d');contours(ax,v,'#20d7f1');ax.set_title(k+': GT yellow, prediction cyan')
    for ax in axs:ax.set_xlim(0,512);ax.set_ylim(512,0);ax.axis('off')
    fig.suptitle(title);fig.tight_layout();fig.savefig(path,dpi=125);plt.close(fig)


def evaluate(images_path,labels_path,out,count=8,seed=20261030):
    root=Path(out);root.mkdir(parents=True,exist_ok=True)
    rec=[]
    with h5py.File(images_path,'r') as iroot,h5py.File(labels_path,'r') as groot:
        for obj,key in [(iroot,'images'),(groot,'labels')]:
            if key not in obj or not isinstance(obj[key],h5py.Dataset):raise ValueError("Expected exact /"+key+" dataset")
        ims,lab=iroot['images'],groot['labels']
        mi,ni=tensor_layout(ims.shape);mg,ng=tensor_layout(lab.shape)
        if ni!=ng:raise ValueError("Mismatched images/labels count")
        if ni<2:raise ValueError("Not enough labeled samples")
        imsref={'images':ims,'mode':mi};labsref={'labels':lab,'mode':mg}
        selected=np.random.default_rng(seed).choice(ni,min(count,ni),replace=False)
        for j,index in enumerate(sorted(int(x) for x in selected)):
            im,gt=read_pair(imsref,labsref,index)
            old=v8_mask(im);new=v9_mask(im)
            row={'index':index,'gt_fg_fraction':float(gt.mean()),
                'v8_pixel':pixel_metrics(old,gt),'v9_pixel':pixel_metrics(new,gt),
                'v8_components':instance_metrics(old,gt),'v9_components':instance_metrics(new,gt)}
            rec.append(row)
            if j<6:make_figure(im,gt,{'v8':old,'v9':new},root/f'example_{index}.jpg',f'GT holdout sample {index}; no label-based tuning')
            print(index,'foreground',round(float(gt.mean()),3),'dice v8',round(row['v8_pixel']['dice'],3),'v9',round(row['v9_pixel']['dice'],3),flush=True)
    summary={}
    for name in ['v8','v9']:
        nonempty=[x for x in rec if x['gt_fg_fraction']>0];empty=[x for x in rec if x['gt_fg_fraction']==0]
        summary[name]={'n':len(rec),'nonempty_n':len(nonempty),'empty_n':len(empty),
          'dice_mean_nonempty':float(np.mean([r[name+'_pixel']['dice'] for r in nonempty])) if nonempty else None,
          'iou_mean_nonempty':float(np.mean([r[name+'_pixel']['iou'] for r in nonempty])) if nonempty else None,
          'component_precision_mean_nonempty':float(np.mean([r[name+'_components']['precision'] for r in nonempty])) if nonempty else None,
          'component_recall_mean_nonempty':float(np.mean([r[name+'_components']['recall'] for r in nonempty])) if nonempty else None,
          'blank_pred_positive_pixels':sum(r[name+'_pixel']['fp_pixels'] for r in empty)}
    res={'dataset':'Dryad doi:10.7941/D1SP93', 'source_image_file':Path(images_path).name,
        'source_label_file':Path(labels_path).name,'sample_count':len(rec),'sample_indices':[x['index'] for x in rec],
        'image_layout':mi,'label_layout':mg,
        'labels_used_for_training_or_tuning':False, 'note':'Connected component matching is a proxy, not manually labeled instances',
        'summary':summary,'per_image':rec}
    (root/'metrics.json').write_text(json.dumps(res,indent=2,ensure_ascii=False))
    with (root/'scores.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['index','GT_fraction','v8_Dice','v9_Dice','v8_IoU','v9_IoU','v8_component_recall','v9_component_recall'])
        for r in rec:w.writerow([r['index'],r['gt_fg_fraction'],r['v8_pixel']['dice'],r['v9_pixel']['dice'],r['v8_pixel']['iou'],r['v9_pixel']['iou'],r['v8_components']['recall'],r['v9_components']['recall']])
    return res

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--images',required=True);p.add_argument('--labels',required=True)
    p.add_argument('--out',default='v10/results_human');p.add_argument('--count',type=int,default=8)
    a=p.parse_args();print(json.dumps(evaluate(a.images,a.labels,a.out,a.count)['summary'],indent=2))
