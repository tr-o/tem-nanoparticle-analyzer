from pathlib import Path
import json
root=Path(__file__).resolve().parent
path=root/'results/metrics.json'
status_path=root/'status.json'
status=json.loads(status_path.read_text()) if status_path.exists() else {'download':'not_run','evaluation':'not_run'}
lines=[
'# v14 — 反転対称の教師あり粒子分割：過去8枚を除いた新しい20枚で評価',
'',
'> **ステータス：新規テスト20枚はEMPSの公式testから選択。v10〜v13で使った8枚は除外。** EMPSにはTEM/SEMが混在し、これはDM3/HRTEMの独立外部評価ではありません。',
'',
'## 評価設計',
'',
'- v13は既存コードの実装・訓練選択と事前固定パラメータ（semantic .52, border .35, area 45 px², erosion 1）を保持。',
'- v14は同じ公式train画像28枚の各画像と輝度反転画像をペア学習し、推論でも通常像と反転像の予測確率を平均する。**入力反転に厳密に対称**。',
'- 過去に繰り返し評価した8枚を除外し、固定seed=20261114で残りの公式test画像から20枚選出。評価マスクは学習・閾値調整に使用しない。',
'- 粒子一致は人手インスタンスマスクとの1対1マッチング（IoU≥0.5）、微平均F1を主指標とし、TP/FP/FN・画素径MAEも保存。',
'- 粒子の**明／暗**は正解マスクを使って*評価後に層別表示するだけ*。予測アルゴリズムには渡さない。',
'- 注意：以前のテスト8枚の失敗に着想を得た改良なので、完全なプロジェクト外データセットでの検証ではない。',
'', f'CI状態：取得 `{status.get("download")}`、評価 `{status.get("evaluation")}`。',''
]
if path.exists() and status.get('evaluation')=='success':
 d=json.loads(path.read_text());base=d['v13'];new=d['v14'];fmt=lambda x:f'{100*x:.2f}%'
 lines+=['## 未使用テスト20枚の結果','',
 '| 指標 | v13（固定） | v14（明暗対称） |','|---|---:|---:|',
 *[f'| {k.upper()} | {base[k]} | {new[k]} |' for k in ('tp','fp','fn')],
 f'| Micro F1 | {fmt(base["micro_f1"])} | {fmt(new["micro_f1"])} |',
 f'| Precision | {fmt(base["micro_precision"])} | {fmt(new["micro_precision"])} |',
 f'| Recall | {fmt(base["micro_recall"])} | {fmt(new["micro_recall"])} |',
 f'| 対応粒子の直径MAE（画像別平均、px） | {base["mean_matched_diameter_mae_px"]} | {new["mean_matched_diameter_mae_px"]} |',
 '',
 ('**判定：この20枚ではF1非低下。候補として維持。ただしDM3/HRTEM外部検証前なのでデフォルト置換は保留。**' if d['go_if_v14_f1_greater_or_equal'] else '**判定：この20枚ではF1低下。標準モデルを更新しない（NO-GO）。**'),
 '', '### 粒子の極性別（評価後の層別のみ）', '',
 '|極性|視野数|v13 F1|v14 F1|','|---|---:|---:|---:|']
 for key,val in d['by_polarity'].items():
  n=sum(r['polarity_for_reporting_only']==key for r in d['per_image'])
  lines += [f'|{key}|{n}|{fmt(val["v13"]["micro_f1"])}|{fmt(val["v14"]["micro_f1"])}|']
 lines+=['','### 全視野別のTP/FP/FN','', '|ID|明暗|GT粒子数|v13 TP|v14 TP|v14 FP|v14 FN|','|---|---|---:|---:|---:|---:|---:|']
 for r in d['per_image']:
  lines.append(f'| `{r["id"]}` | {r["polarity_for_reporting_only"]} | {r["gt_count"]} | {r["v13"]["tp"]} | {r["v14"]["tp"]} | {r["v14"]["fp"]} | {r["v14"]["fn"]} |')
 lines += ['','### 画像：原像・正解輪郭・旧版・新版','',
 '黄色が人手インスタンスGT、シアンが推定輪郭。比較には**同じ画像・同じ座標**を使う。','']
 for fig in sorted((root/'results').glob('*.jpg')):
  lines += [f'![EMPS {fig.stem}：実画像、人手正解、v13旧版、v14明暗対称版](results/{fig.name})','']
 lines += ['[数値の全件記録](results/metrics.json) / [各視野CSV](results/per_image.csv)','']
else:
 lines += ['## 実測データによる評価結果','',
 '**まだ評価完了を確認できません。計算結果やF1改善を創作せず、空欄のまま保持します。**','',
 '比較の基準として以前のv13のGT付き例を掲載します（v14の結果ではありません）。','',
 '![過去v13のGT付き解析例](../v13/results/c61a50a061.jpg)','']
lines += ['## 限界・次の優先課題','',
 '- 明暗の極性が局所的に反転するHRTEM・多相粒子は、単純な全画像反転と同等ではない。',
 '- IoU≥0.5の粒子対応に失敗した粒子の径誤差はMAEに含まれない。必ずF1と合わせて読む。',
 '- EMPSはTEM/SEM混合。撮影セッションやメーカーが独立したDM3データでの再試験を別途要する。',
 '- 新20枚の性能が高くても、最初の8枚での反復開発によるモデル設計の間接的過適合に注意。',
 '', '[モデル・評価コード](polarity_benchmark.py) / [回帰テスト](test_v14.py) / [GitHub Actions](../.github/workflows/v14-polarity-benchmark.yml) / [過去のv13レポート](../v13/REPORT.md)']
(root/'REPORT.md').write_text('\n'.join(lines)+'\n')
