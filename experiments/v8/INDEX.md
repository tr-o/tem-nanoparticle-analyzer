# v8 — 公開DM3実ファイルの読み込み・校正とHRTEM粒子抽出

> **実行日：2026-10-29 | 実ファイル2件でGitHub Actions実行成功**  
> **達成：DM3の生画素の取得、メタデータ校正、nm換算、輪郭出力、画像付き記録。**  
> **未達：専門家マスクに対する正解率の検証。DM4は実ファイル未検証。**

## 1. 取得した公開データ

元データ: [ngumb/ANTEMA — Testimages](https://github.com/ngumb/ANTEMA/tree/main/Testimages)。Gumbiowski et al., *Nanoscale Advances* (2023), [DOI:10.1039/d2na00781a](https://doi.org/10.1039/d2na00781a)。このリポジトリでは**元DM3バイナリを再配布せず**、CIで取得して解析する。

| 項目 | NP-TEM-Image1.dm3 | NP-TEM-Image2.dm3 |
|---|---:|---:|
| ファイルサイズ | 4,802,029 bytes | 4,802,031 bytes |
| フォーマットヘッダ | DM3 | DM3 |
| 画像データ | 1024×1024 int32 | 1024×1024 int32 |
| **元X/Yピクセル寸法** | **0.03833185 nm/px** | **0.04848602 nm/px** |
| 解析用縮小 | 768×768 | 768×768 |
| 解析X/Yピクセル寸法 | 0.05110914 nm/px | 0.06464803 nm/px |
| 実寸取得元 | DM3メタデータ | DM3メタデータ |

ファイルSHA-256:
- Image1: `dabc14ef6dc40d30060d067b148603c08152a2758b9ee8cbc140a2bdfb0cdb87`
- Image2: `9bf9ce564ac96b8874e001916721d6fdf0ce5214778dddb29aba495b6c199b5c`

**元データは32-bitの数値であり、Web掲載画像のスケールバーOCRは使用しない。** X/Y別にDM3軸の校正情報を取得し、縮小倍率を両軸それぞれに適用。測長に際して、校正のないデータから勝手にnmを作る処理は設けていない。

## 2. 重要：従来モデルはHRTEMに通用しなかった

明視野TEM風の模擬画像で教師あり学習したRandom Forestを、**そのまま初見のHRTEM像**へ適用したところ、格子縞や支持膜のノイズを大量に誤検出した。

| 従来モデル | Image1 | Image2 |
|---|---:|---:|
| 採用候補 | 1,436 | 1,364 |
| 要確認 | 854 | 613 |
| 除外 | 150 | 119 |
| 表示上の中央値 | 0.404 nm | 0.438 nm |
| **判断** | **失敗・粒径値採用不可** | **失敗・粒径値採用不可** |

### Image1 — 従来モデルの失敗を可視化
![DM3 Image1を明視野用RFで解析した結果。ノイズ周囲に大量の輪郭を誤生成](results/NP-TEM-Image1/overview.jpg)

### Image2 — 同じく失敗
![DM3 Image2を明視野用RFで解析した結果。粒子以外のノイズが検出されている](results/NP-TEM-Image2/overview.jpg)

**数値が計算できることと、粒子径を正しく測れたことは別。** この失敗を履歴に残し、以降はHRTEM専用手法を別系統として比較する。

## 3. 別経路：格子テクスチャ+暗い粒子エンベロープ

Gaborフィルタ群で局所的に優勢な周期方向を評価し、背景に対して暗い領域との交差から粒子を抽出。接触・重なり疑いは要確認、画像端は除外。現在は**教師ありモデルではなく探索的な画像処理方式**である。

| HRTEM専用方式 | Image1 | Image2 |
|---|---:|---:|
| 自動採用候補 | **41** | **106** |
| 要確認 | 18 | 11 |
| 除外 | 18 | 16 |
| 暫定的な採用径中央値 | 2.02 nm | 2.32 nm |

**これらの値もまだ真の粒子数・粒径精度ではない。** 独立した人手輪郭との照合前なので、最終測定値として使用しない。

### Image1 — HRTEM用の改良案

![Image1のDM3原画素、結晶テクスチャ判定、採否輪郭、暫定ヒストグラム](results_hrtem/NP-TEM-Image1/overview.jpg)

![Image1実データの無注記グレースケールプレビュー](results_hrtem/NP-TEM-Image1/raw_preview.png)

![Image1の周期構造Gabor特徴マップ](results_hrtem/NP-TEM-Image1/texture.png)

![Image1の局所暗部特徴マップ](results_hrtem/NP-TEM-Image1/darkness.png)

![Image1の採否色分け済み粒子輪郭](results_hrtem/NP-TEM-Image1/overlay.png)

### Image2 — HRTEM用の改良案

![Image2のDM3原画素、結晶テクスチャ判定、採否輪郭、暫定ヒストグラム](results_hrtem/NP-TEM-Image2/overview.jpg)

![Image2の無注記グレースケールプレビュー](results_hrtem/NP-TEM-Image2/raw_preview.png)

![Image2の周期構造Gabor特徴マップ](results_hrtem/NP-TEM-Image2/texture.png)

![Image2の局所暗部特徴マップ](results_hrtem/NP-TEM-Image2/darkness.png)

![Image2の採否色分け済み粒子輪郭](results_hrtem/NP-TEM-Image2/overlay.png)

## 4. 評価方法と現在の限界

- **Pixel calibration:** DM3のX/Y軸からnm/pixelを取得し、縮小後は `old_px/new_px` 倍して換算。形状が異方性なら面積を `A_px × sx × sy` で換算。
- **DM3/DM4 I/O:** RosettaSciIOの `rsciio.digitalmicrograph.file_reader`。データセットが複数なら明示的なdataset indexが必要。3Dならframeも指定。2D以外のスペクトル／4Dは誤って粒子解析へ流さない。
- **本当に必要な精度評価:** 同じ視野に手書き輪郭/インスタンスGTを作る。数値はIoU、インスタンスPrecision/Recall、直径MAE、重なり除外率、採用率の選択バイアスで判定。
- **光学・画像上の限界:** HRTEMでは位相コントラスト、格子縞方向、フォーカス、支持膜、試料厚みで輪郭が変わる。**Gaborの周期性はNPの存在を保証せず、実粒径との対応も未検証。**
- **対象外:** 今回のDM4実ファイル、異方的軸を持つ実DM、生の4D STEM、取得時の測定校正の独立確認。

**テスト:** 6件のDM3校正・入力選択の単体テストPASS。公開DM3ファイル2件のダウンロード・デコード・推論・画像/CSV生成がGitHub ActionsでPASS。

## 5. 再現・コード

- [GitHub Actions：実DM3でのCI実行](../../.github/workflows/dm3-real-data.yml)
- [RosettaSciIO対応のDM3/DM4リーダ](dm_io.py)
- [DM3の校正・一覧検査](inspect_dm.py)
- [従来RFを適用した失敗例](analyze_dm.py)
- [HRTEM向けのテクスチャ試験実装](hrtem_texture.py)
- [校正とdataset/フレーム選択の単体テスト](test_dm_io.py)
- [詳細テスト結果（基準モデル）](REPORT.md)
- [詳細テスト結果（HRTEM試験）](HRTEM_EXPERIMENT.md)

**各画像の数値・出力画像・候補CSV・校正JSONはすべてGitHub内に配置。** 外部の生DM3本体のみ再配布せず、出典へリンクする。

### 今後の優先度
1. **HRTEM専用の手動インスタンス正解マスク作成、独立視野で精度評価。**
2. マルチスケール検出を高解像度のまま実施し、細粒径のサンプリング影響を評価。
3. DM4の公開実ファイル1件で読込・校正検証。
4. GUIにDM3/DM4追加、複数視野の分布統合。


## 6. ローカルGUIからDM3/DM4を扱う

画像をアップロードして、DM3/DM4のデータセット一覧・X/Yピクセル校正・元の数値型を確認する実験用ブラウザGUIを追加。解析方式は **HRTEMテクスチャ** と **明視野RF** をユーザーが明示的に選択する。HRTEMを旧RFで自動解析することはしない。

```bash
pip install -r requirements.txt
pip install rosettasciio==0.15.0 gradio
python v8/app_dm.py
```

- [GUI実装コード](app_dm.py)
- 出力：粒子輪郭・粒径ヒストグラム・採用/要確認/除外・候補CSV
- **実DM3 2件をCIで検証済み、実DM4は未検証。** GUIそのもののエンドツーエンド実行は独立していない。

