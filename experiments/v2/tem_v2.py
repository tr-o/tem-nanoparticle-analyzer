#!/usr/bin/env python3
"""TEM real-domain adaptation v2: weak-label RF + conservative instance filtering.

All images MUST provide a calibrated nm/pixel to report nanometers. Original web
figures are for research demonstration; counts without ground truth do not imply precision.
"""
from __future__ import annotations
import argparse,csv,json,sys,math
from pathlib import Path
import cv2,joblib,numpy as np
from scipy import ndimage as ndi
from skimage import measure,segmentation,morphology,feature
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.metrics import f1_score,jaccard_score
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tem_analyzer.geometry import draw_roi_contours
from tem_analyzer.legacy_rf import read_gray,read_mask,feature_stack,normalize,predict_probability
from scale_calibration import detect_scale,exclusion_mask,draw_scale_overlay,transfer_calibration
from dataclasses import asdict

TRAIN_MODEL=ROOT/'experiments/v2/model_rf_real_weak.joblib'
MODEL=(ROOT/'models/weak_tem_rf.joblib' if (ROOT/'models/weak_tem_rf.joblib').exists() else TRAIN_MODEL)

def train(seed=2026,trees=48):
    rng=np.random.default_rng(seed);xx=[];yy=[];ww=[]
    src=[]
    for img in sorted((ROOT/'demo_data/train/images').glob('*.png')):
        src.append((img,ROOT/'demo_data/train/masks'/img.name,'simulated'))
    for d in sorted((ROOT/'experiments/v2/weak_labels').iterdir()):
        if (d/'labels.png').exists():src.append((d/'image.png',d/'labels.png','real_weak'))
    for image_path,mask_path,kind in src:
        img=read_gray(image_path); labels=cv2.imread(str(mask_path),0)
        stack=feature_stack(img);feats=stack.reshape(-1,stack.shape[-1]); y=labels.ravel()
        count=3200 if kind=='simulated' else 12000
        inds=[]
        for c in (0,255):
            pool=np.flatnonzero(y==c)
            if len(pool):inds.append(rng.choice(pool,size=min(count//2,len(pool)),replace=False))
        idx=np.concatenate(inds)
        xx.append(feats[idx]);yy.append((y[idx]==255).astype('uint8'))
        ww.append(np.full(len(idx),2.2 if kind=='real_weak' else 1.,dtype='float32'))
        print(image_path.stem,kind, len(idx),int((y==255).sum()),flush=True)
    X=np.vstack(xx); Y=np.concatenate(yy); W=np.concatenate(ww)
    clf=ExtraTreesClassifier(n_estimators=trees,max_depth=19,min_samples_leaf=3,max_features='sqrt',n_jobs=4,random_state=seed, class_weight='balanced')
    clf.fit(X,Y,sample_weight=W)
    TRAIN_MODEL.parent.mkdir(parents=True,exist_ok=True)
    joblib.dump({'clf':clf,'model':'extra-trees real weak + synthetic','n_source':len(src),
                 'label_protocol':'white particle cores / black confident background / 128 unknown ignored'},TRAIN_MODEL,compress=3)
    print('saved',TRAIN_MODEL, 'X',X.shape,'classes',np.bincount(Y),flush=True)

def metadata_exclusion(shape):
    h,w=shape;m=np.zeros((h,w),bool)
    # annotation / scale bars in bottom right of collected vendor figures.
    # conservative fixed ROI: both scale line and label; note may also mask particles.
    m[int(.87*h):,int(.75*w):]=True
    return m

def split_candidates(prob,valid,min_area=22,threshold=.5,min_distance=7):
    smooth=ndi.gaussian_filter(prob,0.65)
    binary=(smooth>threshold)&valid
    binary=morphology.remove_small_objects(binary,max_size=max(0,int(min_area)-1))
    binary=ndi.binary_fill_holes(binary)&valid
    ccs,n=ndi.label(binary)
    dt=ndi.distance_transform_edt(binary)
    dts=ndi.gaussian_filter(dt,0.9)
    peaks=feature.peak_local_max(dts, min_distance=min_distance, threshold_abs=2.1,
                                  labels=ccs, num_peaks_per_label=16, exclude_border=False)
    by_cc={}
    for y,x in peaks:by_cc.setdefault(int(ccs[y,x]),[]).append((int(y),int(x)))
    markers=np.zeros(binary.shape,'int32'); parent_marker={}; count=0
    for prop in measure.regionprops(ccs):
        if prop.area<min_area:continue
        pts=by_cc.get(prop.label,[])
        if not pts:
            idx=prop.coords[np.argmax(dts[prop.coords[:,0],prop.coords[:,1]])];pts=[tuple(idx)]
        for y,x in pts:
            count+=1;markers[y,x]=count;parent_marker[count]=(int(prop.label),len(pts))
    ws=segmentation.watershed(-dt,markers,mask=binary,compactness=0.0)
    return ws, binary, ccs,parent_marker

def roi_stats(image,mask,forbidden):
    a=int(mask.sum()); ys,xs=np.where(mask)
    cy=float(ys.mean());cx=float(xs.mean())
    equivalent_d=math.sqrt(4*a/math.pi)
    outer=ndi.binary_dilation(mask,iterations=9)&~ndi.binary_dilation(mask,iterations=2)&~forbidden
    if int(outer.sum())<max(10,a//6):
        bg=float(np.median(ndi.gaussian_filter(image,11)[mask]))
        noise=float(ndi.gaussian_filter(image,2)[mask].std())
    else:
        bg=float(np.median(image[outer]));noise=float(np.std(image[outer]))
    inside=float(np.median(image[mask]))
    contrast=bg-inside
    # Historical spatial features for shape assessment, not absolute size selection.
    labels=measure.label(mask)
    prop=max(measure.regionprops(labels),key=lambda p:p.area)
    circ=4*math.pi*a/max(prop.perimeter_crofton**2,1)
    return dict(x_px=round(cx,2),y_px=round(cy,2),diameter_px=round(equivalent_d,3),area_px2=a,
                circularity=round(circ,3),solidity=round(prop.solidity,3),
                aspect_ratio=round(prop.axis_major_length/max(prop.axis_minor_length,1e-5),3),
                contrast=round(contrast,4),contrast_snr=round(contrast/max(noise,0.012),2),
                intensity_median=round(inside,3),background_median=round(bg,3))

def run(img_path,model_path=MODEL,outdir=None, threshold=.48, min_area=22, min_contrast=.095,
        min_diameter=6, min_distance=7,nm_per_px=None, auto_scale=True, confirm_short_bar=False,
        scale_reference=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    img=read_gray(img_path);norm=normalize(img)
    prob=predict_probability(model_path,img)
    cal=detect_scale(scale_reference or img_path,confirm_short_bar=confirm_short_bar)
    if scale_reference is not None:
        cal=transfer_calibration(cal,scale_reference,img_path)
    if nm_per_px is not None:
        if nm_per_px<=0:raise ValueError('nm_per_px must be positive')
        effective_nm_per_px=float(nm_per_px)
        calibration_source='manual_override'
    elif auto_scale and cal.status=='accepted':
        effective_nm_per_px=cal.nm_per_px
        calibration_source='ocr_and_bar'
    else:
        effective_nm_per_px=None
        calibration_source='unavailable' if auto_scale else 'auto_disabled'
    excluded=exclusion_mask(img.shape,cal)
    valid=~excluded
    labels,binary,parents,parent_map=split_candidates(prob,valid,min_area,threshold,min_distance)
    h,w=img.shape
    rows=[];overlay=cv2.cvtColor(np.uint8(norm*255),cv2.COLOR_GRAY2RGB)
    colors={'accepted':(45,240,100),'split_touching':(40,225,250),'rejected':(245,65,80)}
    labels_out=np.zeros(labels.shape,'int32')
    rid=0
    for p in measure.regionprops(labels):
        rid+=1;minr,minc,maxr,maxc=p.bbox
        mask=np.zeros(labels.shape,dtype=bool)
        mask[minr:maxr,minc:maxc]=p.image
        parent,nseed=parent_map.get(int(p.label),(0,1))
        minr,minc,maxr,maxc=p.bbox
        r0=max(0,minr-12);r1=min(h,maxr+12);c0=max(0,minc-12);c1=min(w,maxc+12)
        patch=(slice(r0,r1),slice(c0,c1))
        local_mask=mask[patch]
        stats=roi_stats(norm[patch],local_mask,binary[patch])
        stats['y_px']=round(stats['y_px']+r0,2)
        stats['x_px']=round(stats['x_px']+c0,2)
        y,x=stats['y_px'],stats['x_px']
        edge= bool(p.bbox[0]<=2 or p.bbox[1]<=2 or p.bbox[2]>=h-2 or p.bbox[3]>=w-2)
        reasons=[]
        if stats['area_px2']<min_area:reasons.append('too_small')
        if stats['diameter_px']<min_diameter:reasons.append('too_small_diameter')
        if stats['contrast']<min_contrast:reasons.append('weak_contrast')
        if stats['circularity']<.69:reasons.append('non_round')
        if stats['solidity']<.9:reasons.append('concave')
        if stats['aspect_ratio']>1.65:reasons.append('elongated')
        if edge:reasons.append('image_border')
        if nseed>=4:reasons.append('dense_aggregate')
        # More-than-two centers may be a chain of touching or stacked objects;
        # default: exclude until reviewed.
        if nseed==3 and stats['circularity']<.81:reasons.append('ambiguous_three_way_contact')
        status='rejected' if reasons else ('split_touching' if nseed>=2 else 'accepted')
        draw_roi_contours(overlay,local_mask,
                          roi_origin_xy=(int(c0),int(r0)),
                          color_rgb=colors[status],thickness=1,line_type=cv2.LINE_AA)
        if status!='rejected':labels_out[mask]=rid
        rows.append(dict(id=rid,status=status,rejection_reasons=';'.join(reasons),parent_id=parent,
                         n_seeds_in_parent=nseed,**stats))
    out=Path(outdir or ROOT/'experiments/v2/results'/Path(img_path).stem)
    out.mkdir(parents=True,exist_ok=True)
    with open(out/'particles_all.csv','w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['id','status']);writer.writeheader();writer.writerows(rows)
    acc=[r for r in rows if r['status']!='rejected']
    if effective_nm_per_px is not None:
        for r in rows:
            if r['status']!='rejected':
                r['diameter_nm']=round(r['diameter_px']*effective_nm_per_px,3)
                r['area_nm2']=round(r['area_px2']*effective_nm_per_px**2,3)
            else:
                r['diameter_nm']=''
                r['area_nm2']=''
    # Ensure consistent CSV header even when no accepted particles are present.
    if effective_nm_per_px is not None:
        cols=list(rows[0]) if rows else ['id','status','diameter_nm','area_nm2']
        with open(out/'particles_all.csv','w',newline='',encoding='utf8') as f:
            writer=csv.DictWriter(f,fieldnames=cols);writer.writeheader();writer.writerows(rows)
    with open(out/'particles_accepted.csv','w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=list(acc[0]) if acc else list(rows[0]) if rows else ['id','status']);writer.writeheader();writer.writerows(acc)
    cv2.imwrite(str(out/'overlay.png'),cv2.cvtColor(overlay,cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(out/'probability.png'),np.uint8(prob*255))
    cv2.imwrite(str(out/'excluded_metadata.png'),np.uint8(excluded)*255)
    cv2.imwrite(str(out/'scale_annotation.png'),draw_scale_overlay(img_path,cal))
    calibration=asdict(cal)
    calibration.update(effective_nm_per_px=effective_nm_per_px,calibration_source=calibration_source,
                       image_shape_px=list(img.shape),scale_conversion_applied=effective_nm_per_px is not None)
    (out/'calibration.json').write_text(json.dumps(calibration,indent=2,ensure_ascii=False),encoding='utf8')
    np.savez_compressed(out/'instances_accepted.npz', labels=labels_out)
    from matplotlib.patches import Patch
    fig,axs=plt.subplots(1,3,figsize=(14,4.8),gridspec_kw={'width_ratios':[1,1,1]})
    axs[0].imshow(norm,cmap='gray',vmin=0,vmax=1);axs[0].axis('off');axs[0].set_title('Original (500 px crop)')
    axs[1].imshow(overlay);axs[1].axis('off');axs[1].set_title('Accepted / split / rejected')
    axs[1].legend(handles=[Patch(color=np.array(colors[s])/255,label=s) for s in colors],loc='lower left',fontsize=7,framealpha=.8)
    ds=[r['diameter_px'] for r in acc]
    display_ds=([r['diameter_nm'] for r in acc] if effective_nm_per_px is not None else ds)
    axs[2].hist(display_ds,bins=min(20,max(4,int(np.sqrt(len(display_ds))))) if display_ds else 4,edgecolor='white')
    axs[2].set_xlabel('Equivalent diameter (nm)' if effective_nm_per_px is not None else 'Equivalent diameter (pixel)');axs[2].set_ylabel('Accepted detections')
    axs[2].set_title(f'N={len(acc)} | median={np.median(display_ds):.2f} '+('nm' if effective_nm_per_px is not None else 'px') if ds else 'No accepted particles')
    fig.suptitle(f'{Path(img_path).name}: v2 / real weak supervision',fontsize=12)
    fig.tight_layout();fig.savefig(out/'overview.png',dpi=140);plt.close(fig)
    result={ 'image':Path(img_path).name, 'model':str(model_path),'raw_instances':len(rows),
             'accepted':sum(r['status']=='accepted' for r in rows),
             'split_touching':sum(r['status']=='split_touching' for r in rows),
             'rejected':sum(r['status']=='rejected' for r in rows),
             'median_diameter_px':float(np.median(ds)) if ds else None,
             'nm_per_px':effective_nm_per_px,'calibration_status':cal.status,
             'calibration_source':calibration_source,
             'median_diameter_nm':float(np.median(display_ds)) if ds and effective_nm_per_px is not None else None,
             'limitations':'No independent manual ground truth; flags do not prove optical overlaps.' }
    (out/'summary.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser();subs=ap.add_subparsers(dest='command',required=True)
    sub=subs.add_parser('train');sub.add_argument('--trees',type=int,default=48)
    sub=subs.add_parser('predict');sub.add_argument('--image',required=True);sub.add_argument('--model',default=str(MODEL))
    sub.add_argument('--out',default=None);sub.add_argument('--min-contrast',type=float,default=.095)
    sub.add_argument('--threshold',type=float,default=.48);sub.add_argument('--min-distance',type=int,default=7)
    sub.add_argument('--nm-per-px',type=float,default=None)
    sub.add_argument('--disable-auto-scale',action='store_true')
    sub.add_argument('--confirm-short-bar',action='store_true')
    sub.add_argument('--scale-reference',default=None,help='Same original field at higher resolution for more accurate calibration')
    args=ap.parse_args()
    if args.command=='train':train(trees=args.trees)
    else:run(args.image,args.model,args.out,threshold=args.threshold,min_distance=args.min_distance,
             min_contrast=args.min_contrast,nm_per_px=args.nm_per_px,
             auto_scale=not args.disable_auto_scale,confirm_short_bar=args.confirm_short_bar,
             scale_reference=args.scale_reference)
