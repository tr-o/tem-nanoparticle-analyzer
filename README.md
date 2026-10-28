# TEM nanoparticle analyzer — 最新進捗

**[v6：高密度Ptの過剰除外を検証するブラインド層別レビュー（画像60候補・二重判定ワークフロー）](v6/REPORT.md)**

v6では**モデルの精度を確定したわけではありません**。モデル採用・要確認・除外の各候補を独立して確認する監査のためのサンプルとツールを追加しました。画像由来のSHA-256一致・60件の層別無作為抽出・6件の回帰テストを確認済みです。専門家のレビュー完了後、候補の測定可能性を定量化します。

[**v6レビュー判定基準**](v6/REVIEW_GUIDELINES.md) / [v5予備監査](v5/REPORT.md) / [v1〜v3.1図入り統合レポート](docs/RESEARCH_REPORT.md)

---

# TEM Nanoparticle Analyzer — v5 高密度Pt監査・人手レビュー

**[📊 図入り統合レポート：教師データ・Pt/Ag実測6枚・v1→v3比較・スケールバーOCR/検量](docs/RESEARCH_REPORT.md)**

**[v5 最新レポート：過剰除外の目視監査・レビューキュー・手動採否GUI（全画像埋込）](v5/REPORT.md)**

**[v4 最新レポート：実画像6視野の採用・除外・要確認と粒径分布](v4/REPORT.md)**

![v4の6枚一括比較](v4/docs/v4_all_six_audit.jpg)

> 実画像での検証は探索的。教師データの一部は合成画像、実画像3枚は弱教師。OCRからのnm換算には保留判定があり、独立した人手正解との照合は未実施。

[教師画像一覧](docs/TRAINING_DATA.md) / [スケールバー検量の詳細](v2/SCALE_CALIBRATION.md) / [実行手順](v2/README_GITHUB.md)

---

# TEM nanoparticle supervised segmentation prototype

**教師あり学習 / Random Forest + multi-scale image features + marker-controlled watershed**

これは動作確認済みの試作であり、**添付モデルの学習・検証データは擬似的に生成したTEM風画像**です。実際のTEM画像での性能は未検証です。実際のPt-TEMへの利用時は、代表画像で手動ラベルを作って再学習することを推奨します。

## 動作確認した結果

- 320×320 px、模擬TEM画像16枚を学習、独立した4枚で評価（異なる乱数シード、同一生成方式）。
- **画素単位**のDice平均 **0.913**、IoU平均 **0.839**。
- 模擬データの粒子中心との対応評価：Precision平均 **0.989**、Recall平均 **0.652**（完全に画像内に入った模擬粒子に限定、半径依存の中心距離マッチング）。特に**重なった粒子の分離不足**が主な課題。物理的な粒径誤差を示すものではありません。
- 擬似スケールとして 0.4 nm/pixel を指定した例も含む。この値は実測ではありません。
- `results/test_00/overview.png` に粒子輪郭と粒径ヒストグラム、`particles.csv` に各粒子の測定値。

## 必要環境

Python 3.10 以降（WSL/Windows/Linux）。`requirements.txt` に記載のライブラリ。

```bash
python -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python run_demo.py
```

**付属する学習済みモデルをそのまま使ってデモ解析**：

```bash
python tem_particle_ml.py predict \
  --image demo_data/test/images/test_00.png \
  --model trained_rf.joblib \
  --out results/new_test --nm-per-px 0.4
```

ブラウザGUI（任意）：

```bash
pip install gradio pandas
python app.py
```

GUIには添付画像の解析、スケール指定、閾値の調整、輪郭表示、CSVダウンロード機能があります。

## 実験TEMから教師あり学習を作る

次のように画像と**人間がラベルした2値マスク**を用意します。白=粒子、黒=背景。

```text
my_tem/
  train/
    images/ a.png  b.png  ...
    masks/  a.png  b.png  ...
  test/
    images/ z.png ...
    masks/  z.png ...
```

Fiji/ImageJ、napari、Labelme、CVAT などでアノテーション可能です。学習するのは**粒子と背景の意味的セグメンテーション**であり、Watershedでの分離は現在は教師なしの後処理です。強く重なった粒子を高精度で分離したい場合は、粒子ごとのインスタンス注釈（または中心点と境界の追加ラベル）が必要です。

```bash
python tem_particle_ml.py train \
    --images my_tem/train/images --masks my_tem/train/masks \
    --model pt_rf.joblib
python tem_particle_ml.py evaluate \
    --images my_tem/test/images --masks my_tem/test/masks \
    --model pt_rf.joblib --out real_test_metrics.json
python tem_particle_ml.py predict \
    --image my_real_tem.png --model pt_rf.joblib \
    --out my_real_result --nm-per-px 0.16
```

`0.16` は**説明用の架空の nm/pixel**です。実際には電子顕微鏡のメタデータ、スケールバーの検量などで得た値を指定してください。値が不明なら `--nm-per-px` を省略し、ピクセル単位だけで出力できます。

### 教師データと評価の注意

- **画像単位**でtrain/testを分離。同じ原画像からのタイルやほぼ同じ視野を両方に入れない（リーク回避）。
- Pt粒子でも粒径の小さいもの、密集、極低コントラスト、支持膜の濃淡、汚染を含めて注釈する。
- アノテーションの曖昧な粒子、支持膜の模様、明確な凝集部分は判定基準を決める。判定困難な粒子を必ず個数に含める必要はない。
- 画像周縁で切れた粒子は、集計から除外する。
- `diameter_px` は円相当径 `sqrt(4*A/pi)`、`feret_max_px` は最大Feret径の近似、`aspect_ratio` は長軸/短軸、`circularity` はCrofton周長から算出。
- 画像から粒子が見えない、強く重なる場合、2D投影像から元の単粒子サイズを一意に復元できない。

## ファイル一覧

- `tem_particle_ml.py`: 模擬データ生成、学習、評価、推論、粒径統計
- `app.py`: ローカルブラウザGUI
- `run_demo.py`: 一括実行デモ
- `trained_rf.joblib`: 模擬TEM学習済みモデル
- `demo_data/`: 模擬画像、二値教師マスク、真の生成中心
- `test_metrics.json`: テスト評価結果
- `results/test_0*/`: 輪郭付き画像、粒径分布、CSV等

## 関連する実験データ・参考例

- Gumbiowski et al., *Nanoscale Advances* (2023), https://doi.org/10.1039/d2na00781a 。DeepLabV3+による金属ナノ粒子領域セグメンテーション、粒子分離と計測。
- Subramanian et al., TEMExtraction (2021), https://github.com/CederGroupHub/TEMExtraction 。金ナノ粒子のインスタンスアノテーション131枚を提供するプロジェクト（データ・画像の外部取得が別途必要）。
- Kunwar S. Aaim, Nanoparticle TEM Image Segmentation: https://kunwarsaaim.github.io/projects/post_nanoparticle.html 。Pt BF-TEMの手動マスクでU-Net系を比較した研究。

**現段階は模擬画像による技術的PoCです。実測TEMの定量解析にそのまま使用できると保証するものではありません。**


## v3: Scale-bar OCR and calibrated particle diameters

[6 real-TEM scale bar detections and diagnostics](v2/SCALE_CALIBRATION.md) — [v3 implementation/GUI](v2/README_GITHUB.md).

The calibration pipeline reads the numeric label, locates its drawn bar, excludes the annotation, and maps image pixels to nm. High-resolution originals can be used to calibrate resized images, subject to a same-view correlation check. Short/ambiguous bars are **not** silently accepted. A reduced 15-tree model is included for the v3 GUI, but it is not a substitute for external real-TEM validation.
