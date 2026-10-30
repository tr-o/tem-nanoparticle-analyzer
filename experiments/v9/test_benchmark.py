import unittest
import tempfile
import numpy as np
import h5py
from pathlib import Path
from real_gt_benchmark import discover,read_sample,metrics,gt_mask,v9_mask

class BenchmarkSafety(unittest.TestCase):
    def test_scores_perfect_match(self):
        a=np.zeros((64,64),bool);a[20:34,20:34]=True
        self.assertEqual(metrics(a,a)["dice"],1.)
        self.assertEqual(metrics(a,a)["iou"],1.)
    def test_empty_both_counts_perfect(self):
        a=np.zeros((64,64),bool)
        self.assertEqual(metrics(a,a)["dice"],1.)
    def test_disallow_nonnumeric_gt_encoding(self):
        with self.assertRaises(ValueError):
            gt_mask(np.linspace(0,1,4096).reshape(64,64))
    def test_integer_instance_mask_to_binary(self):
        a=np.array([[0,1],[2,0]],dtype=np.uint8)
        self.assertEqual(int(gt_mask(a).sum()),2)
    def test_h5_nonempty_dataset(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"test.h5"
            with h5py.File(p,"w") as f:f.create_dataset("images",data=np.ones((3,64,64),np.uint16))
            with h5py.File(p) as f:
                k,shape=discover(f);self.assertEqual(k,"images")
                self.assertEqual(read_sample(f[k],2).shape,(64,64))
    def test_constant_image_not_particle(self):
        a=np.full((128,128),.5,dtype=np.float32)
        self.assertFalse(v9_mask(a).any())

if __name__=="__main__": unittest.main()
