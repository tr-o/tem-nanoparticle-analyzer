"""Conservative HRTEM crystalline nanoparticle candidate detector.

Not interchangeable with the bright-field Random Forest. Detects spatially
coherent lattice texture + locally darker particle envelopes; no expert-GT
performance claim. Empirical thresholds are explicit and kept in metadata.
"""
from __future__ import annotations
import argparse,csv,json,math,sys,hashlib
from pathlib import Path
import cv2
import numpy as np
from scipy import ndimage as ndi
from skimage import measure,morphology,feature,segmentation
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0,str(Path(__file__).resolve().parent))
from dm_io import load_dm,robust_preview,resize_scale,area_diameter_nm


def gabor_coherence(im):
    # Local periodic contrast; a crystalline particle has a dominant orientation
    # over many pixels, while amorphous support noise is approximately isotropic.
    val=[]
    for wavelength in (3.8,5.4,7.2):
        for angle in (0.,np.pi/4,np.pi/2,3*np.pi/4):
            ker=cv2.getGaborKernel((23,23),3.2,angle,wavelength,0.75,0,cv2.CV_32F)
            ker2=cv2.getGaborKernel((23,23),3.2,angle,wavelength,0.75,np.pi/2,cv2.CV_32F)
            # zero-sum prevents background brightness from appearing as texture
            ker-=ker.mean();ker2-=ker2.mean()
            a=cv2.filter2D(im,-1,ker)
            b=cv2.filter2D(im,-1,ker2)
            power=ndi.gaussian_filter(a*a+b*b,3.0)
            val.append(power)
    v=np.stack(val)
    # winner-takes-orientation score normalized to image-global robust scale
    sorted_power=np.sort(v,axis=0)
    lead=np.mean(sorted_power[-2:],axis=0)
    typical=np.median(sorted_power,axis=0)
    coh=np.maximum(lead-typical,0)
    upper=max(float(np.percentile(coh,99)),1e-8)
    return np.clip(coh/upper,0,1)


def infer_hrtem(path,outdir,dataset_index=0,max_side=768,min_diameter_nm=1.0,
                dark_threshold=.025,texture_threshold=.12):
    raw,meta=load_dm(path,dataset_index)
    x=robust_preview(raw)
    old=x.shape
    if max(x.shape)>max_side:
        ratio=max_side/max(x.shape)
        shape=tuple(int(round(v*ratio)) for v in x.shape)
        x=cv2.resize(x,shape[::-1],interpolation=cv2.INTER_AREA)
    meta=resize_scale(meta,old,x.shape)
    sy=meta['y_nm_per_px'];sx=meta['x_nm_per_px']
    if sx is None or sy is None:raise ValueError('HRTEM texture physical threshold requires valid DM spatial calibration')
    pixel_nm=math.sqrt(sx*sy)
    size_thresh_px=max(6.,min_diameter_nm/pixel_nm)
    area_thresh=math.pi*(size_thresh_px/2)**2
    # Smooth envelope: negative intensity contrast against a broadly varying local background.
    mid=ndi.gaussian_filter(x,4.2)
    bg=ndi.gaussian_filter(x,28.)
    dark=np.maximum(bg-mid,0)
    coherent=gabor_coherence(x)
    # Mostly use local darkness, require local periodicity from Gabor bank.
    mask=(dark>dark_threshold)&(coherent>texture_threshold)
    mask=ndi.binary_closing(mask,iterations=4)
    mask=ndi.binary_fill_holes(mask)
    mask=morphology.remove_small_objects(mask,min_size=max(16,int(area_thresh*.42)))
    # Separated candidate centers from darkness envelope, not raw pixel minima.
    centerfield=ndi.gaussian_filter(dark*coherent,5)
    valid=mask.astype('uint8')
    peaks=feature.peak_local_max(centerfield,min_distance=max(8,int(size_thresh_px*.68)),
               threshold_abs=.006,labels=valid,exclude_border=False)
    markers=np.zeros(x.shape,np.int32)
    for i,(y,xp) in enumerate(peaks,1):markers[y,xp]=i
    if not len(peaks):
        labels=measure.label(mask)
    else:
        labels=segmentation.watershed(-ndi.gaussian_filter(dark,2),markers,mask=mask)
    display=cv2.cvtColor(np.uint8(x*255),cv2.COLOR_GRAY2RGB)
    rows=[]
    for p in measure.regionprops(labels):
        if p.area<10:continue
        minr,minc,maxr,maxc=p.bbox
        crop=labels[minr:maxr,minc:maxc]==p.label
        equiv=math.sqrt(4*p.area/math.pi)
        c=4*math.pi*p.area/max(p.perimeter_crofton**2,1)
        sol=p.solidity
        dnm=area_diameter_nm(p.area,sx,sy)
        peak=float(np.max(centerfield[p.coords[:,0],p.coords[:,1]]))
        # Accept only plausible coherent compact particles above explicit size floor.
        if minr==0 or minc==0 or maxr==x.shape[0] or maxc==x.shape[1]:
            status='rejected';reason='image_edge'
        elif dnm<min_diameter_nm:
            status='rejected';reason='below_method_size_floor'
        elif c<.38 or sol<.66:
            status='review';reason='overlap_or_irregular'
        elif peak<.009:
            status='review';reason='low_crystallinity_evidence'
        else:
            status='accepted';reason='coherent_lattice_candidate'
        row={'id':int(p.label),'x_px':round(p.centroid[1],2),'y_px':round(p.centroid[0],2),
             'diameter_nm':round(dnm,3),'area_px2':int(p.area),
             'circularity':round(c,3),'solidity':round(sol,3),'status':status,'reason':reason,
             'texture_peak':round(peak,4)}
        rows.append(row)
        color={'accepted':(50,230,80),'review':(255,170,35),'rejected':(239,62,70)}[status]
        contours,_=cv2.findContours(crop.astype('uint8'),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for ct in contours:
            ct=ct+np.array([[[minc,minr]]]);cv2.polylines(display,[ct],True,color,1)
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    cv2.imwrite(str(out/'overlay.png'),cv2.cvtColor(display,cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(out/'texture.png'),np.uint8(255*coherent))
    cv2.imwrite(str(out/'darkness.png'),np.uint8(255*np.clip(dark/max(float(np.percentile(dark,99)),1e-6),0,1)))
    cv2.imwrite(str(out/'raw_preview.png'),np.uint8(x*255))
    with (out/'particles.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['id','x_px','y_px','diameter_nm','area_px2','circularity','solidity','status','reason','texture_peak']);writer.writeheader();writer.writerows(rows)
    good=[r['diameter_nm'] for r in rows if r['status']=='accepted']
    stat={kind:sum(r['status']==kind for r in rows) for kind in ['accepted','review','rejected']}
    stat.update({'file':Path(path).name,'source_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                 'dataset_index':dataset_index,'shape':list(x.shape),'x_nm_per_px':sx,'y_nm_per_px':sy,
                 'median_diameter_nm':float(np.median(good)) if good else None,
                 'method':'HRTEM crystal texture + dark envelope: exploratory, no expert GT',
                 'params':{'min_diameter_nm':min_diameter_nm,'dark_threshold':dark_threshold,'texture_threshold':texture_threshold}})
    (out/'summary.json').write_text(json.dumps(stat,indent=2))
    fig,axs=plt.subplots(1,4,figsize=(16.2,4.4))
    axs[0].imshow(x,cmap='gray');axs[0].set_title('Original DM3 pixels')
    axs[1].imshow(coherent,cmap='gray');axs[1].set_title('Crystalline texture evidence')
    axs[2].imshow(display);axs[2].set_title('Candidate segmentation '+str(stat['accepted']))
    axs[3].hist(good,bins=min(15,max(5,int(np.sqrt(len(good))))) if good else 5,edgecolor='white');axs[3].set_title('Provisional size distribution');axs[3].set_xlabel('Equivalent diameter, nm')
    for a in axs[:3]:a.axis('off')
    fig.tight_layout();fig.savefig(out/'overview.jpg',dpi=125);plt.close(fig)
    return stat

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--image',required=True);p.add_argument('--output',required=True)
    p.add_argument('--dataset-index',type=int,default=0);p.add_argument('--max-side',type=int,default=768)
    p.add_argument('--min-diameter-nm',type=float,default=1.0)
    p.add_argument('--dark-threshold',type=float,default=.025);p.add_argument('--texture-threshold',type=float,default=.12)
    a=p.parse_args();print(json.dumps(infer_hrtem(a.image,a.output,a.dataset_index,a.max_side,a.min_diameter_nm,a.dark_threshold,a.texture_threshold),indent=2))
