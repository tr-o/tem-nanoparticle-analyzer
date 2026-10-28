"""Evidence-based ranking of existing v4 'review' candidates; does not silently approve them.

An independent multi-scale LoG detector provides a second center-position test.
A roundish, high-contrast local region is prioritized for HUMAN review; it is
NOT reclassified as an accepted measurement without confirmation.
"""
import cv2,numpy as np,pandas as pd, argparse, hashlib
from pathlib import Path
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.feature import blob_log

def triage(image_path,candidates_path,out):
    image=cv2.imread(str(image_path),cv2.IMREAD_GRAYSCALE).astype(np.float32)/255.
    x=ndi.gaussian_filter(image,6)-ndi.gaussian_filter(image,1)
    peaks=blob_log(x,min_sigma=1.55,max_sigma=3.8,num_sigma=8,threshold=.026,overlap=.4)
    d=pd.read_csv(candidates_path)
    d['source_image_sha256']=hashlib.sha256(Path(image_path).read_bytes()).hexdigest()
    d['source_image_width_px']=int(image.shape[1])
    d['source_image_height_px']=int(image.shape[0])
    if len(peaks):
        dist,inds=cKDTree(peaks[:,:2]).query(d[['y_px','x_px']].to_numpy(),k=1)
        d['log_center_distance_px']=np.round(dist,3)
        d['independent_log_sigma_px']=np.round(peaks[inds,2],3)
    else:
        d['log_center_distance_px']=np.inf
        d['independent_log_sigma_px']=np.nan
    # Simple conservative ranking; quantities are feature heuristics, not calibrated probabilities.
    d['locally_confirmed_center']=(d.log_center_distance_px<=1.6)
    d['roundish_enough']=(d.solidity>=.86)&(d.circularity>=.66)&(d.aspect_ratio<=1.65)
    d['strong_particle_contrast']=(d.contrast>=.12)&(d.contrast_snr>=1.8)&(d.median_model_probability>=.67)
    d['plausible_size']=(d.diameter_px.between(5.2,11.2))
    evidence=d[['locally_confirmed_center','roundish_enough','strong_particle_contrast','plausible_size']]
    d['independent_evidence_count']=evidence.sum(axis=1)
    # A rejected but independently corroborated center should be offered for manual
    # reconsideration. Do not silently accept it. Border artifacts are excluded.
    d['reconsider_rejected']=(d.status.eq('rejected') & (d.independent_evidence_count>=3) &
      (~d.reason.fillna('').astype(str).str.contains('image_border|too_small',regex=True)))
    # No automatic status changes; just make selection of review crops faster.
    d['review_priority']=np.where(d.status!='review','not_review',np.where(d.independent_evidence_count==4,'high',np.where(d.independent_evidence_count>=2,'medium','low')))
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    d.to_csv(out/'review_triage_all.csv',index=False)
    d[(d.status=='review')|d.reconsider_rejected].sort_values(['reconsider_rejected','independent_evidence_count','contrast_snr'],ascending=[False,False,False]).to_csv(out/'review_queue_sorted.csv',index=False)
    return d

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--image',required=True);p.add_argument('--candidates',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();d=triage(a.image,a.candidates,a.out)
    print(d[d.status=='review'].review_priority.value_counts().to_dict())