import unittest
from v14_bootstrap_uncertainty import bootstrap

class TestBootstrap(unittest.TestCase):
    def test_identical_models_zero(self):
        x=[{'v13':{'tp':4,'fp':2,'fn':2},'v14':{'tp':4,'fp':2,'fn':2}} for _ in range(5)]
        y=bootstrap(x,iterations=100,seed=7)
        self.assertEqual(y['observed_delta_percentage_points'],0)
        self.assertEqual(y['interval_95_percentile_pp'],[0.0,0.0])
    def test_no_fake_precision_on_one_image(self):
        x=[{'v13':{'tp':1,'fp':0,'fn':0},'v14':{'tp':1,'fp':0,'fn':0}}]
        with self.assertRaises(ValueError):bootstrap(x)
if __name__=='__main__':unittest.main()
