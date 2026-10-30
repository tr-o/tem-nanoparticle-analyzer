#!/usr/bin/env python3
"""Review TEM particle candidates without destroying algorithm decisions.

The original CSV is immutable. Human/assistant decisions are a separate CSV,
and application to a measurement is reproducible and auditable.
The program intentionally never treats the model's review priority as truth.
"""
from __future__ import annotations
import argparse,csv,json,math,os,tempfile,datetime
from pathlib import Path
import pandas as pd
import numpy as np

DECISIONS={'accept','reject','uncertain'}

def empty_decisions() -> pd.DataFrame:
    return pd.DataFrame(columns=['id','decision','operator','comment','recorded_at_utc'])

def load_decisions(path):
    path=Path(path)
    if not path.exists(): return empty_decisions()
    d=pd.read_csv(path,dtype={'id':'int64','decision':'str','operator':'str','comment':'str','recorded_at_utc':'str'}).fillna('')
    if d.id.duplicated().any():raise ValueError('Duplicate candidate id in review decisions')
    if not set(d.decision).issubset(DECISIONS):raise ValueError('Invalid review decision')
    return d

def write_atomic(df,path):
    path=Path(path);path.parent.mkdir(exist_ok=True,parents=True)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',newline='',suffix='.tmp',dir=path.parent,delete=False) as f:
        name=f.name
        df.to_csv(f,index=False)
    os.replace(name,path)

def record_decision(candidates_path,decision_path,id,decision,operator='reviewer',comment=''):
    decision=str(decision).strip().lower()
    if decision not in DECISIONS: raise ValueError(f'Decision must be one of {sorted(DECISIONS)}')
    if not operator.strip():raise ValueError('operator must not be blank')
    d=pd.read_csv(candidates_path)
    if int(id) not in set(d.id):raise ValueError(f'unknown candidate ID: {id}')
    prev=load_decisions(decision_path)
    prev=prev[prev.id!=int(id)]
    new=pd.DataFrame([{'id':int(id),'decision':decision,'operator':operator,
       'comment':comment,'recorded_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}])
    write_atomic(pd.concat([prev,new],ignore_index=True).sort_values('id'),decision_path)

def apply_decisions(candidates_path,decision_path,outdir,nm_per_px=None,require_all_reviewed=False):
    d=pd.read_csv(candidates_path)
    if d.id.duplicated().any():raise ValueError('Original candidate IDs must be unique')
    decisions=load_decisions(decision_path)
    if not set(decisions.id).issubset(set(d.id)):raise ValueError('Decision file has unknown candidate ID')
    d=d.merge(decisions,on='id',how='left',validate='one_to_one')
    d['decision']=d.decision.fillna('')
    d['original_status']=d.status.copy()
    # Distinguish model accept from explicit manual confirmation.
    d['final_status']=np.select(
      [d.decision.eq('accept'),d.decision.eq('reject'),d.decision.eq('uncertain')],
      ['manually_accepted','manually_rejected','pending_review'],
      default='')
    d.loc[d.final_status.eq(''),'final_status']=d.loc[d.final_status.eq(''),'original_status'].map(
      lambda s:'model_accepted_unconfirmed' if str(s).startswith('accepted') else ('model_rejected_unconfirmed' if s=='rejected' else 'pending_review'))
    if require_all_reviewed and d.final_status.eq('pending_review').any():
        raise ValueError('Unreviewed candidates remain')
    # Do not confuse automated acceptance with manually confirmed labels.
    auto=d[d.final_status.eq('model_accepted_unconfirmed')]
    confirmed=d[d.final_status.eq('manually_accepted')]
    all_accepted=d[d.final_status.isin(['manually_accepted','model_accepted_unconfirmed'])]
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    d.to_csv(out/'candidates_with_audit.csv',index=False)
    confirmed.to_csv(out/'particles_manually_confirmed.csv',index=False)
    all_accepted.to_csv(out/'particles_analysis_accepted.csv',index=False)
    if nm_per_px is not None:
        if float(nm_per_px)<=0:raise ValueError('nm_per_px must be > 0')
        d['diameter_nm']=d.diameter_px*float(nm_per_px)
        all_accepted=all_accepted.copy();all_accepted['diameter_nm']=all_accepted.diameter_px*float(nm_per_px)
        d.to_csv(out/'candidates_with_audit.csv',index=False)
        all_accepted.to_csv(out/'particles_analysis_accepted.csv',index=False)
    summary={'total_candidates':len(d),'confirmed_accept':len(confirmed),'model_accepted_unconfirmed':len(auto),
       'pending_review':int(d.final_status.eq('pending_review').sum()),
       'manual_reject':int(d.final_status.eq('manually_rejected').sum()),
       'model_rejected_unconfirmed':int(d.final_status.eq('model_rejected_unconfirmed').sum()),
       'analysis_accepted_total':len(all_accepted),
       'note':'Confirmed means reviewer clicked accept, not expert-validated ground truth. Model-accepted are not yet manually verified.'}
    (out/'review_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf8')
    return summary

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('record');a.add_argument('--candidates',required=True);a.add_argument('--decisions',required=True)
    a.add_argument('--id',type=int,required=True);a.add_argument('--decision',choices=sorted(DECISIONS),required=True)
    a.add_argument('--operator',default='reviewer');a.add_argument('--comment',default='')
    a=sub.add_parser('apply');a.add_argument('--candidates',required=True);a.add_argument('--decisions',required=True)
    a.add_argument('--out',required=True);a.add_argument('--nm-per-px',type=float)
    a.add_argument('--require-all-reviewed',action='store_true')
    a=p.parse_args()
    if a.cmd=='record':record_decision(a.candidates,a.decisions,a.id,a.decision,a.operator,a.comment)
    else:print(json.dumps(apply_decisions(a.candidates,a.decisions,a.out,a.nm_per_px,a.require_all_reviewed),indent=2))
if __name__=='__main__':main()