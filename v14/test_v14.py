import sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from polarity_benchmark import fresh_test_ids, PREVIOUS_TEST, polarity_probabilities, foreground_polarity

class ProbabilityModel:
    def __init__(self,classes):self.classes_=np.array(classes)
    def predict_proba(self,x):
        y=np.clip(x[:,0],0,1)
        if len(self.classes_)==2:return np.c_[1-y,y]
        return np.c_[.2*np.ones_like(y),.5*(1-y),.3+.5*y]

class Guardrails(unittest.TestCase):
    def test_unseen_ids_only(self):
        fake=[(str(i),'','') for i in range(60)]+[(x,'','') for x in PREVIOUS_TEST]
        a=fresh_test_ids(fake,count=20)
        self.assertEqual(len(a),20)
        self.assertEqual(set(x[0] for x in a)&PREVIOUS_TEST,set())
        self.assertEqual([x[0] for x in a],[x[0] for x in fresh_test_ids(fake,20)])
    def test_refuse_oversampling(self):
        with self.assertRaisesRegex(ValueError,'only'):
            fresh_test_ids([('one','','')],20)
    def test_polarity_inference_symmetry(self):
        x=np.random.default_rng(5).uniform(0,1,(51,69)).astype('float32')
        a,b=polarity_probabilities(ProbabilityModel([False,True]),ProbabilityModel([0,1,2]),x)
        c,d=polarity_probabilities(ProbabilityModel([False,True]),ProbabilityModel([0,1,2]),1-x)
        np.testing.assert_allclose(a,c,rtol=1e-6,atol=1e-6)
        np.testing.assert_allclose(b,d,rtol=1e-6,atol=1e-6)
    def test_polarity_report_only(self):
        lab=np.zeros((30,30),int);lab[5:18,5:18]=1
        bright=np.full(lab.shape,.3);bright[lab>0]=.8
        self.assertEqual(foreground_polarity(bright,lab),'bright')
        self.assertEqual(foreground_polarity(1-bright,lab),'dark')
        self.assertEqual(foreground_polarity(bright*.0+.5,lab),'low_contrast')
    def test_no_gt_leak_from_test_selection(self):
        cases=[('a','/does-not-exist','/does-not-exist'),('b','/does-not-exist','/does-not-exist')]
        self.assertEqual(len(fresh_test_ids(cases,2)),2)
if __name__=='__main__':unittest.main()
