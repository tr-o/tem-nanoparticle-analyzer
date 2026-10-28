"""v4 regression gates: image-aware splitting, transparent decisions."""
import sys,unittest
from pathlib import Path
import numpy as np
from scipy import ndimage as ndi
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'v4'))
from tem_v4 import rescue_split,classify_candidate

class TestV4(unittest.TestCase):
    def test_one_large_noisy_sphere_is_not_many_particles(self):
        r=np.random.default_rng(11);Y,X=np.mgrid[:150,:150]
        m=(X-75)**2+(Y-75)**2<=22**2
        image=np.clip(.79-.53*ndi.gaussian_filter(m.astype(float),1.6)+r.normal(0,.018,m.shape),0,1).astype('float32')
        prob=ndi.gaussian_filter(m.astype(float),1)*.95
        labels,_,_,parents,_,d=rescue_split(prob,image,np.ones(m.shape,bool),min_area=22)
        self.assertGreater(d,25)
        self.assertLessEqual(len(np.unique(labels))-1,2)
        self.assertFalse(any(entry[2] for entry in parents.values()))

    def test_rejected_at_image_border(self):
        stat=dict(diameter_px=9,circularity=.96,solidity=.97,aspect_ratio=1.1,contrast=.35,contrast_snr=5)
        status,reason=classify_candidate(stat,1,False,True,.95,typical_d=10)
        self.assertEqual(status,'rejected');self.assertEqual(reason,['image_border'])

    def test_unresolved_rescue_moves_to_review(self):
        stat=dict(diameter_px=13,circularity=.59,solidity=.8,aspect_ratio=1.8,contrast=.22,contrast_snr=2.5)
        status,_=classify_candidate(stat,7,True,False,.95,typical_d=8)
        self.assertEqual(status,'review')

if __name__=='__main__':unittest.main()
