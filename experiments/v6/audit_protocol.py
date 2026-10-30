#!/usr/bin/env python3
"""TEM v6: independent blinded stratified audit with provenance and consensus.

Never substitutes model predictions for manual ground truth.  An audit estimates
candidate-level usability, not the detection recall of particles never detected.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, datetime, math, tempfile, os
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

CATEGORIES = ('single', 'touching_separable', 'overlap', 'background', 'uncertain')
STRATA = ('accepted_isolated', 'accepted_split', 'review_high', 'review_medium', 'review_low', 'rejected')
POSITIVE = ('single', 'touching_separable')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def atomic_text(path, text):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd, name=tempfile.mkstemp(dir=path.parent,suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f:f.write(text)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def stratum(row):
    st=str(row['status'])
    if st=='accepted_isolated':return 'accepted_isolated'
    if st.startswith('accepted'):return 'accepted_split'
    if st=='rejected':return 'rejected'
    priority=str(row['review_priority'])
    if st=='review' and priority in ('high','medium','low'):return 'review_'+priority
    raise ValueError('Unknown status/priority combination: '+st+'/'+priority)

def prepare(image_path,candidates_path,outdir,per_stratum=10,seed=20261029,exclude_ids=()):
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    d=pd.read_csv(candidates_path)
    required=['id','status','review_priority','x_px','y_px','diameter_px']
    if any(k not in d for k in required):raise ValueError('Missing fields: '+','.join(x for x in required if x not in d))
    if d['id'].duplicated().any():raise ValueError('Duplicate candidate IDs')
    if d['id'].isna().any():raise ValueError('Missing candidate IDs')
    for field in ('x_px','y_px','diameter_px'):
        if not np.isfinite(pd.to_numeric(d[field],errors='coerce')).all():raise ValueError('Non-finite coordinates/sizes')
    image=Image.open(image_path).convert('L');width,height=image.size
    if not ((d.x_px>=0)&(d.x_px<width)&(d.y_px>=0)&(d.y_px<height)).all():
        raise ValueError('Candidate coordinates outside image; likely wrong image')
    if 'source_image_sha256' in d:
        hashes=set(d.source_image_sha256.astype(str))
        if len(hashes)!=1 or sha(image_path) not in hashes:raise ValueError('Candidate CSV image hash does not match input')
    d['stratum']=d.apply(stratum,axis=1)
    counts=d.groupby('stratum').size().to_dict()
    excluded=set(int(x) for x in exclude_ids)
    possible=d[~d.id.isin(excluded)].copy()
    rng=np.random.default_rng(seed)
    selected=[]
    for grp in STRATA:
        sub=possible[possible.stratum==grp].sort_values('id')
        n=min(per_stratum,len(sub))
        if n:
            idx=rng.choice(len(sub),size=n,replace=False)
            chosen=sub.iloc[np.sort(idx)].copy()
            chosen['sample_stratum']=grp
            chosen['eligible_population_count']=int(len(sub))
            chosen['inclusion_probability']=n/len(sub)
            selected.append(chosen)
    sampled=pd.concat(selected,ignore_index=True)
    sampled=sampled.sample(frac=1,random_state=seed).reset_index(drop=True)
    img_hash=sha(image_path);csv_hash=sha(candidates_path)
    manifest={'version':6,'image_sha256':img_hash,'image_size_px':[width,height],
              'candidate_csv_sha256':csv_hash,'sampling_seed':seed,'per_stratum_target':per_stratum,
              'excluded_prior_pilot_ids':sorted(excluded),'total_candidates':len(d),
              'stratum_population':{k:int(counts.get(k,0)) for k in STRATA},
              'stratum_eligible':{k:int(sum(possible.stratum==k)) for k in STRATA},
              'stratum_sampled':{k:int(sum(sampled.sample_stratum==k)) for k in STRATA},
              'sample_count':len(sampled),
              'note':'Sampling excludes previously examined pilot IDs. Estimates describe the remaining eligible candidate population; not true particle recall.'}
    sampled['audit_key']=[hashlib.sha256(f'{img_hash}:{csv_hash}:{seed}:{int(i)}'.encode()).hexdigest()[:16] for i in sampled.id]
    sampled['blind_id']=[f'A{i:03d}' for i in range(1,len(sampled)+1)]
    manifest['queue_sha256']=hashlib.sha256('\n'.join(sampled['audit_key']).encode()).hexdigest()
    sampled.to_csv(out/'audit_private.csv',index=False)
    # Intentionally hide all model labels, source status, reasons and evidence scores.
    sampled[['blind_id','audit_key','id','x_px','y_px','diameter_px']].to_csv(out/'audit_blind.csv',index=False)
    manifest['private_csv_sha256']=sha(out/'audit_private.csv')
    manifest['blind_csv_sha256']=sha(out/'audit_blind.csv')
    atomic_text(out/'audit_manifest.json',json.dumps(manifest,indent=2,ensure_ascii=False))
    return sampled,manifest

def add_decision(manifest_path,private_path,events_path,blind_id,reviewer,label,note='',manual_diameter_px=None,role='reviewer'):
    label=str(label).strip().lower()
    if label not in CATEGORIES:raise ValueError('Invalid label')
    reviewer=str(reviewer).strip()
    if role not in ('reviewer','adjudicator'):raise ValueError('Unknown review role')
    if not reviewer:raise ValueError('Reviewer ID required')
    m=json.loads(Path(manifest_path).read_text())
    if sha(private_path) not in (m['private_csv_sha256'],m['blind_csv_sha256']):
        raise ValueError('Queue file modified since audit preparation')
    p=pd.read_csv(private_path,dtype={'blind_id':str,'audit_key':str})
    if m['queue_sha256']!=hashlib.sha256('\n'.join(p.audit_key).encode()).hexdigest():raise ValueError('Queue hash mismatch')
    target=p[p.blind_id==blind_id]
    if len(target)!=1:raise ValueError('Unknown blind_id')
    if manual_diameter_px is not None:
        manual_diameter_px=float(manual_diameter_px)
        if not 0 < manual_diameter_px < 10000:raise ValueError('Invalid manual diameter')
    e={'audit_key':str(target.iloc[0].audit_key),'blind_id':blind_id,'reviewer':reviewer,'role':role,'label':label,
       'manual_diameter_px':manual_diameter_px,'note':note,'image_sha256':m['image_sha256'],
       'candidate_csv_sha256':m['candidate_csv_sha256'],'queue_sha256':m['queue_sha256'],
       'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    path=Path(events_path);path.parent.mkdir(parents=True,exist_ok=True)
    # Fail instead of silently overwriting a decision by the same reviewer.
    if path.exists():
        for prev in path.read_text().splitlines():
            if not prev.strip():continue
            j=json.loads(prev)
            if j['audit_key']==e['audit_key'] and j['reviewer']==reviewer:
                raise ValueError('Reviewer already decided this candidate; preserve append-only audit log')
            for field in ('image_sha256','candidate_csv_sha256','queue_sha256'):
                if j[field]!=e[field]:raise ValueError('Provenance mismatch; do not mix datasets')
    if role=='adjudicator':
        prior=[json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []
        previous=[q for q in prior if q['audit_key']==e['audit_key'] and q.get('role','reviewer')=='reviewer']
        if len(set(q['reviewer'] for q in previous))<2 or len(set(q['label'] for q in previous))<2:
            raise ValueError('Adjudication requires conflicting independent reviews first')
    with path.open('a',encoding='utf8') as f:f.write(json.dumps(e,ensure_ascii=False)+'\n')
    return e

def evaluate(manifest_path,private_path,events_path,outdir):
    m=json.loads(Path(manifest_path).read_text())
    if sha(private_path)!=m['private_csv_sha256']:raise ValueError('Private queue file modified since audit preparation')
    d=pd.read_csv(private_path,dtype={'blind_id':str,'audit_key':str})
    if m['queue_sha256']!=hashlib.sha256('\n'.join(d.audit_key).encode()).hexdigest():raise ValueError('Queue hash mismatch')
    p=Path(events_path)
    events=[] if not p.exists() else [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    allowed=set(d.audit_key); seen=set()
    for e in events:
        if e['audit_key'] not in allowed:raise ValueError('Event for unknown candidate')
        for k in ('image_sha256','candidate_csv_sha256','queue_sha256'):
            if e[k]!=m[k]:raise ValueError('Event provenance does not match locked audit')
        if e['label'] not in CATEGORIES:raise ValueError('Invalid event label')
        key=(e['audit_key'],e['reviewer'])
        if key in seen:raise ValueError('Duplicate reviewer decision')
        seen.add(key)
    labels={}
    for e in events:labels.setdefault(e['audit_key'],[]).append(e)
    df=d.copy();out_status=[];pair_label=[];nreviewers=[];manual_diameter=[]
    for _,row in d.iterrows():
        arr=labels.get(row.audit_key,[])
        ordinary=[e for e in arr if e.get('role','reviewer')=='reviewer']
        adjudicators=[e for e in arr if e.get('role','reviewer')=='adjudicator']
        # Require two independent named reviewers, with exact agreement. Divergences
        # are never resolved by averaging them.
        uniq=set(e['reviewer'] for e in arr)
        nreviewers.append(len(uniq))
        if len(set(e['reviewer'] for e in ordinary))<2:
            state='awaiting_second_reviewer' if len(ordinary)==1 else 'not_reviewed';label=''
        elif len(set(e['label'] for e in ordinary))==1:
            state='consensus';label=ordinary[0]['label']
        elif len(adjudicators)==1:
            state='consensus_adjudicated';label=adjudicators[0]['label']
        else:state='disagreement_adjudication_required';label=''
        if label=='uncertain':state='consensus_uncertain'
        ds=[float(e['manual_diameter_px']) for e in arr if e.get('manual_diameter_px') is not None]
        manual_diameter.append(float(np.median(ds)) if state.startswith('consensus') and len(ds)>=2 and label in POSITIVE else np.nan)
        out_status.append(state);pair_label.append(label)
    df['audit_state']=out_status;df['consensus_label']=pair_label;df['reviewer_count']=nreviewers
    df['manual_diameter_px_consensus']=manual_diameter
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    df.to_csv(out/'review_consensus.csv',index=False)
    metrics={'audited_candidates':len(df),'events':len(events),'with_two_reviewers':int(sum(df.reviewer_count>=2)),
         'consensus':int(sum(df.audit_state.isin(['consensus','consensus_adjudicated']))),
         'consensus_uncertain':int(sum(df.audit_state=='consensus_uncertain')),
         'adjudicated':int(sum(df.audit_state=='consensus_adjudicated')),
         'disagreements':int(sum(df.audit_state=='disagreement_adjudication_required')),
         'pending':int(sum(df.audit_state.isin(['not_reviewed','awaiting_second_reviewer']))),
         'image_sha256':m['image_sha256'], 'candidate_csv_sha256':m['candidate_csv_sha256']}
    # No population extrapolation until a fully reviewed random sample exists in
    # EVERY stratum. No dishonest 'zero error' estimates from incomplete review.
    completed=all(sum((df.sample_stratum==st)&(df.audit_state.isin(['consensus','consensus_adjudicated']))) == m['stratum_sampled'][st] for st in STRATA)
    metrics['eligible_population_estimation_allowed']=bool(completed and all(m['stratum_sampled'][st]>0 for st in STRATA))
    if metrics['eligible_population_estimation_allowed']:
        table=[];weighted_total=0;denom=0
        for st in STRATA:
            sub=df[df.sample_stratum==st]
            num=int(sum(sub.consensus_label.isin(POSITIVE)))
            n=len(sub);N=m['stratum_eligible'][st]
            phat=num/n
            weighted_total+=N*phat;denom+=N
            # Wilson interval within each sampled stratum; not a global CI.
            z=1.96;center=(phat+z*z/(2*n))/(1+z*z/n)
            half=z*math.sqrt(phat*(1-phat)/n+z*z/(4*n*n))/(1+z*z/n)
            table.append({'stratum':st,'n_reviewed':n,'N_eligible':N,'n_usable':num,
                          'sample_usable_fraction':phat,'wilson_95_lower':max(0,center-half),
                          'wilson_95_upper':min(1,center+half)})
        pd.DataFrame(table).to_csv(out/'stratum_estimates.csv',index=False)
        metrics['estimated_candidate_usable_fraction']=weighted_total/denom
        metrics['warning']='This is candidate-level usability among eligible unexamined candidates. It is not recall, and excludes previously spotchecked pilot IDs.'
    else:metrics['warning']='Two independent matching labels per sampled candidate in all 6 strata required before extrapolating usable fraction.'
    atomic_text(out/'audit_summary.json',json.dumps(metrics,ensure_ascii=False,indent=2))
    return metrics

def export_verified_crops(image_path, manifest_path, private_path, consensus_path, outdir, radius_px=24):
    """Export *object-level* adjudicated examples, NOT pixel masks or held-out GT.

    Never includes uncertain/unreviewed candidates; all exports retain image hash.
    The same image must not appear in both future train and test folds.
    """
    m=json.loads(Path(manifest_path).read_text())
    if sha(image_path)!=m['image_sha256'] or sha(private_path)!=m['private_csv_sha256']:
        raise ValueError('Source image/private queue provenance mismatch')
    d=pd.read_csv(consensus_path)
    valid=d[d.audit_state.isin(['consensus','consensus_adjudicated']) & d.consensus_label.isin(CATEGORIES[:4])]
    image=np.asarray(Image.open(image_path).convert('L'))
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for _,r in valid.iterrows():
        x=int(round(r.x_px));y=int(round(r.y_px));pad=radius_px
        arr=np.pad(image,pad,mode='reflect')[y:y+2*pad+1,x:x+2*pad+1]
        # Explicitly label crop rather than pretending to have a pixel-level mask.
        rel=f"{r.consensus_label}/{r.blind_id}.png"
        dest=out/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        Image.fromarray(arr).save(dest)
        rows.append({'blind_id':r.blind_id,'class':r.consensus_label,'image_sha256':m['image_sha256'],
                     'candidate_csv_sha256':m['candidate_csv_sha256'],'crop_path':rel,
                     'label_type':'object_level_consensus_not_pixel_mask','dataset_split_group':m['image_sha256']})
    pd.DataFrame(rows,columns=['blind_id','class','image_sha256','candidate_csv_sha256','crop_path','label_type','dataset_split_group']).to_csv(out/'verified_object_crops.csv',index=False)
    atomic_text(out/'README.md', '# Verified candidate crops\n\nThese are **object-level** annotations, not segmentation masks.\nDo not treat them as independent validation of the image used for training.\nKeep all crops from the same source image in a single fold.\n')
    return len(rows)

def gallery(image_path,blind_csv,out_image,manifest_path=None,cols=6,pad=23):
    if manifest_path is not None:
        m=json.loads(Path(manifest_path).read_text())
        if sha(image_path)!=m['image_sha256'] or sha(blind_csv)!=m['blind_csv_sha256']:
            raise ValueError('Blinded gallery image/queue provenance mismatch')
    im=Image.open(image_path).convert('L');df=pd.read_csv(blind_csv)
    tile=148;nrows=math.ceil(len(df)/cols)
    canvas=Image.new('RGB',(tile*cols,nrows*(tile+24)),(244,244,244));draw=ImageDraw.Draw(canvas)
    import cv2
    npimg=np.asarray(im)
    for i,row in df.iterrows():
        x=int(round(row.x_px));y=int(round(row.y_px));size=pad
        enlarged=cv2.copyMakeBorder(npimg,pad,pad,pad,pad,cv2.BORDER_REFLECT_101)[y:y+2*pad+1,x:x+2*pad+1]
        patch=Image.fromarray(enlarged).resize((tile-8,tile-8),Image.Resampling.NEAREST).convert('RGB')
        ox=(i%cols)*tile+4;oy=(i//cols)*(tile+24)+4
        canvas.paste(patch,(ox,oy));cx=ox+(tile-8)//2;cy=oy+(tile-8)//2
        draw.line((cx-5,cy,cx+5,cy),fill=(255,216,30),width=1)
        draw.line((cx,cy-5,cx,cy+5),fill=(255,216,30),width=1)
        draw.text((ox+5,oy+tile-3),str(row.blind_id),fill=(25,25,25))
    Path(out_image).parent.mkdir(parents=True,exist_ok=True)
    canvas.save(out_image,quality=84,optimize=True)
    return str(out_image)

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('prepare');p.add_argument('--image',required=True);p.add_argument('--candidates',required=True);p.add_argument('--out',required=True);p.add_argument('--per-stratum',type=int,default=10);p.add_argument('--seed',type=int,default=20261029);p.add_argument('--exclude-ids-csv')
    p=sub.add_parser('gallery');p.add_argument('--image',required=True);p.add_argument('--blind',required=True);p.add_argument('--out',required=True);p.add_argument('--manifest',required=True)
    p=sub.add_parser('record');p.add_argument('--manifest',required=True);p.add_argument('--private',required=True);p.add_argument('--events',required=True);p.add_argument('--blind-id',required=True);p.add_argument('--reviewer',required=True);p.add_argument('--label',required=True,choices=CATEGORIES);p.add_argument('--note',default='');p.add_argument('--diameter-px',type=float);p.add_argument('--role',choices=['reviewer','adjudicator'],default='reviewer')
    p=sub.add_parser('evaluate');p.add_argument('--manifest',required=True);p.add_argument('--private',required=True);p.add_argument('--events',required=True);p.add_argument('--out',required=True)
    p=sub.add_parser('export-crops');p.add_argument('--image',required=True);p.add_argument('--manifest',required=True);p.add_argument('--private',required=True);p.add_argument('--consensus',required=True);p.add_argument('--out',required=True)
    a=ap.parse_args()
    if a.cmd=='prepare':
        excluded=set(pd.read_csv(a.exclude_ids_csv).id) if a.exclude_ids_csv else set()
        d,m=prepare(a.image,a.candidates,a.out,a.per_stratum,a.seed,excluded);print(json.dumps(m,indent=2))
    elif a.cmd=='gallery':gallery(a.image,a.blind,a.out,a.manifest)
    elif a.cmd=='record':print(add_decision(a.manifest,a.private,a.events,a.blind_id,a.reviewer,a.label,a.note,a.diameter_px,a.role))
    elif a.cmd=='evaluate':print(evaluate(a.manifest,a.private,a.events,a.out))
    elif a.cmd=='export-crops':print('Exported', export_verified_crops(a.image,a.manifest,a.private,a.consensus,a.out),'object-level crops')
if __name__=='__main__': main()
