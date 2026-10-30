# v10 — 実測HRTEMの正解マスクで測る、検出精度と過剰除外

> **判定：実測GT評価は未完了。** 人手GTで評価していないスコアは精度改善の証拠としない。

## 1. 今回の変更

- v9で失敗した固定DryadファイルIDを廃止し、REST APIの**公開済みversion・ファイル名一致・全ページ取得**で検証する。
- 最小級のAu 5 nm画像と人手マスクの組（約185 MB＋92 MB）だけを選択。**全33.7 GBは取得しない。**
- SHA-256とHDF5ヘッダを照合。ファイル名・取得先・サンプル番号を実行記録に保存する。
- HDF5の `images` / `labels` の対応、512×512画像、画像数、非有限値やラベル値を照合する。
- Dice / IoU / 画素Precision / Recallに加え、IoU 0.5で対応付けた**連結成分の検出精度**と対応した径のMAE（px）を測る。
- GTは**モデル学習や閾値調整に一切使わない**。v8とv9の固定処理を同じ画像で比較。

## 2. 元データと実行状況

- 出典: [Sytwu et al., Dryad 10.7941/D1SP93](https://doi.org/10.7941/D1SP93)。Au / Ag / CdSeのHRTEMと人手セグメンテーション。
- 正解は1人のアノテータのラベル。立体粒子の真の輪郭とは限らない。
- テストに使用するのは **Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05** の Images / Labels ペア。

| ステップ | 状態 |
|---|---|
| 公開データ取得 | `failure` |
| HDF5とSHA-256検証 | `not_verified` |
| 人手GTによる評価 | `skipped` |

## 3. 実測GTベンチマーク

**未測定。** 実測HRTEMのGTマスクに対するDice・IoU・検出率はまだ得られていない。
次の画像はデータ取得の代わりになる合成テスト画像ではなく、**過去のDM3実画像での検出例**である。

![既存の実DM3のv8粒子候補（GTなし）](../v8/results_hrtem/NP-TEM-Image1/overview.jpg)

![別の実DM3のv8粒子候補（GTなし）](../v8/results_hrtem/NP-TEM-Image2/overview.jpg)

## 3B. EMPS実測TEM/SEM：教師ありRandom Forestと粒子別マスク

出典：[Yildirim & Cole, EMPS](https://github.com/by256/emps) — 465のTEM/SEM画像と、粒子ごとにIDを持つアノテーション。公開MITライセンス。

学習には公式 **train.csv** のみ、評価には **test.csv** のみ使用。異なる撮影モードを含むため、HRTEM専用性能と混同しない。

データ取得：`success` / 評価：`failure`。

**実画像・教師あり評価は未完了**。公開GitHubからの取得またはモデル実行が成功していない場合、架空のDiceを報告しない。

## 4. 評価の限界と今後の改良対象

1. **画像枚数と独立性:** Dryad側は最小ペアの固定seedによる最大8パッチ。パッチは同じ取得セッション由来の可能性がある。交差セッションの汎化評価ではない。
2. **連結成分の限界:** 人手のインスタンス別IDがないため、接触して1連結になった粒子は個々の粒子数として判定できない。ここでのinstance指標は連結成分の代理指標。
3. **径の単位:** このH5は処理済みパッチであり、尺度の独立したメタデータ照合をしていないので、直径誤差は**px単位**。元DM3の校正値を勝手に転用しない。
4. **学習への転用:** GTを使って学習する場合は、同一視野や同一撮影セッション由来のパッチがtrain/testに混ざらない分割が必要。**本ベンチマークは学習には使用しない。**
5. **検出モデルの採用:** 実測GTで改良が実証されない限り、v9を標準モデルへ切り替えない。

## 5. 再実行とコード

- [ファイル名照合と完全性検証付きDryad取得](fetch_dataset.py)
- [GTの画素・連結成分評価と重ね描画](benchmark.py)
- [8件の回帰テスト](test_v10.py)
- [GitHub Actions：公開データ取得・評価・画像レポート更新](../.github/workflows/v10-real-gt.yml)

```bash
pip install -r requirements.txt
pip install h5py requests
PYTHONPATH=v10 python -m unittest discover -s v10 -p "test_v10.py" -v
python v10/fetch_dataset.py --out /tmp/lbnl
python v10/benchmark.py --images /tmp/lbnl/Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05_Images.h5 --labels /tmp/lbnl/Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05_Labels.h5 --out v10/results_human
python v10/build_report.py
```

**方針：** 計測できた結果だけをGitHubへ記録し、解析画像は本文に直接埋め込む。元HDF5は容量のため再配布しない。
