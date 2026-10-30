"""Gradio GUI: v2 supervised TEM instances + v3 guarded scale calibration.

Launch from the repository root: python experiments/v2/app_v3.py
"""
from pathlib import Path
import tempfile
import pandas as pd
import gradio as gr
from tem_v2 import run,MODEL


def analyze(image_path,reference_path,model_path,scale_override,confirm_short,threshold,min_contrast):
    if not image_path:
        raise gr.Error('TEM画像を選択してください')
    model_path=Path(model_path).expanduser()
    if not model_path.exists():
        raise gr.Error(f'モデルが見つかりません: {model_path}')
    try:
        manual=float(scale_override) if scale_override and scale_override>0 else None
        out=Path(tempfile.mkdtemp(prefix='tem_calibrated_'))
        res=run(image_path,model_path,outdir=out,threshold=threshold,min_contrast=min_contrast,
                nm_per_px=manual,scale_reference=reference_path or None,
                confirm_short_bar=bool(confirm_short))
        table=pd.read_csv(out/'particles_accepted.csv')
        import json
        cal=json.loads((out/'calibration.json').read_text())
        status=cal['status']; factor=res['nm_per_px']
        if factor is None:
            note=f"**自動nm換算は未実施**（{status}）。 {cal['reason']}  \nラベル: `{cal['text']}` / バー幅: {cal['bar_width_px']} px。CSVはpxのみ。"
        else:
            note=(f"**換算適用: {factor:.5g} nm/px**（{res['calibration_source']}, 自動検量: {status}）。 "
                  f"バー: {cal['bar_width_px']:.1f} px、文字: `{cal['text']}`、相対端点誤差の目安: "
                  f"{100*(cal['uncertainty_relative'] or 0):.1f}%  ")
        msg=(f"解析: 採用 {res['accepted']}、接触分割 {res['split_touching']}、除外 {res['rejected']}。  \n"
             +note+"  \n*モデルは実画像3枚の弱教師を利用。未学習画像での精度は未検証です。*")
        return str(out/'overlay.png'),str(out/'overview.png'),str(out/'scale_annotation.png'),table,str(out/'particles_accepted.csv'),str(out/'calibration.json'),msg
    except Exception as exc:
        raise gr.Error(str(exc)) from exc


with gr.Blocks(title='TEM Particle Analyzer — calibrated v3') as demo:
    gr.Markdown('## 教師ありTEM粒径解析 v3 — スケール自動認識付き\n'
                '実TEMに適応した弱教師モデル + 接触粒子分割 + 重なり候補の保守的除外。'
                '**短いバーや文字を認識できない画像はnm換算を保留**します。')
    with gr.Row():
        image=gr.Image(type='filepath',label='TEM画像（解析する画像）')
        reference=gr.Image(type='filepath',label='元の高解像度画像（同じ視野・任意）')
    with gr.Row():
        model=gr.Textbox(label='モデルパス（joblib）',value=str(MODEL))
        manual=gr.Number(label='手動nm/pixel上書き（任意・0なら自動）',value=0)
        confirm=gr.Checkbox(label='短いスケールバーも確認済みとして換算',value=False)
    with gr.Row():
        threshold=gr.Slider(.2,.9,value=.48,step=.01,label='粒子確率閾値')
        min_contrast=gr.Slider(.01,.35,value=.095,step=.005,label='周囲との最小コントラスト')
        go=gr.Button('解析する',variant='primary')
    summary=gr.Markdown()
    with gr.Row():
        overlay=gr.Image(label='採用/分割/除外粒子')
        overview=gr.Image(label='粒径ヒストグラム（検量済みならnm）')
        scale_img=gr.Image(label='スケールバー検出と除外領域')
    table=gr.Dataframe(label='採用粒子（個別の粒径）')
    with gr.Row():
        csv=gr.File(label='採用粒子CSV')
        calibration=gr.File(label='検量履歴JSON')
    go.click(analyze,[image,reference,model,manual,confirm,threshold,min_contrast],
             [overlay,overview,scale_img,table,csv,calibration,summary])

if __name__=='__main__':
    demo.launch(inbrowser=True)
