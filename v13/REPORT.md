# v13 — 実測EMPSで粒子境界を直接学習する

> 実測評価の結果はGitHub Actions完了後、このページに画像と一緒に自動記録します。未検証の改善値は主張しません。

## 検証方法

公式train28枚で多尺度RFの領域マスク＋粒子内部/境界/背景のExtraTreesを学習し、別のtrain6枚で境界の分割閾値を選択。公式test8枚でv11ベースラインと1対1のIoU≥0.5で比較。撮影条件が異なるHRTEMへの汎化は今後の検証課題。

[GitHub Actions](../.github/workflows/v13-emps.yml) / [実装](boundary_model.py) / [v12失敗例](../v12/REPORT.md)
