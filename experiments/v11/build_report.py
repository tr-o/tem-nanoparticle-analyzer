"""v11 evaluation report: always show completion status accurately."""
from pathlib import Path
import json
root=Path(__file__).resolve().parent
met=root/'results/metrics.json'
stat=json.loads((root/'status.json').read_text()) if (root/'status.json').exists() else {'dataset':'not_run','evaluation':'not_run'}
lines=['# v11 — 粒子分割の過剰結合を、教師あり検証で改善する', '',
'> **EMPS実測画像・粒子別IDラベルの学習/評価。テスト画像に閾値を合わせ込まない。**', '',
'## 目的と試験設計', '',
'- v10では粒子領域Dice **0.765** に対し、Watershed分割後の粒子単位Recallが **0.223** と低かった（公式test 8画像のmacro平均）。',
'- v11では**RFの特徴量と学習画像を同じまま**にし、別の公式train画像6枚を検証用に確保して、二値化しきい値とWatershed中心間隔を選ぶ。',
'- 学習28画像と検証6画像は別。公式test 8画像を使ったチューニングは禁止。',
'- 分割候補の評価には、粒子ID付き人手GTとの**IoU ≥ 0.5 の1対1対応**を用いる。',
'- 実測元データは[EMPS（Yildirim & Cole 2021）](https://github.com/by256/emps)の公式分割。MITライセンス。',
'',f'公開データ取得：`{stat.get("dataset","not_run")}` / 評価：`{stat.get("evaluation","not_run")}`。','']
if met.exists():
    data=json.loads(met.read_text());old=data['baseline'];new=data['tuned'];param=data['validation_best']
    def pct(x):return f'{100*x:.2f}%'
    lines+=['## 実測テスト8画像の結果','',
        f'**train内の検証用6画像で選んだ設定：** 粒子確率閾値 `{param["threshold"]}`、最小中心距離 `{param["min_center_distance"]} px`。検証F1は `{param["validation_instance_f1"]:.3f}`。', '',
        '| 公式testの粒子対応指標 | v10固定設定 | v11検証セットで選択 |', '|---|---:|---:|',
        f'| 1対1正解TP | {old["tp"]} | {new["tp"]} |',
        f'| 誤検出FP | {old["fp"]} | {new["fp"]} |',
        f'| 見落としFN | {old["fn"]} | {new["fn"]} |',
        f'| **micro F1** | **{pct(old["micro_f1"])}** | **{pct(new["micro_f1"])}** |',
        f'| micro Precision | {pct(old["micro_precision"])} | {pct(new["micro_precision"])} |',
        f'| micro Recall | {pct(old["micro_recall"])} | {pct(new["micro_recall"])} |',
        f'| macro Recall（8画像平均） | {pct(old["macro_recall"])} | {pct(new["macro_recall"])} |',
        '', '### 全画像の比較（原画像／粒子別GT／固定版／検証調整版）', '',
        '黄色は人手GTの粒子別境界、シアンは予測境界。表示のための座標移動は行っていない。','']
    for fig in sorted((root/'results').glob('*.jpg')):
        lines +=[f'![実測EMPS {fig.stem}: v10固定設定とv11検証で選択した分離の比較]({fig.relative_to(root).as_posix()})','']
    if new['micro_f1']>old['micro_f1']:
        verdict='テストでmicro F1は改善。ただし、この8枚だけで撮影条件を超えた汎化は証明できない。'
    else:
        verdict='**micro F1改善は確認できなかった。** 設定は既存の標準版へ取り込まない。'
    lines+=['**判定：** '+verdict]
else:
    lines +=['**独立テストの結果は未取得。** 指標・改善率は報告しない。',
            '', '## 前段階で取得した実測画像の解析図',
            '', '![v10 の人手ラベル付き実測粒子の解析プレビュー](../v10/results_emps/f28b702df5.jpg)']
lines+=['','## 限界と次の実装','',
 '- EMPSはTEM/SEM混合。HRTEM（格子縞）の精度と同一視できない。',
 '- EMPSは外部の粒子別マスク。輪郭を境界として扱うが、原子レベルの「真の」粒径を保証しない。',
 '- スケールはメタデータ照合していないので実長ではなくpx。',
 '- 公式test 8画像は初回評価から再使用している。今後の新規モデル選択には別セッションの未知画像が必要。',
 '- 改善が不十分なら中心検出にも教師ありモデルを導入し、Watershedの中心不足を直接解決する。',
 '', '## 再現', '',
 '```bash','pip install -r requirements.txt','PYTHONPATH=v11 python -m unittest discover -s v11 -p "test_v11.py"',
 'python experiments/v11/tune_instances.py --dataset-root /path/to/emps --out experiments/v11/results','python experiments/v11/build_report.py','```','',
 '[実装](tune_instances.py) / [単体テスト](test_v11.py) / [GitHub Actions](../.github/workflows/v11-emps.yml) / [前回v10レポート](../v10/REPORT.md)']
(root/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
