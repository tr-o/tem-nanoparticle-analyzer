import unittest,numpy as np
from center_model import centroid_pixels,seeded_watershed,CENTER_GRID
class TestCenter(unittest.TestCase):
    def test_centers_per_instance_not_foreground_mask(self):
        x=np.zeros((96,96),np.int32);x[15:37,15:37]=17;x[58:82,58:82]=999
        c=centroid_pixels(x)
        self.assertTrue(c[25,25]);self.assertTrue(c[69,69]);self.assertLess(int(c.sum()),30)
    def test_no_unlabeled_particle(self):
        self.assertFalse(seeded_watershed(np.zeros((64,64),bool),np.zeros((64,64)),.3,5).any())
    def test_two_distinct_center_peaks(self):
        mask=np.zeros((90,90),bool);mask[20:70,20:70]=True
        p=np.zeros((90,90),np.float32)
        p[30,35]=1;p[57,60]=1
        result=seeded_watershed(mask,p,.1,7)
        self.assertEqual(len(np.unique(result[result>0])),2)
    def test_grid(self):
        self.assertEqual(len(CENTER_GRID),16)
        self.assertIn((.35,6),CENTER_GRID)
if __name__=='__main__':unittest.main()
