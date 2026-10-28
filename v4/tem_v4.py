#!/usr/bin/env python3
"""TEM v4: audit-first particle selection, multi-center rescue, review queue.

This module never treats an arbitrary increase in particle counts as accuracy.
Original v3.1 OCR calibration is preserved and may be reused when accessible.
Core model uses simulated + *weak* real annotations; results are not validated GT.
"""
from __future__ import annotations
import sys, json, math, csv, argparse
from pathlib import Path
from collections import Counter, defaultdict
import numpy as np
import cv2
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage import measure, feature, segmentation, morphology
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'v2'))
from tem_particle_ml import read_gray, normalize,predict_probability
from tem_v2 import split_candidates, roi_stats, MODEL
from scale_calibration import detect_scale, transfer_calibration,exclusion_mask
from dataclasses import asdict


def rescue_split(prob, image, valid, threshold=.48, min_area=22, min_distance=7,
                 dark_min=.11, dark_spacing=3, area_per_marker=100):
    """Recover distinct dark centers inside undersegmented connected regions.

    Marker watershed is run on a locally high-pass filtered dark-center field;
    it cannot resolve true projection overlap, therefore doubtful new pieces
    become 'review' instead of accepted automatically.
    """
    old, binary, parents, pm = split_candidates(prob, valid, min_area,threshold,min_distance)
    # Estimate the characteristic isolated-particle diameter FROM the image.
    # Otherwise an isolated 25-px Ag sphere gets split into dozens of 4-px
    # false 'particles' by noisy local minima.
    props=measure.regionprops(parents)
    clear_d=[math.sqrt(4*p.area/math.pi) for p in props if p.area>=min_area
             and (4*math.pi*p.area/max(p.perimeter_crofton**2,1))>.80 and p.solidity>.90]
    typical_d=float(np.median(clear_d)) if clear_d else 12.
    typical_area=math.pi*(typical_d/2)**2
    spacing=max(dark_spacing,int(round(typical_d*.61)))
    smooth=ndi.gaussian_filter(normalize(image),1.1)
    dark=ndi.gaussian_filter(normalize(image),max(4.,typical_d*.27))-smooth
    candidates=feature.peak_local_max(dark,min_distance=spacing,threshold_abs=dark_min,
                                      labels=parents,exclude_border=False)
    peaks_by_parent=defaultdict(list)
    for y,x in candidates:
        if prob[y,x]>=max(.52,threshold) and valid[y,x]:
            peaks_by_parent[int(parents[y,x])].append((int(y),int(x)))
    old_by_parent=defaultdict(list)
    for p in measure.regionprops(old):
        center=p.coords[np.argmax(ndi.distance_transform_edt(old==p.label)[p.coords[:,0],p.coords[:,1]])] if p.area<60 else np.asarray(p.centroid).round().astype(int)
        par=parents[tuple(p.coords[0])]
        old_by_parent[int(par)].append(tuple(int(x) for x in center))
    new_markers=np.zeros(old.shape,np.int32)
    seed_kind={}; parent_counts={}; recovered_parent=set(); pid=0
    for p in measure.regionprops(parents):
        if p.area < min_area:continue
        oldpts=old_by_parent.get(p.label,[])
        darkpts=sorted(peaks_by_parent.get(p.label,[]), key=lambda t:float(dark[t]),reverse=True)
        # Rescue only clearly undersegmented LARGE parents. Do not split well-formed
        # small isolated particles based on within-particle intensity noise.
        circ=4*math.pi*p.area/max(p.perimeter_crofton**2,1)
        aspect=p.axis_major_length/max(p.axis_minor_length,1e-4)
        irregular=(circ<.69 or p.solidity<.85 or aspect>1.85)
        rescue=(irregular and p.area >= max(75,1.8*typical_area,area_per_marker*len(oldpts))
                and len(darkpts)>=max(2,len(oldpts)+1))
        if rescue:
            # Per-image particle scale controls splitting density.
            budget=max(len(oldpts)+1,int(math.ceil(p.area/max(typical_area*.67,12))))
            chosen=[]
            for pt in darkpts:
                if all((pt[0]-q[0])**2+(pt[1]-q[1])**2 >= spacing**2 for q in chosen):
                    chosen.append(pt)
                if len(chosen)>=budget:break
            if len(chosen)<=len(oldpts):rescue=False
        if not rescue:
            chosen=[]
            for pt in oldpts:
                y,x=pt
                if not (0<=y<old.shape[0] and 0<=x<old.shape[1] and parents[y,x]==p.label):
                    pt=tuple(p.coords[np.argmax(dark[p.coords[:,0],p.coords[:,1]])]);
                chosen.append(pt)
            if not chosen:chosen=[tuple(p.coords[np.argmax(dark[p.coords[:,0],p.coords[:,1]])])]
        else: recovered_parent.add(p.label)
        for pt in chosen:
            pid+=1;new_markers[pt]=pid
            seed_kind[pid]='new_center' if rescue else 'original_center'
            parent_counts[pid]=(p.label,len(chosen),rescue)
    # marker-controlled watershed guided by local darkness rather than only EDT
    # is used for rescued connected regions; original EDT watershed retained elsewhere.
    energy=-dark + .12*np.clip(ndi.gaussian_filter(normalize(image),1.3)-normalize(image),-.3,.3)
    refined=segmentation.watershed(energy,new_markers,mask=binary)
    # Each segmentation label is tied to exactly one marker. In unrescued parents
    # use original watershed geometry to avoid changing non-targeted examples.
    mapping={}
    for p in measure.regionprops(refined):
        mark=parent_counts.get(p.label,(0,1,False))
        mapping[p.label]=mark
    for p in measure.regionprops(parents):
        if p.label in recovered_parent:continue
        positions=np.where(parents==p.label)
        # original mask uses independent marker values; remap to v4 ids by nearest
        oldids=np.unique(old[positions]);oldids=oldids[oldids>0]
        if len(oldids)==0:continue
        newids=np.unique(refined[positions]);newids=newids[newids>0]
        # For well-behaved components keep the already verified original geometry.
        if len(newids)!=len(oldids):continue
        # overwrite labels for this parent's pixels with unique marker IDs.
        for oid,nid in zip(oldids,newids):
            refined[(parents==p.label)&(old==oid)]=nid
    return refined,binary,parents,mapping, dark, typical_d


def classify_candidate(stats, nseeds, from_rescue, edge, pixel_prob, typical_d, profile='balanced'):
    """Three levels, separating certain artifacts from reviewable particles.

    'review' is NOT counted as an automatically measured particle.
    """
    d=stats['diameter_px'];circ=stats['circularity'];solid=stats['solidity']
    aspect=stats['aspect_ratio'];c=stats['contrast']; snr=stats['contrast_snr']
    reasons=[]
    if edge:return 'rejected',['image_border']
    if d<4.8:return 'rejected',['too_small']
    if c<.055 or (c<.09 and snr<.75):return 'rejected',['insufficient_contrast']
    if pixel_prob<.42:return 'rejected',['low_model_probability']
    if d>max(55,2.30*typical_d):return 'review',['oversized_object']
    # The older algorithm rejected *all* centers in crowded parents and used
    # shape limits too strictly. Salvage compact units but keep tentative ones.
    clear= (circ>=.52 and solid>=.76 and aspect<=2.1 and c>=.10 and snr>=1.1)
    doubtful=(circ<.40 or solid<.67 or aspect>2.6 or snr<.9 or d>max(33,1.65*typical_d))
    if from_rescue:
        if clear and not doubtful and nseeds<=12:
            return 'review',['resplit_from_dense_parent','verify_separation']
        return 'review',['complex_aggregate']
    if nseeds>=4:
        if clear and not doubtful:return 'review',['multi_particle_contact']
        return 'review',['dense_or_overlapping_cluster']
    if nseeds>=2:
        if clear and not doubtful:return 'accepted_touching',['watershed_contact']
        return 'review',['ambiguous_contact']
    if clear and not doubtful:
        return 'accepted_isolated',[]
    # Relatively irregular but strong real-contrast singlets are allowed to
    # be reviewed, not silently called overlap or automatically discarded.
    if d<27 and snr>=1 and c>=.09:
        return 'review',['irregular_but_contrasting']
    return 'rejected',['unresolved_shape_or_noise']


def run(img_path, outdir, model_path=MODEL, scale_reference=None, probability_cache=None,
        threshold=.48, nm_per_px=None, min_area=22):
    img=read_gray(img_path); norm=normalize(img)
    if probability_cache:
        probability=cv2.imread(str(probability_cache),cv2.IMREAD_GRAYSCALE)
        if probability is None or probability.shape != img.shape:raise ValueError('probability cache must match image')
        probability=probability.astype('float32')/255
    else: probability=predict_probability(model_path,img)
    # OCR explicitly separate from particle detection. Must not silently infer
    # physical units from material name or vendor's expected particle size.
    cal=detect_scale(scale_reference or img_path)
    if scale_reference: cal=transfer_calibration(cal,scale_reference,img_path)
    pxnm=(float(nm_per_px) if nm_per_px is not None else cal.nm_per_px if cal.status=='accepted' else None)
    if pxnm is not None and pxnm<=0:raise ValueError('nm_per_px must be positive')
    forbidden=exclusion_mask(img.shape,cal)
    labels,binary,parents,mapping,dark,typical_d=rescue_split(probability,img,~forbidden,threshold,min_area)
    h,w=img.shape; rows=[]
    colors={'accepted_isolated':(44,208,93),'accepted_touching':(24,213,227),
            'accepted_resolved':(187,89,251),
            'review':(255,172,37),'rejected':(242,58,72)}
    overlay=cv2.cvtColor((norm*255).astype('uint8'),cv2.COLOR_GRAY2RGB)
    for prop in measure.regionprops(labels):
        r0,c0,r1,c1=prop.bbox
        rr0=max(0,r0-11);rr1=min(h,r1+11);cc0=max(0,c0-11);cc1=min(w,c1+11)
        patch=np.s_[rr0:rr1,cc0:cc1]
        m=np.zeros((rr1-rr0,cc1-cc0),bool)
        m[r0-rr0:r1-rr0,c0-cc0:c1-cc0]=prop.image
        if prop.area<min_area: continue
        stat=roi_stats(norm[patch],m,binary[patch])
        stat['x_px']=round(stat['x_px']+cc0,2);stat['y_px']=round(stat['y_px']+rr0,2)
        par, nseed, rescued=mapping.get(prop.label,(0,1,False))
        edge=(r0<=1 or c0<=1 or r1>=h-1 or c1>=w-1 or bool(np.any(forbidden[r0:r1,c0:c1]&prop.image)))
        probscore=float(np.median(probability[r0:r1,c0:c1][prop.image]))
        status,reasons=classify_candidate(stat,nseed,rescued,edge,probscore,typical_d)
        record=dict(id=int(prop.label),status=status,reason=';'.join(reasons),source_parent=int(par),
                    seeds_in_parent=nseed,new_center_rescue=bool(rescued),
                    median_model_probability=round(probscore,3),**stat)
        rows.append(record)
    # Second pass: only promote rescued centers with independently resolved
    # separation in the actual intensity profile (bright inter-center saddle).
    # Closest-neighbor distance is expressed relative to each candidate's diameter.
    if len(rows)>1:
        center=np.asarray([[r['y_px'],r['x_px']] for r in rows],dtype=float)
        distances, neighbors=cKDTree(center).query(center,k=2)
        blurred=ndi.gaussian_filter(norm,1.1)
        def sample(p):
            y=int(np.clip(round(p[0]),0,h-1));x=int(np.clip(round(p[1]),0,w-1))
            return float(blurred[y,x])
        for i,r in enumerate(rows):
            j=int(neighbors[i,1]);nn=float(distances[i,1]);
            relief=sample((center[i]+center[j])*.5)-.5*(sample(center[i])+sample(center[j]))
            r['nearest_center_px']=round(nn,3)
            r['intercenter_brightness_saddle']=round(relief,4)
            eligible=(r['status']=='review' and r['new_center_rescue']
                and r['circularity']>=.80 and r['solidity']>=.89
                and r['aspect_ratio']<=1.4 and r['contrast_snr']>=2.0
                and r['median_model_probability']>=.77
                and nn / max(r['diameter_px'],1) >= .80
                and relief >= .05 and r['diameter_px']<=1.70*typical_d)
            if eligible:
                r['status']='accepted_resolved'
                r['reason']='multi_center_separation_with_bright_saddle'
    else:
        for r in rows:
            r['nearest_center_px']='';r['intercenter_brightness_saddle']=''
    for r in rows:
        if pxnm and r['status'].startswith('accepted'):
            r['diameter_nm']=round(float(r['diameter_px'])*pxnm,3)
        # Store colors only after all decisions, avoiding stale orange contours.
        mask=labels==r['id']
        yx=np.where(mask)
        if not len(yx[0]):continue
        rr0,rr1=max(0,min(yx[0])-2),min(h,max(yx[0])+3)
        cc0,cc1=max(0,min(yx[1])-2),min(w,max(yx[1])+3)
        patch=mask[rr0:rr1,cc0:cc1]
        for cnt in measure.find_contours(patch.astype('float32'),.5):
            points=np.round(cnt[:,::-1]+np.array([cc0,rr0])).astype('int32').reshape(-1,1,2)
            cv2.polylines(overlay,[points],True,colors[r['status']],1,lineType=cv2.LINE_AA)
    path=Path(outdir);path.mkdir(parents=True,exist_ok=True)
    fieldnames=list(dict.fromkeys(k for row in rows for k in row))
    for name,selection in [('all',rows),('accepted',[r for r in rows if r['status'].startswith('accepted')]),('review',[r for r in rows if r['status']=='review'])]:
        with (path/f'particles_{name}.csv').open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=fieldnames);writer.writeheader();writer.writerows(selection)
    cv2.imwrite(str(path/'decision_overlay.png'),cv2.cvtColor(overlay,cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(path/'annotation_exclusion.png'),forbidden.astype('uint8')*255)
    accepted=[r for r in rows if r['status'].startswith('accepted')]
    counts=Counter(r['status'] for r in rows)
    summary=dict(image=Path(img_path).name,model=Path(model_path).name,counts=dict(counts),
                 total_candidates=len(rows),estimated_isolated_diameter_px=round(typical_d,2),accepted=len(accepted),review=int(counts['review']),rejected=int(counts['rejected']),
                 recovered_candidates=sum(r['new_center_rescue'] for r in rows),
                 nm_per_px=pxnm,scale_status=cal.status,
                 median_diameter_nm=float(np.median([r['diameter_nm'] for r in accepted])) if accepted and pxnm else None,
                 median_diameter_px=float(np.median([r['diameter_px'] for r in accepted])) if accepted else None,
                 notes='Selection counts are not recall/precision; review candidates excluded from reported diameters. Weak real training labels include Ag-1, Ag-2, Pt-2.')
    (path/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (path/'calibration.json').write_text(json.dumps(asdict(cal),ensure_ascii=False,indent=2,default=lambda x:x.item() if isinstance(x,np.generic) else str(x)),encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    fig,axs=plt.subplots(1,3,figsize=(14.6,4.9),gridspec_kw={'width_ratios':[1,1,1]})
    axs[0].imshow(norm,cmap='gray',vmin=0,vmax=1);axs[0].axis('off');axs[0].set_title('Original micrograph')
    axs[1].imshow(overlay);axs[1].axis('off');axs[1].set_title(f'Accept {len(accepted)} | review {counts["review"]} | reject {counts["rejected"]}')
    axs[1].legend(handles=[Patch(color=np.array(col)/255,label=name) for name,col in colors.items()],loc='lower left',fontsize=7)
    key='diameter_nm' if pxnm else 'diameter_px'
    ds=[r[key] for r in accepted]
    axs[2].hist(ds,bins=min(22,max(5,int(math.sqrt(len(ds))))) if ds else 5,edgecolor='white')
    axs[2].set_xlabel('Equivalent diameter (nm)' if pxnm else 'Equivalent diameter (px)');axs[2].set_ylabel('Auto-accepted count')
    axs[2].set_title(f'Median {np.median(ds):.2f} '+('nm' if pxnm else 'px') if ds else 'No accepted particles')
    fig.suptitle(f'v4 audit-first / {Path(img_path).name}',fontsize=11)
    fig.tight_layout();fig.savefig(path/'overview.png',dpi=130);plt.close(fig)
    print(json.dumps(summary,ensure_ascii=False));return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--image',required=True);p.add_argument('--out',required=True)
    p.add_argument('--model',default=str(MODEL));p.add_argument('--scale-reference');p.add_argument('--probability-cache');
    p.add_argument('--nm-per-px',type=float);p.add_argument('--threshold',type=float,default=.48)
    a=p.parse_args();run(a.image,a.out,a.model,a.scale_reference,a.probability_cache,a.threshold,a.nm_per_px)
