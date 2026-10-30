# 実験の索引：v1〜v15

[README](../README.md) / [全画像索引](FIGURE_INDEX.md)

**各バージョンは研究時点のスナップショットです。** 後続版で学習データ・評価画像が違う場合、その数値を単純に上下比較してはいけません。

| 時期 | 実験と記録 | 学んだこと |
|---|---|---|
| v1 | [人工TEMの16+4教師データ](TRAINING_DATA.md) / [初期手法](METHODS.md) | RF領域認識は模擬画像で動作、接触分離が弱点 |
| v2/v3 | [公開Pt/Ag 6枚を解析](../experiments/v2/REPORT.md) / [スケール検量](../experiments/v2/SCALE_CALIBRATION.md) | 弱教師とOCR、短いバー保留、ノイズ過検出 |
| v4 | [過剰除外・中心再分離](../experiments/v4/REPORT.md) | 密集Ptは採否見直しが必要 |
| v5 | [目視スポット監査](../experiments/v5/REPORT.md) | 要確認に単粒子候補が残る |
| v6 | [二人のブラインドレビュー基盤](../experiments/v6/REPORT.md) | 正解と自己評価を分離 |
| v7 | [ROI座標系統一](../experiments/v7/REPORT.md) | 青/赤の固定座標ずれを診断。生成元の完全特定は未達 |
| v8 | [実DM3・校正・HRTEM](../experiments/v8/INDEX.md) | 原画素とnm/px取得成功。旧RFはHRTEMで大量誤検出 |
| v9 | [HRTEM人手マスク取得の試み](../experiments/v9/REPORT.md) | Dryad取得失敗。精度未評価 |
| v10 | [EMPS人手インスタンスで初の計測](../experiments/v10/REPORT.md) | 領域Diceだけでは粒子の接触分離を評価できない |
| v11 | [Watershedを教師側検証で調整](../experiments/v11/REPORT.md) | 小幅な改善 |
| v12 | [中心位置の教師ありRF](../experiments/v12/REPORT.md) | インスタンスF1低下、NO-GO |
| v13 | [教師あり粒子間境界](../experiments/v13/REPORT.md) | 旧8枚でインスタンスF1 53.20%、反復テストに注意 |
| v14 | [明暗反転を対称化](../experiments/v14/REPORT.md) / [不確実性](../experiments/v14/UNCERTAINTY.md) | 新20枚で総合NO-GO、明るい粒子では改善 |
| v15 | [教師28→96枚](../experiments/v15/REPORT.md) / [不確実性](../experiments/v15/UNCERTAINTY.md) | 別の新20枚でF1 23.14%→34.66%。HRTEM汎化は未確認 |

研究ごとのコードは同じ`experiments/vN`配下に保存。過去の失敗例も削除していません。

## 表示画像の例

![初期Pt/Ag実測像の改良結果](../experiments/v4/docs/pt1_zoom_audit.jpg)

![v13 教師ありの粒子境界比較](../experiments/v13/results/5f42a8d4a9.jpg)

![v15 教師増量での予測輪郭比較](../experiments/v15/results/04dbda93f9.jpg)
