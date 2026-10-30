from pathlib import Path
import json
root=Path(__file__).resolve().parent
status=json.loads((root/'status.json').read_text()) if (root/'status.json').exists() else {'data':'not_run','evaluation':'not_run'}
metric=root/'results/metrics.json'
lines=['# v12 — 粒子中心の教師あり検出で接触粒子を分割', '',
'> **この段階の新規性：粒子/背景だけでなく、粒子IDの人手GTから中心位置も学習。** EMPS公式train/testを厳密に分離する。', '',
'## 構成','',
'- 従来：多尺度Random Forestで粒子領域を学習 → 距離変換ピーク → Watershed。',
'- v12：同じ領域モデル + **別のRandom Forestで粒子中心候補の確率を学習** → 検証セットで選んだ中心閾値をWatershedのマーカーに使用。',
'- 粒子中心教師ラベルは、公式trainにある個々のインスタンス重心の周辺のみを陽性とする。',
'- train28画像で領域RFと中心RFを学習、別の公式train6画像でマーカーパラメータを選択。テスト8画像は一切閾値探索に使わない。',
'- 対象：公開[EMPS instance segmentation](https://github.com/by256/emps)（TEM/SEM混合、MITライセンス）。',
'',f'実測データ取得：`{status.get("data","not_run")}`、評価：`{status.get("evaluation","not_run")}`。','']
if metric.exists():
 d=json.loads(metric.read_text());p=d['validation_best'];old=d['old'];new=d['new'];pct=lambda v:f'{v*100:.2f}%'
 lines+=['## 独立テスト（公式test 8画像）','',
 f'**検証用trainから選んだ設定：** 中心確率閾値 `{p["center_threshold"]}`、最小中心距離 `{p["min_center_distance"]} px`。検証セットでのF1 `{p["val_f1"]:.3f}`。','',
 '| 粒子IDの一対一対応（IoU≥0.5） | v11 距離変換中心 | v12 教師あり中心 |', '|---|---:|---:|',
 f'| TP | {old["tp"]} | {new["tp"]} |',f'| FP | {old["fp"]} | {new["fp"]} |',f'| FN | {old["fn"]} | {new["fn"]} |',
 f'| micro F1 | **{pct(old["micro_f1"])}** | **{pct(new["micro_f1"])}** |',
 f'| micro Precision | {pct(old["micro_precision"])} | {pct(new["micro_precision"])} |',
 f'| micro Recall | {pct(old["micro_recall"])} | {pct(new["micro_recall"])} |',
 f'| macro Recall | {pct(old["macro_recall"])} | {pct(new["macro_recall"])} |',
 '','## 実測TEM/SEMと人手GTの境界比較','',
 '**黄：専門家が付けた各粒子の輪郭。シアン：v11/v12で検出した粒子。** いずれも同一画像座標。','']
 for fig in sorted((root/'results').glob('*.jpg')):
  lines+= [f'![EMPS {fig.stem}：v11と教師あり中心v12の粒子輪郭・中心確率]({fig.relative_to(root).as_posix()})','']
 verdict='**独立テストでF1が改善**したが、8画像での探索段階であり、未知の撮影条件に一般化するとは限らない。' if new['micro_f1']>old['micro_f1'] else '**独立テストでF1改善は確認できず。** v12は標準モデルに採用せず、失敗例とコードだけ残す。'
 lines+=['**採否判定：** '+verdict]
else:
 lines+=['**まだ実測の独立テスト値を取得できていない。数値を捏造しない。**',
 '','![前版v11での独立実測画像・正解マスクとの比較](../v11/results/c61a50a061.jpg)']
lines+=['','## 限界','',
 '- 元のGTは粒子投影像のアノテーションであり、物理的に重なった粒子は不確定。',
 '- 今回は画像を512 px以下へ縮小しているため、nm単位の検量は行わず粒径誤差はpx単位。',
 '- EMPSにはSEMも含まれる。v8のHRTEM-DM3での汎化は別途検証が必要。',
 '- 既存test8画像の再利用により追加モデル選択を繰り返すとテストセットへの過適合リスクがある。今後のGo/No-Goには未知撮影セッションが必要。',
 '', '## GitHub再現','',
 '[中心学習・分割コード](center_model.py) / [単体テスト](test_v12.py) / [再実行ワークフロー](../.github/workflows/v12-emps.yml) / [v11レポート](../v11/REPORT.md)']
(root/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
