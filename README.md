# TEM Nanoparticle Analyzer

教師あり **Random Forest + 多尺度特徴量 + marker-controlled watershed** によるTEMナノ粒子の粒径解析プロトタイプ。

> **重要:** デモで使用した教師画像・マスクは**すべて人工生成した模擬TEM**です。実際のPt-TEM画像での精度は未評価です。論文中の平均粒径との一致を目標にはしていません。

![教師ありTEM粒径解析のワークフロー](docs/analysis_overview.jpg)

## 最初に

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_demo.py
# ブラウザGUI (任意)
pip install gradio pandas
python app.py
```

生成済み教師データは `demo_data/train/images` と `demo_data/train/masks`、独立テスト画像は `demo_data/test/` 以下です。**マスクは白が粒子、黒が背景**。元画像とマスクは同じベース名で対応します。

[画像・マスクの一覧](docs/TRAINING_DATA.md) · [公開TEMの参照ギャラリー](docs/REFERENCE_TEM.md) · [評価方法](docs/METHODS.md)

## 動作

- RFで多尺度Gaussian、LoG、局所コントラスト、輝度勾配などから**画素単位の粒子確率**を推定する（K-meansや閾値のみではない）。
- Watershedで接触領域を暫定分離する。**強い重なりは分離失敗しうる**。
- 円相当径、Feret最大径、円形度、アスペクト比、CSV、輪郭付き画像、ヒストグラムを出力。
- スケールが未確定の場合はpx単位のみで出力。デモの`0.4 nm/pixel`は架空の値。

## 実測TEMから再学習

```bash
python tem_particle_ml.py train --images real/train/images --masks real/train/masks --model pt_rf.joblib
python tem_particle_ml.py evaluate --images real/test/images --masks real/test/masks --model pt_rf.joblib --out real_metrics.json
python tem_particle_ml.py predict --image my_tem.png --model pt_rf.joblib --out results/my_tem --nm-per-px 0.16
```

※ `0.16` は説明用の仮定値。実際の校正値を入力してください。画像単位のtrain/test分離を徹底し、接触粒子・低コントラスト・支持膜の濃淡を含めて評価します。

## デモ精度（**模擬データのみ**）

320×320 px画像16枚で学習、別の4枚をテスト（同じ画像生成方式、異なるseed）。

| 指標 | 平均 |
|---|---:|
| 粒子領域 Dice | 0.913 |
| 粒子領域 IoU | 0.839 |
| 粒子中心 Precision | 0.989 |
| 粒子中心 Recall | 0.652 |

値は旧試作による実測実行結果であり、**現リポジトリ上の再生成・再学習後に必ず再測定してください**。Pixel Diceと粒子ごとの径の精度は別です。接触粒子の見落としが残っています。

## データの取り扱いと権利

`demo_data/`は本プロジェクトでプログラム生成した模擬データです。外部の研究機関・メーカーのTEM画像は、権利確認なしに教師データとして混入・再配布しません。`docs/REFERENCE_TEM.md`に元サイトへの参照とライセンス区分を記録しています。

関連研究: Gumbiowski et al. (2023), [Nanoscale Advances](https://doi.org/10.1039/D2NA00781A) / [ANTEMA](https://github.com/ngumb/ANTEMA)。

## 方針

まずデモを**再現可能な基準系**として確立し、その後実測Pt-TEMを手動注釈して再学習。将来的には接触粒子に対するインスタンス教師データを追加する。
