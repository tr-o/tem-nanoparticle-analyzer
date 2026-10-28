#!/usr/bin/env python3
"""Local interactive particle-review UI. Never modifies original model CSV."""
from pathlib import Path
import sys,os
sys.path.insert(0,str(Path(__file__).parent))
import cv2,numpy as np,pandas as pd,gradio as gr,hashlib
from review_workflow import record_decision, load_decisions, apply_decisions
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATES='v5/results/YOUR_TEM/review_triage_all.csv'
DEFAULT_IMAGE='data/external/YOUR_TEM_500px.png'  # User supplies legally obtained image
DEFAULT_DECISIONS=str(ROOT/'v5'/'review_decisions.csv')

def queue(path,mode):
    d=pd.read_csv(path)
    if mode=='pending-review only':d=d[d.status=='review']
    elif mode=='all candidates':pass
    elif mode=='reconsider rejected':d=d[d.reconsider_rejected]
    else:d=d[d.review_priority==mode]
    # Deterministic score sort, low ID tie-break.
    return d.sort_values(['independent_evidence_count','contrast_snr','id'],ascending=[False,False,True]).reset_index(drop=True)

def show(image_path,candidates_path,decisions_path,mode,index):
    try:
        d=queue(candidates_path,mode)
        if not len(d):return None,'No candidates in this queue',0,'',None
        i=min(max(int(index),0),len(d)-1)
        r=d.iloc[i];img=cv2.imread(image_path,cv2.IMREAD_GRAYSCALE)
        if img is None:raise ValueError('Image not found; supply the image paired with the candidate CSV')
        if 'source_image_sha256' in d.columns and hashlib.sha256(Path(image_path).read_bytes()).hexdigest()!=str(d.iloc[0].source_image_sha256):
            raise ValueError('IMAGE MISMATCH: the queue was generated from a different image. Re-run triage on this exact image. Do not apply coordinates to a resized/different view.')
        x=int(round(r.x_px));y=int(round(r.y_px));pad=29
        im=np.pad(img,pad,mode='reflect');crop=im[y:y+2*pad+1,x:x+2*pad+1]
        crop=cv2.resize(crop,(472,472),interpolation=cv2.INTER_NEAREST)
        crop=cv2.cvtColor(crop,cv2.COLOR_GRAY2RGB)
        cv2.drawMarker(crop,(236,236),(255,195,45),cv2.MARKER_CROSS,14,1)
        dec=load_decisions(decisions_path)
        matched=dec[dec.id==int(r.id)];existing=str(matched.iloc[0].decision) if len(matched) else '(not reviewed)'
        message=f'Item {i+1}/{len(d)} | candidate ID {int(r.id)} | model={r.status} | review-priority={r.review_priority} | original reason={r.reason} | diameter={r.diameter_px:.2f} px | saved={existing}'
        return crop,message,i,str(int(r.id)),pd.DataFrame([r])
    except Exception as e:return None,str(e),int(index),'',None

def save(candidates_path,decisions_path,id,decision,operator,comment):
    if not id:return 'Select a candidate first'
    try:
        record_decision(candidates_path,decisions_path,int(id),decision,operator,comment)
        return f'Saved decision for candidate {id}: {decision}'
    except Exception as e:return f'Error: {e}'

def export(candidates_path,decisions_path,outdir):
    try:return str(apply_decisions(candidates_path,decisions_path,outdir))
    except Exception as e:return f'Error: {e}'

with gr.Blocks(title='TEM particle audit - human review') as demo:
    gr.Markdown('# TEM粒子の目視レビュー（v5）\n**モデル判定を上書きせず記録し、確認した結果だけ別ファイルに反映**します。画像中心の黄色い十字は候補位置。')
    with gr.Row():
        imagepath=gr.Textbox(label='TEM image',value=DEFAULT_IMAGE)
        csvpath=gr.Textbox(label='v5 triage CSV',value=DEFAULT_CANDIDATES)
        decisionpath=gr.Textbox(label='Saved review decisions CSV',value=DEFAULT_DECISIONS)
    with gr.Row():
        mode=gr.Dropdown(label='Queue',value='high',choices=['high','medium','low','reconsider rejected','pending-review only','all candidates'])
        index=gr.Number(label='Queue item (0-based)',value=0,precision=0)
        load=gr.Button('Load candidate')
        prev=gr.Button('Previous')
        next=gr.Button('Next')
    with gr.Row():
        im=gr.Image(label='Particle-centered magnification',interactive=False)
        tbl=gr.Dataframe(label='Quantitative evidence',interactive=False)
    status=gr.Textbox(label='Model and audit status',interactive=False)
    idbox=gr.Textbox(label='Candidate ID',interactive=False)
    with gr.Row():
        choice=gr.Radio(['accept','reject','uncertain'],label='Reviewer decision',value='uncertain')
        operator=gr.Textbox(label='Reviewer (provenance)',value='operator')
        comment=gr.Textbox(label='Note',value='')
        btn=gr.Button('Record explicit decision',variant='primary')
    feedback=gr.Textbox(label='Saved status',interactive=False)
    outdir=gr.Textbox(label='Export directory',value=str(ROOT/'v5'/'reviewed_output'))
    exportbtn=gr.Button('Export CSV / summary of reviewed and unreviewed candidates')
    wired=[imagepath,csvpath,decisionpath,mode,index]
    render=[im,status,index,idbox,tbl]
    load.click(show,inputs=wired,outputs=render)
    mode.change(lambda:0,outputs=index).then(show,inputs=wired,outputs=render)
    prev.click(lambda i:max(0,int(i)-1),inputs=index,outputs=index).then(show,inputs=wired,outputs=render)
    next.click(lambda i:int(i)+1,inputs=index,outputs=index).then(show,inputs=wired,outputs=render)
    btn.click(save,inputs=[csvpath,decisionpath,idbox,choice,operator,comment],outputs=feedback)
    exportbtn.click(export,inputs=[csvpath,decisionpath,outdir],outputs=feedback)

if __name__=='__main__':demo.launch(server_name='127.0.0.1')