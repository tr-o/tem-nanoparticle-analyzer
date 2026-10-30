#!/usr/bin/env python3
"""Generate image-embedded, evidence-calibrated GitHub report."""
import json,os,glob
from pathlib import Path
ROOT=Path(__file__).resolve().parent
stat=ROOT/'eval_status.json'
status=json.loads(stat.read_text()) if stat.exists() else {'download':'not_run','benchmark':'not_run'}
metrics=ROOT/'results_human/metrics.json'
lines=[
 '# v10 — 実測HRTEMの正解マスクで測る、検出精度と過剰除外',
 '',
 '> **判定：'+('実測GT評価を完了' if metrics.exists() else '実測GT評価は未完了')+'。** 人手GTで評価していないスコアは精度改善の証拠としない。',
 '',
 '## 1. 今回の変更',
 '',
 '- v9で失敗した固定DryadファイルIDを廃止し、REST APIの**公開済みversion・ファイル名一致・全ページ取得**で検証する。',
 '- 最小級のAu 5 nm画像と人手マスクの組（約185 MB＋92 MB）だけを選択。**全33.7 GBは取得しない。**',
 '- SHA-256とHDF5ヘッダを照合。ファイル名・取得先・サンプル番号を実行記録に保存する。',
 '- HDF5の `images` / `labels` の対応、512×512画像、画像数、非有限値やラベル値を照合する。',
 '- Dice / IoU / 画素Precision / Recallに加え、IoU 0.5で対応付けた**連結成分の検出精度**と対応した径のMAE（px）を測る。',
 '- GTは**モデル学習や閾値調整に一切使わない**。v8とv9の固定処理を同じ画像で比較。',
 '',
 '## 2. 元データと実行状況',
 '',
 '- 出典: [Sytwu et al., Dryad 10.7941/D1SP93](https://doi.org/10.7941/D1SP93)。Au / Ag / CdSeのHRTEMと人手セグメンテーション。',
 '- 正解は1人のアノテータのラベル。立体粒子の真の輪郭とは限らない。',
 '- テストに使用するのは **Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05** の Images / Labels ペア。',
 '',
 '| ステップ | 状態 |', '|---|---|',
 f'| 公開データ取得 | `{status.get("download","unknown")}` |',
 f'| HDF5とSHA-256検証 | `{status.get("integrity","unknown")}` |',
 f'| 人手GTによる評価 | `{status.get("benchmark","unknown")}` |',
 ]
if status.get('error'):
    lines+=['',f'> 外部データの取得または評価エラー：`{str(status["error"])[:400]}`。未測定のスコアは作成しない。']
lines+=['','## 3. 実測GTベンチマーク','']
if metrics.exists():
    res=json.loads(metrics.read_text());lines += [
      f'評価パッチ：{len(res["per_image"])}枚（インデックス {res["sample_indices"]}）。', '',
      '| 指標 | v8 Gabor+dark | v9 保守的フィルタ |','|---|---:|---:|']
    for title,key in [ ('非空画像の平均Dice','dice_mean_nonempty'),('非空画像の平均IoU','iou_mean_nonempty'),('連結成分Precision平均','component_precision_mean_nonempty'),('連結成分Recall平均','component_recall_mean_nonempty'),('空GTの誤検出画素数','blank_pred_positive_pixels')]:
        def fmt(x):return '—' if x is None else f'{x:.4f}' if isinstance(x,float) else str(x)
        lines +=[f'| {title} | {fmt(res["summary"]["v8"].get(key))} | {fmt(res["summary"]["v9"].get(key))} |']
    lines +=['','### 元HRTEMと手動GT、予測輪郭の対応','',
      '**黄＝GT、シアン＝予測**。赤青ずれのバグを避けるため、同一配列座標から輪郭を直接描画している。','']
    for f in sorted((ROOT/'results_human').glob('example_*.jpg')):
        lines +=[f'![実測HRTEM {f.stem}：原画像、人手GT、v8、v9の輪郭]({f.relative_to(ROOT).as_posix()})','']
    v8=res['summary']['v8']['dice_mean_nonempty'];v9=res['summary']['v9']['dice_mean_nonempty']
    if v8 is not None and v9 is not None:
        lines +=[f'**判定：** 非空GT Diceではv9がv8より'+('改善' if v9>v8 else '悪化' if v9<v8 else '同等')+f'（{v8:.3f} → {v9:.3f}）。この結果だけから未知撮影セッションへの汎化は主張しない。']
else:
    lines += ['**未測定。** 実測HRTEMのGTマスクに対するDice・IoU・検出率はまだ得られていない。',
              '次の画像はデータ取得の代わりになる合成テスト画像ではなく、**過去のDM3実画像での検出例**である。',
              '', '![既存の実DM3のv8粒子候補（GTなし）](../v8/results_hrtem/NP-TEM-Image1/overview.jpg)',
              '', '![別の実DM3のv8粒子候補（GTなし）](../v8/results_hrtem/NP-TEM-Image2/overview.jpg)']
# EMPS true per-instance labels are an independent public fallback when Dryad 401 blocks binary access.
emps_metrics=ROOT/'results_emps/metrics.json'
emps_status=ROOT/'emps_status.json'
ems=json.loads(emps_status.read_text()) if emps_status.exists() else {}
lines += ['', '## 3B. EMPS実測TEM/SEM：教師ありRandom Forestと粒子別マスク', '',
    '出典：[Yildirim & Cole, EMPS](https://github.com/by256/emps) — 465のTEM/SEM画像と、粒子ごとにIDを持つアノテーション。公開MITライセンス。',
    '', '学習には公式 **train.csv** のみ、評価には **test.csv** のみ使用。異なる撮影モードを含むため、HRTEM専用性能と混同しない。',
    '', f'データ取得：`{ems.get("acquire","not_run")}` / 評価：`{ems.get("evaluation","not_run")}`。', '']
if emps_metrics.exists():
    data=json.loads(emps_metrics.read_text());aggregate=data['aggregate']
    lines += ['### 正解マスクに対する定量結果', '',
         f'学習に使用した画像：{len(data["train_images"])}枚。未学習の公式test画像：{len(data["test_files"])}枚。', '',
         '| 指標 | 結果 |', '|---|---:|',
         f'| Pixel Dice | {aggregate["pixel"]["dice"]:.3f} |',
         f'| Pixel IoU | {aggregate["pixel"]["iou"]:.3f} |',
         f'| 連結成分のPrecision (IoU 0.5) | {aggregate["instance_connected"]["precision"]:.3f} |',
         f'| 連結成分のRecall (IoU 0.5) | {aggregate["instance_connected"]["recall"]:.3f} |',
         f'| Watershed分割後Precision (IoU 0.5) | {aggregate["instance_watershed"]["precision"]:.3f} |',
         f'| Watershed分割後Recall (IoU 0.5) | {aggregate["instance_watershed"]["recall"]:.3f} |',
         '', '### 実測画像・粒子ごとの正解輪郭・RF予測・確率マップ',
         '', '**黄＝粒子ID別の正解境界、シアン＝Watershed後の予測境界**。', '']
    for jpg in sorted((ROOT/'results_emps').glob('*.jpg')):
        lines += [f'![EMPS {jpg.stem}: 実測画像、人手インスタンスGT、RF予測、確率]({jpg.relative_to(ROOT).as_posix()})','']
    lines += ['輪郭が不一致の粒子は良好に見える例だけを選ばず含める。スケール情報を確認していないため**粒径誤差はpx単位**で報告。']
else:
    lines += ['**実画像・教師あり評価は未完了**。公開GitHubからの取得またはモデル実行が成功していない場合、架空のDiceを報告しない。']

lines += [
 '', '## 4. 評価の限界と今後の改良対象','',
 '1. **画像枚数と独立性:** Dryad側は最小ペアの固定seedによる最大8パッチ。パッチは同じ取得セッション由来の可能性がある。交差セッションの汎化評価ではない。',
 '2. **連結成分の限界:** 人手のインスタンス別IDがないため、接触して1連結になった粒子は個々の粒子数として判定できない。ここでのinstance指標は連結成分の代理指標。',
 '3. **径の単位:** このH5は処理済みパッチであり、尺度の独立したメタデータ照合をしていないので、直径誤差は**px単位**。元DM3の校正値を勝手に転用しない。',
 '4. **学習への転用:** GTを使って学習する場合は、同一視野や同一撮影セッション由来のパッチがtrain/testに混ざらない分割が必要。**本ベンチマークは学習には使用しない。**',
 '5. **検出モデルの採用:** 実測GTで改良が実証されない限り、v9を標準モデルへ切り替えない。',
 '', '## 5. 再実行とコード', '',
 '- [ファイル名照合と完全性検証付きDryad取得](fetch_dataset.py)',
 '- [GTの画素・連結成分評価と重ね描画](benchmark.py)',
 '- [8件の回帰テスト](test_v10.py)',
 '- [GitHub Actions：公開データ取得・評価・画像レポート更新](../.github/workflows/v10-real-gt.yml)',
 '', '```bash',
 'pip install -r requirements.txt',
 'pip install h5py requests',
 'PYTHONPATH=v10 python -m unittest discover -s v10 -p "test_v10.py" -v',
 'python experiments/v10/fetch_dataset.py --out /tmp/lbnl',
 'python experiments/v10/benchmark.py --images /tmp/lbnl/Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05_Images.h5 --labels /tmp/lbnl/Au_5nm_260kx_450e_Std_UTC_FFCorr_Team05_Labels.h5 --out experiments/v10/results_human',
 'python experiments/v10/build_report.py',
 '```', '',
 '**方針：** 計測できた結果だけをGitHubへ記録し、解析画像は本文に直接埋め込む。元HDF5は容量のため再配布しない。'
 ]
(ROOT/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(f'v10 report built: {len(lines)} lines; human metrics available: {metrics.exists()}')
