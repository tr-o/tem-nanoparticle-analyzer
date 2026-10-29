"""Actual DM3/DM4 particle-analysis workflow (research/provisional model)."""
from __future__ import annotations
import argparse,csv,hashlib,json,sys,math
from pathlib import Path
import cv2
import joblib
import numpy as np
from skimage import measure, morphology, segmentation, feature
from scipy import ndimage as ndi
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).resolve().parent))
from dm_io import load_dm,robust_preview,resize_scale,area_diameter_nm,json_safe
from tem_particle_ml import predict_probability,split_instances,feature_stack


def infer(path, model, output, dataset_index=None, frame=None, max_side=768, threshold=.52,
          min_area=12, confidence_min=.55, circularity_min=.55):
    original,meta=load_dm(path,dataset_index,frame)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    preview=robust_preview(original)
    old_shape=preview.shape
    if max(preview.shape)>max_side:
        ratio=max_side/max(preview.shape)
        new_shape=tuple(max(16,int(round(n*ratio))) for n in preview.shape)
        preview=cv2.resize(preview,(new_shape[1],new_shape[0]),interpolation=cv2.INTER_AREA)
    meta=resize_scale(meta,old_shape,preview.shape)
    # No screenshot scales: DM original pixels contain no overlaid scale annotation.
    prob=predict_probability(str(model),preview)
    labels,mask=split_instances(prob,threshold=threshold,min_area=min_area,min_distance=5,prominence=1.7)
    rows=[];accepted=[]
    H,W=preview.shape
    overlay=cv2.cvtColor(np.uint8(preview*255),cv2.COLOR_GRAY2RGB)
    for p in measure.regionprops(labels):
        if p.area<min_area:continue
        minr,minc,maxr,maxc=p.bbox
        edge=minr==0 or minc==0 or maxr==H or maxc==W
        local_prob=prob[p.coords[:,0],p.coords[:,1]]
        c=float(4*np.pi*p.area/max(p.perimeter_crofton**2,1))
        solidity=float(p.solidity)
        # Three-state decision: never claim a complex overlap is a single NP.
        conf=float(np.median(local_prob))
        if edge or conf<.4:state='rejected';why='edge_or_probability'
        elif c<circularity_min or solidity<.76:state='review';why='irregular_or_overlap_possible'
        elif conf<confidence_min:state='review';why='probability_uncertain'
        else:state='accepted';why='compact_confident_candidate'
        diam_px=math.sqrt(4*p.area/math.pi)
        dnm=area_diameter_nm(p.area,meta['x_nm_per_px'],meta['y_nm_per_px']) if state=='accepted' else None
        row={'id':int(p.label),'x_px':round(p.centroid[1],2),'y_px':round(p.centroid[0],2),
             'area_px2':int(p.area),'equivalent_diameter_px':round(diam_px,3),
             'equivalent_diameter_nm':round(dnm,4) if dnm is not None else None,
             'circularity':round(c,3),'solidity':round(solidity,3),'pixel_probability':round(conf,3),
             'status':state,'reason':why}
        rows.append(row)
        if state=='accepted':accepted.append(row)
        mask_local=labels[minr:maxr,minc:maxc]==p.label
        color={'accepted':(25,220,80),'review':(255,164,38),'rejected':(230,64,67)}[state]
        contours,_=cv2.findContours(np.uint8(mask_local),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for ct in contours:
            ct=ct+np.array([[[minc,minr]]],dtype=ct.dtype)
            cv2.polylines(overlay,[ct],True,color,1,lineType=cv2.LINE_AA)
    (output/'source_metadata.json').write_text(json.dumps(json_safe(meta),indent=2,ensure_ascii=False))
    names=['id','x_px','y_px','area_px2','equivalent_diameter_px','equivalent_diameter_nm','circularity','solidity','pixel_probability','status','reason']
    for name, data in [('all',rows),('accepted',accepted)]:
        with open(output/f'particles_{name}.csv','w',newline='') as f:
            w=csv.DictWriter(f,names);w.writeheader();w.writerows(data)
    cv2.imwrite(str(output/'raw_preview.png'),np.uint8(preview*255))
    cv2.imwrite(str(output/'probability.png'),np.uint8(np.clip(prob,0,1)*255))
    cv2.imwrite(str(output/'overlay.png'),cv2.cvtColor(overlay,cv2.COLOR_RGB2BGR))
    n_accept=sum(x['status']=='accepted' for x in rows)
    n_review=sum(x['status']=='review' for x in rows)
    n_reject=sum(x['status']=='rejected' for x in rows)
    ds=[r['equivalent_diameter_nm'] if meta['calibration_status']=='calibrated' else r['equivalent_diameter_px'] for r in accepted]
    fig,axs=plt.subplots(1,3,figsize=(13.2,4.5))
    axs[0].imshow(preview,cmap='gray');axs[0].set_title('DM raw pixel preview');axs[0].axis('off')
    axs[1].imshow(overlay);axs[1].set_title(f'Accepted {n_accept} | review {n_review} | rejected {n_reject}');axs[1].axis('off')
    axs[2].hist(ds,bins=min(20,max(5,int(np.sqrt(len(ds))))) if len(ds) else 5,edgecolor='white')
    axs[2].set_xlabel('Equivalent diameter (nm)' if meta['calibration_status']=='calibrated' else 'Equivalent diameter (pixel)')
    axs[2].set_ylabel('Accepted count');axs[2].set_title('Provisional distribution')
    fig.tight_layout();fig.savefig(output/'overview.jpg',dpi=120);plt.close(fig)
    summary={'source':str(path),'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
             'shape_original':list(old_shape),'shape_analysis':list(preview.shape),
             'calibration_status':meta['calibration_status'],'x_nm_per_px':meta['x_nm_per_px'],
             'y_nm_per_px':meta['y_nm_per_px'],'n_candidates':len(rows),
             'accepted':n_accept,'review':n_review,'rejected':n_reject,
             'median_equivalent_diameter_nm':float(np.median(ds)) if ds and meta['calibration_status']=='calibrated' else None,
             'median_equivalent_diameter_px':float(np.median(ds)) if ds and meta['calibration_status']!='calibrated' else None,
             'validation':'No independent hand-labeled ground truth; preliminary candidate measurements only.',
             'model':Path(model).name}
    (output/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True);parser.add_argument('--model',default=str(ROOT/'trained_rf.joblib'))
    parser.add_argument('--output',required=True);parser.add_argument('--dataset-index',type=int);parser.add_argument('--frame',type=int)
    parser.add_argument('--max-side',type=int,default=768);parser.add_argument('--threshold',type=float,default=.52)
    args=parser.parse_args()
    print(json.dumps(infer(args.image,args.model,args.output,args.dataset_index,args.frame,args.max_side,args.threshold),indent=2,ensure_ascii=False))
