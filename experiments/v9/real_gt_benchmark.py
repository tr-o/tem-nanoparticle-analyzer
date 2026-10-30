#!/usr/bin/env python3
"""v9 LBNL human-mask benchmark. Labels are NEVER used to tune thresholds."""
import argparse, csv, json
from pathlib import Path
import cv2, h5py, numpy as np
from scipy import ndimage as ndi
from skimage import morphology, measure
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"v8"))
from hrtem_texture import gabor_coherence

def discover(f):
    found=[]
    def visit(name,obj):
        if isinstance(obj,h5py.Dataset) and obj.ndim in (3,4) and all(s>0 for s in obj.shape):
            found.append((name,obj.shape))
    f.visititems(visit)
    if not found: raise ValueError("No 3D/4D image tensors found")
    found.sort(key=lambda x:np.prod(x[1]),reverse=True)
    return found[0]

def read_sample(ds,i):
    shape=ds.shape
    if len(shape)==4:
        if shape[-1]==1:return np.asarray(ds[i,:,:,0])
        if shape[1]==1:return np.asarray(ds[i,0,:,:])
        raise ValueError("Not a single-channel 4D tensor: "+str(shape))
    if len(shape)==3:
        if shape[1]>=64 and shape[2]>=64:return np.asarray(ds[i,:,:])
        if shape[0]>=64 and shape[1]>=64:return np.asarray(ds[:,:,i])
    raise ValueError("Unexpected array orientation: "+str(shape))

def count_samples(ds):
    if ds.ndim==4:return ds.shape[0]
    return ds.shape[0] if ds.shape[1]>=64 and ds.shape[2]>=64 else ds.shape[-1]

def norm(im):
    x=np.asarray(im,dtype=np.float32)
    lo,hi=np.percentile(x,[.5,99.5])
    return np.clip((x-lo)/(hi-lo),0,1) if hi>lo else np.zeros_like(x)

def v8_mask(im):
    x=norm(im)
    dark=np.maximum(ndi.gaussian_filter(x,28)-ndi.gaussian_filter(x,4.2),0)
    m=(dark>.025)&(gabor_coherence(x)>.12)
    m=ndi.binary_fill_holes(ndi.binary_closing(m,iterations=4))
    return morphology.remove_small_objects(m,min_size=16)

def v9_mask(im):
    """Higher specificity: background and irregular/merged detections are rejected."""
    x=norm(im)
    dark=np.maximum(ndi.gaussian_filter(x,28)-ndi.gaussian_filter(x,4.2),0)
    m=(dark>.029)&(gabor_coherence(x)>.19)
    m=ndi.binary_fill_holes(ndi.binary_closing(m,iterations=3))
    labels=measure.label(m)
    keep=np.zeros_like(m,dtype=bool)
    for obj in measure.regionprops(labels):
        if obj.area<95:continue
        circ=4*np.pi*obj.area/max(obj.perimeter_crofton**2,1)
        if circ<.55 or obj.solidity<.80:continue
        r0,c0,r1,c1=obj.bbox
        if r0==0 or c0==0 or r1==im.shape[0] or c1==im.shape[1]:continue
        keep[labels==obj.label]=True
    return keep

def gt_mask(raw):
    x=np.asarray(raw)
    if x.ndim!=2 or not np.all(np.isfinite(x)):raise ValueError("Invalid GT mask")
    u=np.unique(x)
    if len(u)==1:return x!=0
    if len(u)==2:return x==u.max()
    if not np.issubdtype(x.dtype,np.integer) or np.min(x)<0:
        raise ValueError("Non-binary/instance GT (unsupported); refuses evaluation")
    return x>0

def metrics(pred,truth):
    p=np.asarray(pred,bool);g=np.asarray(truth,bool)
    tp=int(np.count_nonzero(p&g));fp=int(np.count_nonzero(p&~g))
    fn=int(np.count_nonzero(~p&g))
    if not np.any(p) and not np.any(g):dice=iou=1.
    else:
        dice=2*tp/max(1,2*tp+fp+fn);iou=tp/max(1,tp+fp+fn)
    return dict(dice=round(dice,5),iou=round(iou,5),precision=round(tp/max(1,tp+fp),5),
                recall=round(tp/max(1,tp+fn),5),fp=fp,fn=fn)

def plot(im,gt,old,new,out,title):
    img=norm(im)
    rgb=np.stack([img,img,img],axis=-1)
    a=rgb.copy();b=rgb.copy()
    for buf,p in [(a,old),(b,new)]:
        buf[morphology.binary_dilation(gt)^morphology.binary_erosion(gt)]=[1,.2,.2]
        buf[morphology.binary_dilation(p)^morphology.binary_erosion(p)]=[.2,.9,.2]
    fig,axes=plt.subplots(1,4,figsize=(14,4))
    for ax,m,txt in zip(axes,[img,gt,a,b],
                        ["Original HRTEM","Manual segmentation GT","v8: red GT / green predicted","v9: red GT / green predicted"]):
        ax.imshow(m,cmap="gray" if m.ndim==2 else None)
        ax.set_title(txt,fontsize=9);ax.axis("off")
    fig.suptitle(title);fig.tight_layout()
    fig.savefig(out,dpi=140);plt.close(fig)

def benchmark(images,labels,out,n=8,seed=20261030):
    output=Path(out);output.mkdir(parents=True,exist_ok=True)
    with h5py.File(images,"r") as a,h5py.File(labels,"r") as b:
        imkey,imshape=discover(a);gtkey,gtshape=discover(b)
        img=a[imkey];lbl=b[gtkey]
        ni=count_samples(img);nl=count_samples(lbl)
        if ni!=nl:raise ValueError(f"Unmatched number of images and masks: {ni} vs {nl}")
        chosen=sorted(int(v) for v in np.random.default_rng(seed).choice(ni,min(n,ni),replace=False))
        scores=[]
        for pos,i in enumerate(chosen):
            im=read_sample(img,i);gt=gt_mask(read_sample(lbl,i))
            if im.shape!=gt.shape:raise ValueError(f"Image/mask shape mismatch: {im.shape}/{gt.shape}")
            old=v8_mask(im);new=v9_mask(im)
            row=dict(index=i,blank=not bool(np.any(gt)),v8=metrics(old,gt),v9=metrics(new,gt))
            scores.append(row)
            if pos<6:plot(im,gt,old,new,output/f"patch_{i}.jpg",f"Human-labeled patch index {i}")
            print("patch",i,"GT foreground",round(float(gt.mean()),3),"v8 Dice",row["v8"]["dice"],"v9 Dice",row["v9"]["dice"],flush=True)
    def aggregate(key):
        nonblank=[r[key] for r in scores if not r["blank"]]
        empty=[r[key] for r in scores if r["blank"]]
        return dict(n=len(scores),nonblank_n=len(nonblank),blank_n=len(empty),
            mean_nonblank_dice=round(float(np.mean([r["dice"] for r in nonblank])),5) if nonblank else None,
            mean_nonblank_iou=round(float(np.mean([r["iou"] for r in nonblank])),5) if nonblank else None,
            blank_false_positive_pixels=sum(r["fp"] for r in empty))
    result=dict(origin="LBNL Dryad 10.7941/D1SP93, MANUAL labels",image_name=Path(images).name,
        label_name=Path(labels).name,image_dataset=imkey,mask_dataset=gtkey,indices=chosen,
        no_training_or_threshold_tuning_on_labels=True,v8=aggregate("v8"),v9=aggregate("v9"),
        per_image=scores)
    (output/"metrics.json").write_text(json.dumps(result,indent=2))
    with (output/"scores.csv").open("w",newline="") as f:
        w=csv.writer(f);w.writerow(["index","GT_blank","v8_Dice","v9_Dice","v8_IoU","v9_IoU"])
        for r in scores:w.writerow([r["index"],r["blank"],r["v8"]["dice"],r["v9"]["dice"],r["v8"]["iou"],r["v9"]["iou"]])
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--images",required=True)
    p.add_argument("--labels",required=True);p.add_argument("--out",required=True)
    p.add_argument("--count",type=int,default=8)
    args=p.parse_args()
    res=benchmark(args.images,args.labels,args.out,args.count)
    print(json.dumps({"v8":res["v8"],"v9":res["v9"]},indent=2))
