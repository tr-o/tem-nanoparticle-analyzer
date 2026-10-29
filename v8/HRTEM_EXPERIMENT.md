# HRTEM用の別経路 — 結晶格子テクスチャに基づく粒子候補抽出

> **暫定的な探索結果。教師あり明視野モデルでの大量誤検出を受け、別アルゴリズムを試験したもの。正解マスク未照合。**

## 旧モデルの失敗を記録

旧明視野モデルが格子縞とノイズを粒子と誤認し、画像1で1,436候補・径中央値0.40 nm、画像2で1,364候補・径中央値0.44 nmとなった。**これらの値は測定結果として採用しない。**

## HRTEMテクスチャ方式

Gaborフィルタ群の位相を組み合わせて局所的な周期縞の優勢方向を計算し、暗い粒子エンベロープと交差させる。サイズ下限は**今回の方式の検出条件**であって試料の物理的な下限を意味しない。

| Image | Accept | Review | Reject | Provisional median |
|---|---:|---:|---:|---:|
| NP-TEM-Image1.dm3 | 41 | 18 | 18 | 2.02 nm |
| NP-TEM-Image2.dm3 | 106 | 11 | 16 | 2.32 nm |

### NP-TEM-Image1

![実DM3原画像、結晶テクスチャ、輪郭、ヒストグラム](results_hrtem/NP-TEM-Image1/overview.jpg)

![原画像](results_hrtem/NP-TEM-Image1/raw_preview.png)

![結晶周期性特徴マップ](results_hrtem/NP-TEM-Image1/texture.png)

![粒子周囲の暗いコントラスト特徴](results_hrtem/NP-TEM-Image1/darkness.png)

![採用・要確認・除外の輪郭](results_hrtem/NP-TEM-Image1/overlay.png)

[全候補CSV](results_hrtem/NP-TEM-Image1/particles.csv) / [実行情報](results_hrtem/NP-TEM-Image1/summary.json)


### NP-TEM-Image2

![実DM3原画像、結晶テクスチャ、輪郭、ヒストグラム](results_hrtem/NP-TEM-Image2/overview.jpg)

![原画像](results_hrtem/NP-TEM-Image2/raw_preview.png)

![結晶周期性特徴マップ](results_hrtem/NP-TEM-Image2/texture.png)

![粒子周囲の暗いコントラスト特徴](results_hrtem/NP-TEM-Image2/darkness.png)

![採用・要確認・除外の輪郭](results_hrtem/NP-TEM-Image2/overlay.png)

[全候補CSV](results_hrtem/NP-TEM-Image2/particles.csv) / [実行情報](results_hrtem/NP-TEM-Image2/summary.json)


## 解釈

- この方式は**教師あり学習済みモデルではなく**、HRTEM向けの物理的特徴に基づく探索的処理。
- 粒子数は候補数、粒径は採用候補の円相当径。真の精度・再現率や分布を示すものではない。
- 特に格子縞の方向・焦点・支持膜の構造で誤検出するため、独立した人手の正解と比較する必要がある。
- 元のDM3ピクセル校正に基づいてnm換算を行った。元データはGitHubに再配布しない。

[DM3インポート全体レポート](REPORT.md)
