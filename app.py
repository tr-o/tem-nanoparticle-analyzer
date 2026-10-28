"""Optional Gradio browser interface. Install gradio and pandas before use."""
from pathlib import Path
import tempfile

import gradio as gr
import pandas as pd
from tem_particle_ml import save_inference

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = ROOT / 'trained_rf.joblib'
EXAMPLE = ROOT / 'demo_data/test/images/test_00.png'


def analyze(file_path, model_path, nm_per_px, threshold, min_area, prominence):
    if not file_path:
        raise gr.Error('TEM画像を選択してください')
    path = Path(model_path).expanduser()
    if not path.exists():
        raise gr.Error('モデルがありません。先に python run_demo.py を実行してください: ' + str(path))
    scale = float(nm_per_px) if nm_per_px is not None and float(nm_per_px) > 0 else None
    out = Path(tempfile.mkdtemp(prefix='tem_result_'))
    info = save_inference(file_path, path, out, scale,
                          float(threshold), int(min_area), prominence=float(prominence))
    table = pd.read_csv(out/'particles.csv')
    msg = (f"測定粒子数: {info['n_measured']}、平均径: {info['mean_diameter']:.2f} {info['diameter_unit']}"
           if info['mean_diameter'] is not None else '粒子が見つかりませんでした')
    return str(out/'overlay.png'), str(out/'overview.png'), table, str(out/'particles.csv'), msg


with gr.Blocks(title='TEM supervised nanoparticle analyzer') as demo:
    gr.Markdown('## TEM粒径解析（教師ありRF + Watershed）\n'
                '**付属の学習済みモデルは模擬TEMのみで訓練**。実測TEMには再学習してください。')
    with gr.Row():
        image = gr.Image(value=str(EXAMPLE) if EXAMPLE.exists() else None,
                         type='filepath', label='TEM画像')
        with gr.Column():
            model = gr.Textbox(label='モデルのパス', value=str(DEFAULT_MODEL))
            scale = gr.Number(label='nm/pixel（0の場合はpx出力）', value=0.)
            threshold = gr.Slider(.2, .9, value=.52, step=.01, label='確率閾値')
            min_area = gr.Slider(5, 120, value=22, step=1, label='最小面積 px²')
            prominence = gr.Slider(.5, 5., value=2., step=.25, label='分離パラメータ')
            run = gr.Button('解析する', variant='primary')
    summary = gr.Markdown()
    with gr.Row():
        overlay = gr.Image(label='輪郭付き画像')
        overview = gr.Image(label='輪郭とヒストグラム')
    table = gr.Dataframe(label='測定値')
    csv = gr.File(label='CSVダウンロード')
    run.click(analyze, [image, model, scale, threshold, min_area, prominence],
              [overlay, overview, table, csv, summary])

if __name__ == '__main__':
    demo.launch(inbrowser=True)
