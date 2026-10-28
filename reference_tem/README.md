# 文献中のTEM画像：出典・ライセンス

`reference_tem/`は第三者の**公開された実験TEM図**専用です。`demo_data/`の教師データ（模擬TEM）とは区別します。

## `08_AuPt_srep40103_fig2.jpg`

- 著者: Weiwei He, Xiangna Han, Huimin Jia, Junhui Cai, Yunlong Zhou, Zhi Zheng
- 論文: *AuPt Alloy Nanostructures with Tunable Composition and Enzyme-like Activities for Colorimetric Detection of Bisulfide*
- 掲載: *Scientific Reports* **7**, 40103 (2017), Fig. 2.
- 原論文: https://doi.org/10.1038/srep40103
- 原画像: https://media.springernature.com/lw685/springer-static/image/art%3A10.1038%2Fsrep40103/MediaObjects/41598_2017_Article_BFsrep40103_Fig2_HTML.jpg
- ライセンス: [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)、論文本文のRights and permissions参照
- 改変: 保存時点で**複合Figure 2そのまま**。各パネルの切り出しなし。
- 用途: **教師データではなく参考画像**。スケールバーやパネル文字を含むので、そのままモデルに流し込まない。

その他の最初の候補9件は[参考TEM目録](../docs/REFERENCE_TEM.md)から参照し、再配布条件未確認のものはダウンロード・Git追跡しません。

## `05_Pt_supported_srep44411_fig4.jpg`

- 原論文: *Scientific Reports* **7**, article 44411 (2017), Fig. 4, https://doi.org/10.1038/srep44411
- 原画像: https://media.springernature.com/lw685/springer-static/image/art%3A10.1038%2Fsrep44411/MediaObjects/41598_2017_Article_BFsrep44411_Fig4_HTML.jpg
- ライセンス: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)、原論文をクレジット。未改変の複合図。
- 用途: 背景の複雑な担持Ptの**参考画像（教師マスクなし）**。

## `06_Pt_C_membranes301_fig3.png`（取得可能な場合）

- 原論文: *Membranes* **12**(3), 301 (2022), Fig. 3, https://doi.org/10.3390/membranes12030301
- 原画像: https://www.mdpi.com/membranes/membranes-12-00301/article_deploy/html/images/membranes-12-00301-g003.png
- ライセンス: 論文のCC BY 4.0に従い帰属表示。MDPIサイトがダウンロードを制限した場合には保存されません。
- 用途: TEM粒子とカーボン背景の識別を想定した**参考画像（教師マスクなし）**。

## `07_Pt_C_nanomaterials3800_fig1.png`（取得可能な場合）

- 原論文: *Nanomaterials* **12**(21), 3800 (2022), Fig. 1, https://doi.org/10.3390/nano12213800
- 原画像: https://www.mdpi.com/nanomaterials/nanomaterials-12-03800/article_deploy/html/images/nanomaterials-12-03800-g001.png
- ライセンス: 論文のCC BY 4.0に従い帰属表示。MDPIサイトがダウンロードを制限した場合には保存されません。
- 用途: 微小粒子検出の難易度を把握するための**参考画像（教師マスクなし）**。

## データセットの分離

**引用した図をそのまま「粒子の正解がある教師データ」と呼ばない**でください。教師画像とGTマスクは `demo_data/` です。上記はマスク未作成の参考TEM画像です。
