#!/usr/bin/env python3
"""Blinded TEM candidate annotation GUI; no model status is revealed to reviewer.
Run after audit_protocol.py prepare, with ONLY audit_blind.csv (not private CSV).
Requires actual image in correct pixels and SHA matched to manifest.
"""
from pathlib import Path
import sys,json,hashlib
sys.path.insert(0,str(Path(__file__).parent))
import numpy as np,pandas as pd,cv2,gradio as gr
from audit_protocol import add_decision, CATEGORIES,sha

ROOT=Path(__file__).resolve().parent

def render(image_path,blind_csv,manifest_path,index):
    try:
        manifest=json.loads(Path(manifest_path).read_text())
        if sha(image_path)!=manifest['image_sha256'] or sha(blind_csv)!=manifest['blind_csv_sha256']:
            raise ValueError('Image or blind CSV hash mismatch')
        d=pd.read_csv(blind_csv)
        i=max(0,min(int(index),len(d)-1));row=d.iloc[i]
        img=cv2.imread(image_path,cv2.IMREAD_GRAYSCALE)
        if img is None:raise ValueError('Missing image')
        p=32;im=cv2.copyMakeBorder(img,p,p,p,p,cv2.BORDER_REFLECT_101)
        x=int(round(row.x_px));y=int(round(row.y_px));patch=im[y:y+2*p+1,x:x+2*p+1]
        patch=cv2.cvtColor(cv2.resize(patch,(440,440),interpolation=cv2.INTER_NEAREST),cv2.COLOR_GRAY2RGB)
        cx=cy=220;cv2.drawMarker(patch,(cx,cy),(255,225,20),cv2.MARKER_CROSS,18,1)
        overview=cv2.cvtColor(img,cv2.COLOR_GRAY2RGB)
        cv2.circle(overview,(x,y),11,(255,220,10),2)
        # No model status or classifier priority is shown.
        return patch, overview, f'Blind sample {row.blind_id} ({i+1}/{len(d)}). Label only what is clearly visible.',i,str(row.blind_id)
    except Exception as exc:return None,None,str(exc),int(index),''

def save(manifest,blind,events,blind_id,reviewer,label,note,diameter):
    try:
        if diameter in (None,''):diameter=None
        e=add_decision(manifest,blind,events,blind_id,reviewer,label,note,diameter)
        return 'Recorded '+e['blind_id']+' as '+e['label']+' for reviewer '+e['reviewer']
    except Exception as exc:return 'ERROR: '+str(exc)

def app():
    with gr.Blocks(title='TEM v6 blinded dual reviewer') as demo:
        gr.Markdown('# TEM粒子のブラインド二重レビュー\n**モデルの採否を見ずに、粒子ごとの根拠を分類します。** 同じ候補を2人が独立に評価し、不一致は別途仲裁。こちらの画面では統計を確定しません。')
        with gr.Row():
            image=gr.Textbox(label='TEM source file',value='data/external/pt1_original.png')
            blind=gr.Textbox(label='Blind audit CSV',value=str(ROOT/'audit/audit_blind.csv'))
            manifest=gr.Textbox(label='Audit manifest',value=str(ROOT/'audit/audit_manifest.json'))
        events=gr.Textbox(label='Append-only events JSONL',value=str(ROOT/'audit/review_events.jsonl'))
        with gr.Row():
            index=gr.Number(label='Item index (0-based)',value=0,precision=0)
            prev=gr.Button('Previous');load=gr.Button('Load');nxt=gr.Button('Next')
        with gr.Row():
            crop=gr.Image(label='Blind candidate crop',interactive=False)
            full_image=gr.Image(label='Context / entire TEM field',interactive=False)
            with gr.Column():
                status=gr.Textbox(label='Sample information',interactive=False)
                blindid=gr.Textbox(label='Blind ID',interactive=False)
                reviewer=gr.Textbox(label='Reviewer identifier')
                choice=gr.Radio(list(CATEGORIES),value='uncertain',label='Visual classification')
                note=gr.Textbox(label='Reason / visible ambiguity')
                diameter=gr.Number(label='Optional manual diameter (px), blank if not measured')
                submit=gr.Button('Record append-only decision',variant='primary')
                msg=gr.Textbox(label='Save result',interactive=False)
        deps=[image,blind,manifest,index];outs=[crop,full_image,status,index,blindid]
        load.click(render,inputs=deps,outputs=outs)
        prev.click(lambda i:max(0,int(i)-1),inputs=index,outputs=index).then(render,inputs=deps,outputs=outs)
        nxt.click(lambda i:int(i)+1,inputs=index,outputs=index).then(render,inputs=deps,outputs=outs)
        submit.click(save,inputs=[manifest,blind,events,blindid,reviewer,choice,note,diameter],outputs=msg)
    return demo

if __name__=='__main__':app().launch(server_name='127.0.0.1')
