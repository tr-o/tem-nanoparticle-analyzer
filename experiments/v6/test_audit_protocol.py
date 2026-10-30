import json,sys,tempfile,unittest
from pathlib import Path
import pandas as pd
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).parent))
from audit_protocol import prepare,add_decision,evaluate,gallery,export_verified_crops

class TestAudit(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name)
        a=np.full((96,96),185,np.uint8);a[35:41,31:37]=45
        self.image=self.p/'tem.png';Image.fromarray(a).save(self.image)
        rows=[];i=0
        for st,pri in [('accepted_isolated','not_review'),('accepted_resolved','not_review'),
                       ('review','high'),('review','medium'),('review','low'),('rejected','not_review')]:
            for j in range(4):
                i+=1;rows.append(dict(id=i,status=st,review_priority=pri,x_px=8+(i%8)*9,
                  y_px=9+(i//8)*13,diameter_px=7.4))
        self.candidates=self.p/'candidates.csv';pd.DataFrame(rows).to_csv(self.candidates,index=False)
        self.queue=self.p/'queue';self.events=self.p/'events.jsonl'
        self.d,self.m=prepare(self.image,self.candidates,self.queue,per_stratum=3,seed=7,exclude_ids={1,5})
    def tearDown(self):self.tmp.cleanup()
    def test_sampling_reproducible_blinded_nonoverlap(self):
        self.assertEqual(len(self.d),18)
        self.assertTrue(1 not in set(self.d.id) and 5 not in set(self.d.id))
        self.assertEqual(set(self.m['stratum_sampled'].values()),{3})
        columns=pd.read_csv(self.queue/'audit_blind.csv').columns
        self.assertNotIn('status',columns);self.assertNotIn('sample_stratum',columns)
        self.assertEqual(list(self.d.id),list(prepare(self.image,self.candidates,self.p/'repeat',3,7,{1,5})[0].id))
        gallery(self.image,self.queue/'audit_blind.csv',self.p/'gallery.jpg',self.queue/'audit_manifest.json')
        self.assertTrue((self.p/'gallery.jpg').exists())
    def test_no_premature_accuracy_and_consensus(self):
        r=self.d.iloc[0]
        a=evaluate(self.queue/'audit_manifest.json',self.queue/'audit_private.csv',self.events,self.p/'out')
        self.assertFalse(a['eligible_population_estimation_allowed'])
        add_decision(self.queue/'audit_manifest.json',self.queue/'audit_private.csv',self.events,r.blind_id,'r1','single')
        add_decision(self.queue/'audit_manifest.json',self.queue/'audit_private.csv',self.events,r.blind_id,'r2','background')
        b=evaluate(self.queue/'audit_manifest.json',self.queue/'audit_private.csv',self.events,self.p/'out')
        self.assertEqual(b['disagreements'],1)
        with self.assertRaises(ValueError):
            add_decision(self.queue/'audit_manifest.json',self.queue/'audit_private.csv',self.events,r.blind_id,'r1','single')
    def test_conflict_adjudication(self):
        r=self.d.iloc[1];m=self.queue/'audit_manifest.json';p=self.queue/'audit_private.csv'
        add_decision(m,p,self.events,r.blind_id,'expert_a','single')
        add_decision(m,p,self.events,r.blind_id,'expert_b','background')
        with self.assertRaisesRegex(ValueError,'requires conflicting'):
            add_decision(m,p,self.events,self.d.iloc[0].blind_id,'chief','single',role='adjudicator')
        add_decision(m,p,self.events,r.blind_id,'chief','single',role='adjudicator')
        result=evaluate(m,p,self.events,self.p/'adjudicated')
        self.assertEqual(result['adjudicated'],1)
    def test_binding_prevents_cross_image_and_forged_csv(self):
        manifest=self.queue/'audit_manifest.json';private=self.queue/'audit_private.csv'
        forged=pd.read_csv(private);forged.loc[0,'x_px']+=5;forged.to_csv(private,index=False)
        with self.assertRaisesRegex(ValueError,'modified'):
            add_decision(manifest,private,self.events,self.d.iloc[0].blind_id,'reviewer','single')
    def test_verified_export_requires_consensus(self):
        r=self.d.iloc[0];man=self.queue/'audit_manifest.json';private=self.queue/'audit_private.csv'
        add_decision(man,self.queue/'audit_blind.csv',self.events,r.blind_id,'reviewer1','single')
        summary=evaluate(man,private,self.events,self.p/'half')
        self.assertEqual(export_verified_crops(self.image,man,private,self.p/'half/review_consensus.csv',self.p/'export'),0)
        add_decision(man,self.queue/'audit_blind.csv',self.events,r.blind_id,'reviewer2','single')
        evaluate(man,private,self.events,self.p/'full')
        self.assertEqual(export_verified_crops(self.image,man,private,self.p/'full/review_consensus.csv',self.p/'export'),1)
        self.assertTrue((self.p/'export/single'/f'{r.blind_id}.png').exists())
    def test_full_agreement_eligible_estimate(self):
        for _,r in self.d.iterrows():
            label='single' if r.sample_stratum.startswith('accepted') else 'background'
            for reviewer in ('expert_a','expert_b'):
                add_decision(self.queue/'audit_manifest.json',self.queue/'audit_private.csv',self.events,r.blind_id,reviewer,label)
        a=evaluate(self.queue/'audit_manifest.json',self.queue/'audit_private.csv',self.events,self.p/'out')
        self.assertTrue(a['eligible_population_estimation_allowed']);self.assertEqual(a['consensus'],18)
        self.assertEqual(a['estimated_candidate_usable_fraction'],6/22)
        self.assertTrue((self.p/'out/stratum_estimates.csv').exists())
if __name__=='__main__':unittest.main()
