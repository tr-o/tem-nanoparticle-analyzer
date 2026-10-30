"""Browser GUI for actual DM3/DM4 files; run: python experiments/v8/app_dm.py.

Separate the instrument pixel calibration from particle-detection confidence.
Never route HRTEM to the bright-field RandomForest without explicit choice.
"""
import json
import tempfile
from pathlib import Path
import gradio as gr
from inspect_dm import inspect
from hrtem_texture import infer_hrtem
from analyze_dm import infer as infer_rf
ROOT=Path(__file__).resolve().parents[2]


def inspect_file(file_path):
    if not file_path:
        raise gr.Error('まずDM3/DM4ファイルを選んでください。')
    try:
        data=inspect(file_path)
    except Exception as e:
        raise gr.Error(f'DM3/DM4形式・メタデータ読取エラー: {e}') from e
    rows=[]
    for x in data['two_dimensional_images']:
        rows.append([x['index'],str(x['shape']),x['dtype'],x['calibration_status'],x['x_nm_per_px'],x['y_nm_per_px']])
    return data,rows


def run_file(file_path,dataset_index,frame_index,analysis_mode,size_floor_nm):
    if not file_path: raise gr.Error('ファイルを指定してください。')
    idx=int(dataset_index)
    frame=None if frame_index is None or int(frame_index)<0 else int(frame_index)
    if idx<0:raise gr.Error('dataset_indexは0以上です。')
    try:
        output=Path(tempfile.mkdtemp(prefix='tem_dm_analysis_'))
        if analysis_mode.startswith('HRTEM'):
            if frame is not None:
                raise ValueError('HRTEM 3D frame selection is not implemented; extract a single 2D image first')
            summary=infer_hrtem(file_path,output,dataset_index=idx,min_diameter_nm=float(size_floor_nm))
            csv=output/'particles.csv'
        else:
            summary=infer_rf(file_path,ROOT/'models/synthetic_rf.joblib',output,
                           dataset_index=idx,frame=frame,max_side=768)
            csv=output/'particles_all.csv'
        return str(output/'overview.jpg'),str(output/'overlay.png'),summary,str(csv)
    except Exception as e:
        raise gr.Error(f'解析失敗（元データは変更されません）: {e}') from e

with gr.Blocks(title='TEM DM3/DM4 nanoparticle analysis (research prototype)') as demo:
    gr.Markdown('''# TEM DM3 / DM4 生データ粒径解析 — 研究用
**DM3/DM4の元画素・校正軸から解析**します。明視野用RFとHRTEM専用テクスチャ試験は別方式です。**検出数や粒径の正確さは未検証です。**''')
    image=gr.File(file_types=['.dm3','.dm4'],type='filepath',label='元DM3/DM4ファイル')
    with gr.Row():
        inspect_button=gr.Button('画像・メタデータを調べる')
        info=gr.JSON(label='DM3/DM4メタデータとデータセット一覧')
    dataset=gr.Dataframe(headers=['dataset index','size','dtype','calibration','x nm/px','y nm/px'],datatype=['number','str','str','str','number','number'],interactive=False)
    inspect_button.click(inspect_file,[image],[info,dataset])
    with gr.Row():
        index=gr.Number(value=0,precision=0,label='dataset index（複数画像はメタデータで確認）')
        frame=gr.Number(value=-1,precision=0,label='3D frame index（未指定なら -1）')
        mode=gr.Radio(['HRTEM crystal texture (experimental)','Bright-field RandomForest (NOT for lattice HRTEM)'],
                      value='HRTEM crystal texture (experimental)',label='解析方式')
        min_size=gr.Number(value=1.0,minimum=0.1,label='HRTEM暫定径下限（nm、検出ルール）')
    action=gr.Button('粒子候補を解析')
    with gr.Row():
        overview=gr.Image(label='解析図・ヒストグラム')
        overlay=gr.Image(label='候補輪郭')
    result=gr.JSON(label='単位・採用数・検量状態')
    data=gr.File(label='粒子候補のCSV')
    action.click(run_file,[image,index,frame,mode,min_size],[overview,overlay,result,data])
    gr.Markdown('''結果を論文に使用する前に、実測の人手アノテーション、校正メタデータと照合してください。粒子の重なりや格子縞による偽検出は残ります。''')

if __name__=='__main__':demo.launch()
