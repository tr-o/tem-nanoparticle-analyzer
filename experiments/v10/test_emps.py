import tempfile,unittest
from pathlib import Path
import numpy as np
from PIL import Image
from benchmark_emps import match_instances,watersplit,features,prepare_instances,pixel_score,read_pairs,robust

class EMPSBench(unittest.TestCase):
    def test_instance_matching_preserves_ids(self):
        gt=np.zeros((64,64),np.int32)
        gt[8:22,10:24]=101;gt[34:47,35:48]=400
        pred=np.zeros_like(gt);pred[8:22,10:24]=1;pred[34:47,35:48]=2
        m=match_instances(pred,gt);self.assertEqual(m['tp'],2)
        self.assertEqual(m['fp'],0);self.assertEqual(m['fn'],0)
        self.assertEqual(m['diameter_mae_px'],0)
    def test_sparse_large_integer_ids_do_not_allocate_huge_index(self):
        gt=np.zeros((64,64),np.int32);gt[10:30,10:30]=1_000_000_000
        pr=np.zeros_like(gt);pr[10:30,10:30]=1
        self.assertEqual(match_instances(pr,gt)['tp'],1)
    def test_wrong_location_is_false_positive(self):
        g=np.zeros((64,64),np.int32);g[10:25,10:25]=2
        p=np.zeros_like(g);p[35:50,35:50]=1
        s=match_instances(p,g);self.assertEqual(s['tp'],0)
        self.assertEqual(s['fp'],1)
    def test_robust_normalize_float32_under_numpy2(self):
        a=np.arange(1024,dtype=np.uint16).reshape(32,32)
        x=robust(a);self.assertEqual(x.dtype,np.float32)
        self.assertTrue(np.isfinite(features(x)).all())
    def test_features_shape_and_no_nan(self):
        a=np.ones((64,64),np.float32)/2
        f=features(a);self.assertEqual(f.shape,(64,64,14));self.assertTrue(np.isfinite(f).all())
    def test_instance_mask_image(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'gt.png';a=np.zeros((32,32),np.uint16);a[4:11,6:12]=100;a[17:26,17:22]=200
            Image.fromarray(a).save(p)
            r=prepare_instances(p,(32,32))
            self.assertEqual(set(np.unique(r)),{0,100,200})
    def test_watersplit_empty(self):
        r=watersplit(np.zeros((64,64),bool));self.assertEqual(int(r.sum()),0)
    def test_no_duplicate_train_test_files(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d);(r/'images').mkdir();(r/'segmaps').mkdir()
            for x in ('a','b'):
                Image.fromarray(np.zeros((16,16),np.uint8)).save(r/'images'/f'{x}.png')
                Image.fromarray(np.zeros((16,16),np.uint8)).save(r/'segmaps'/f'{x}.png')
            (r/'train.csv').write_text('a\na\n')
            with self.assertRaises(ValueError):read_pairs(r,'train')

if __name__=='__main__':unittest.main()
