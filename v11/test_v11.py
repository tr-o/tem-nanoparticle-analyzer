import unittest
import numpy as np
from tune_instances import f1,mask_at,PARAMS

class TestTune(unittest.TestCase):
    def test_f1(self):
        self.assertAlmostEqual(f1(6,2,4),2*6/(12+2+4))
        self.assertEqual(f1(0,0,0),0)
    def test_mask_threshold(self):
        x=np.zeros((32,32),np.float32);x[8:20,8:20]=.55
        self.assertTrue(mask_at(x,.52)[12,12])
        self.assertFalse(mask_at(x,.60).any())
    def test_grid_frozen_independent_of_gt(self):
        self.assertIn((.52,9),PARAMS)
        self.assertIn((.4,3),PARAMS)
        self.assertEqual(len(PARAMS),20)

if __name__=='__main__':unittest.main()
