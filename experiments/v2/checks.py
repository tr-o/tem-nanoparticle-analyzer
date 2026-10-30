"""Lightweight regression checks for the conservative TEM v2 pipeline."""
import json,sys
from pathlib import Path
import numpy as np
from scipy import ndimage as ndi
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tem_analyzer.legacy_rf import read_gray,predict_probability,read_mask
from v2.tem_v2 import metadata_exclusion,split_candidates
from sklearn.metrics import f1_score,jaccard_score
import warnings

for size in ((250,250),(500,500),(320,320)):
    ignored=metadata_exclusion(size)
    assert ignored.shape==size
    assert ignored[-1,-1] and not ignored[0,0]
    assert .025<ignored.mean()<.045
# Touching spheres, modeled in a probability map with two local maxima.
y,x=np.mgrid[:120,:150]
a=np.exp(-((x-60)**2+(y-60)**2)/(2*10**2))
b=np.exp(-((x-76)**2+(y-60)**2)/(2*10**2))
p=np.maximum(a,b).astype('float32')
labels,binary,_,_=split_candidates(p,np.ones(p.shape,bool),min_area=30,threshold=.28,min_distance=6)
assert len(set(labels[labels>0]))>=2,'two touching circles should be separable'
# No ground truth evaluation of natural TEM: synthetic four test images are separate.
from v2.tem_v2 import MODEL
v2=[];v1=[]
for image in sorted((ROOT/'demo_data/test/images').glob('*.png')):
    mask=read_mask(ROOT/'demo_data/test/masks'/image.name)
    img=read_gray(image)
    for path,arr in [(MODEL,v2),(ROOT/'models/synthetic_rf.joblib',v1)]:
        p=predict_probability(path,img)
        pred=(p>.5)
        arr.append({'image':image.name,'dice':float(f1_score(mask.ravel(),pred.ravel())),'iou':float(jaccard_score(mask.ravel(),pred.ravel()))})
summary={'v1_synthetic_test_dice_mean':float(np.mean([x['dice'] for x in v1])),
         'v2_synthetic_test_dice_mean':float(np.mean([x['dice'] for x in v2])),
         'v1_synthetic_test_iou_mean':float(np.mean([x['iou'] for x in v1])),
         'v2_synthetic_test_iou_mean':float(np.mean([x['iou'] for x in v2])),
         'synthetic_test_images':4,'separate_real_gt':0,
         'touching_circles_split_test':'PASS','metadata_roi_test':'PASS'}
(ROOT/'experiments/v2/checks.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
