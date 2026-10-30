import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from data_scale_benchmark import unseen_test, SEED,choose_superset_training
class V15Integrity(unittest.TestCase):
    def test_excludes_past_test(self):
        data=[(str(i),'','') for i in range(30)]
        seen={'0','3','7'};selected=unseen_test(data,seen,15)
        self.assertFalse(set(x[0] for x in selected)&seen)
    def test_reproducible_holdout(self):
        sample=[(str(i),'','') for i in range(30)]
        self.assertEqual(unseen_test(sample,{},10),unseen_test(sample,{},10))
    def test_refuses_missing_training(self):
        with self.assertRaisesRegex(ValueError,'Missing v13'):
            choose_superset_training([('a',None,None)],{'missing'},2)
    def test_refuses_too_many(self):
        with self.assertRaises(ValueError):unseen_test([('only','','')],{'only'},1)
if __name__=='__main__':unittest.main()
