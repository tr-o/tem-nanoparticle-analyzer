from pathlib import Path
import json
root=Path(__file__).resolve().parent
status=json.loads((root/'status.json').read_text()) if (root/'status.json').exists() else {'data':'not_run','evaluation':'not_run'}
metrics=root/'results/metrics.json'
lines=['# v13 — 粒子境界を教師あり学習して隣接粒子を分離', '',
'> **同一の公式EMPS test 8枚を使用。元の粒子領域RFに、背景／粒子内部／粒子境界の3クラスExtraTreesを追加した探索的試験。**','',
'## 方法とデータ漏洩防止','',
'- 28枚の公式train画像・粒子IDマスクで境界分類器を学習。境界は粒子間IDの相違と粒子/背景の境界から定義する。',
'- 別の公式train 6枚だけで境界確率閾値・最小マーカー面積・erosionを探索。テスト8枚を閾値選択に使用しない。',
'- v11ベースラインも同じtrain/valとテスト8枚を使用。最終指標は**IoU≥0.5の1対1粒子対応**。',
'- EMPSは**TEMとSEMの混合**。この結果はHRTEM/DM3における性能証明ではない。',
'',f'データ取得 `{status.get("data","not_run")}`、評価 `{status.get("evaluation","not_run")}`。','']
if metrics.exists():
 d=json.loads(metrics.read_text());best=d['border_validation_best'];old=d['v11'];new=d['v13'];pct=lambda x:f'{100*x:.2f}%'
 lines+=['## 人手インスタンスGTに対する公式test 8枚の成績','',
 f'検証データで選択した境界閾値 **{best["threshold"]}**、最小内側領域面積 **{best["min_seed_area"]} px²**、erosion **{best["erosion"]}**。検証F1 **{best["val_f1"]:.3f}**。','',
 '| 粒子一致（IoU ≥ 0.5） | v11 距離変換 | v13 教師あり境界 |','|---|---:|---:|',
 f'| TP | {old["tp"]} | {new["tp"]} |',f'| FP | {old["fp"]} | {new["fp"]} |',f'| FN | {old["fn"]} | {new["fn"]} |',
 f'| micro F1 | {pct(old["micro_f1"])} | {pct(new["micro_f1"])} |',
 f'| micro Precision | {pct(old["micro_precision"])} | {pct(new["micro_precision"])} |',
 f'| micro Recall | {pct(old["micro_recall"])} | {pct(new["micro_recall"])} |','',
 '## 解析画像：黄が人手GT、シアンが予測輪郭','',
 '原画像、GT、v11/v13、教師あり境界確率をすべて同一原点・縮尺で描画。','']
 for fig in sorted((root/'results').glob('*.jpg')):
  lines+= [f'![EMPS {fig.stem}：原画像、人手インスタンスGT、v11、v13、教師あり境界確率](results/{fig.name})','']
 verdict=('**v13はこの8枚の独立テストではF1改善。ただし実画像全般の検証は必要。**' if new['micro_f1']>old['micro_f1'] else '**v13は独立テストではNo-Go。標準モデルの更新は行わず、失敗理由を残す。**')
 lines+=['## 採否判断','',verdict,'']
else:
 lines+=['## 未実施・失敗時の判定','', '**このCIでは実測GT成績を確認できていないため精度を主張しません。**',
 '', '![既存v11実測画像＋粒子ID正解の比較](../v11/results/c61a50a061.jpg)','']
lines+=['## 再現性と制限','',
'- 精度比較は同じ8テスト画像を複数試作で繰返し使用しており、モデル選択の過適合リスクがある。新撮影条件を用いる外部検証で最終採用判定を行う。',
'- 重なりの3D構造は2DインスタンスGTから同定できない。',
'- nm/pixelは元SEM/TEM計測ファイルのメタデータがないため推測しない。',
'','[教師あり境界分離コード](boundary_model.py) / [5件の回帰テスト](test_v13.py) / [GitHub Actions](../.github/workflows/v13-emps.yml) / [v12（中心学習の失敗例）](../v12/REPORT.md)']
(root/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
