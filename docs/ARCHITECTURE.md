# データフローとソフトウェア構造

[README](../README.md) / [使い方](USER_GUIDE.md) / [評価基準](VALIDATION.md) / [図索引](FIGURE_INDEX.md)

## 解析の全体像

```mermaid
flowchart TD
 A[PNG / TIFF / DM3 / DM4] --> B[原画素とメタデータを保全]
 B --> C{空間校正を取得できるか}
 C -->|DM3メタデータ| D[X/Y nm per pixel]
 C -->|PNG等| E[スケールバーOCRと画素幅測定]
 E --> F{品質・短いバーなど確認}
 F -->|問題あり| G[px計測のみ・要確認]
 F -->|検量成功| D
 D --> H[多尺度特徴量と教師あり粒子領域確率]
 G --> H
 H --> I[粒子内部・境界確率 / HRTEMテクスチャ別経路]
 I --> J[接触分離 Watershed]
 J --> K[形状・重なり疑い・画像端の採否判定]
 K --> L[粒子CSV・粒径分布・画像・理由ログ]
 L --> M[人手レビュー・専門家GT評価]
```

この図は設計概念です。各バージョンにすべてが同時実装されているわけではありません。

## パイプラインを混ぜない

| 主用途 | コード | 根拠と制限 |
|---|---|---|
| 人工TEMのデモ | [初期RF](../tem_analyzer/legacy_rf.py) | 教師16枚・検証4枚は人工画像 |
| Pt/Agの明視野画像 | [v2](../experiments/v2/tem_v2.py)、[v4](../experiments/v4/tem_v4.py) | 弱教師・採否規則。専門家GT不足 |
| スケールバーOCR | [v2 scale](../experiments/v2/scale_calibration.py) | 短いバーは自動確定せず、元解像度参照 |
| DM3/DM4生データI/O | [v8 io](../experiments/v8/dm_io.py) | DM3実ファイル2件で確認。DM4実ファイル未評価 |
| HRTEM格子特徴 | [v8](../experiments/v8/hrtem_texture.py) | Gabor+暗部。教師ありでなく正解未照合 |
| TEM/SEMインスタンス境界 | [v13](../experiments/v13/boundary_model.py)、[v15](../experiments/v15/data_scale_benchmark.py) | EMPS公式インスタンスラベルで検証。DM3へ転用不可 |

## 座標・単位の不変条件

- 原画像画素座標は **(row, col)**、OpenCV描画は **(x, y)=(col, row)**。
- クロップ内部の輪郭は元ROI原点を足して**原画像の座標系に戻す**。v7の修正を回帰テスト。
- 縮小画像のピクセル校正は、横/縦それぞれの倍率だけ増やして保持。
- `A_px × sx_nm/px × sy_nm/px`をnm²に変換し、円相当径は`d=2√(A_nm2/π)`。スケール不明では絶対nm値を出さない。
- 画像とGTは同一視野、寸法、原点を確認し、異なる場合は黙って伸縮させない。

## 運用構造

**`tem_analyzer/` は利用者向けの安定した入口**で、従来の研究コードを明示的に起動します。過去の研究結果を勝手に書き換えません。`experiments/vN`は再現用に保存された研究プロトタイプであり、単独での比較は各README/REPORTの条件を守って行います。

![DM3原画素とテクスチャによる粒子候補](../experiments/v8/results_hrtem/NP-TEM-Image2/overview.jpg)
