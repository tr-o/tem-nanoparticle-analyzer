import unittest
import numpy as np
from boundary_model import boundary_targets,split_by_border,metrics_sum

class TestBorder(unittest.TestCase):
 def test_true_label_interfaces_are_boundary(self):
  x=np.zeros((32,32),np.int32);x[5:25,3:15]=1;x[5:25,15:27]=2
  t=boundary_targets(x)
  self.assertEqual(t[12,14],2);self.assertEqual(t[12,15],2)
  self.assertEqual(t[12,7],1);self.assertEqual(t[0,0],0)
 def test_two_separated_cores_get_two_ids(self):
  m=np.zeros((40,50),bool);m[9:31,6:44]=True
  b=np.ones(m.shape,np.float32)
  b[13:27,9:22]=0.1;b[13:27,28:41]=0.1
  labels=split_by_border(m,b,threshold=.3,min_seed_area=20)
  self.assertEqual(len(np.unique(labels[labels>0])),2)
 def test_background_only(self):
  self.assertFalse(split_by_border(np.zeros((20,20),bool),np.zeros((20,20),np.float32)).any())
 def test_geometry_mismatch_raises(self):
  with self.assertRaises(ValueError):split_by_border(np.ones((20,20),bool),np.ones((18,20),np.float32))
 def test_f1_aggregation(self):
  x=metrics_sum([dict(tp=5,fp=3,fn=1,precision=5/8,recall=5/6)])
  self.assertAlmostEqual(x['micro_f1'],10/14)

if __name__=='__main__':unittest.main()
