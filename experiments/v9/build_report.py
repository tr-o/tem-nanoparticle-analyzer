from pathlib import Path
import json
root=Path(__file__).resolve().parent
status_path=root/"status.json"
status=json.loads(status_path.read_text()) if status_path.exists() else {}
real=root/"results_human/metrics.json"
lines=[
"# v9 — HRTEM精度改善：人手正解マスクとの直接比較",
"",
"> 実験TEMでの精度は **独立した人手正解と比較した場合だけ** 報告。人工データや採用数の増減を精度の証拠にしない。",
"",
"## 研究データ",
"",
"- 従来v8では公開ANTEMA DM3のHRTEM粒子領域抽出は探索的で、独立ラベルはなかった。",
"- 新たに **LBNL/Sytwu et al. のDryad HRTEMマスク**を独立評価に採用：",
"  [10.7941/D1SP93](https://doi.org/10.7941/D1SP93)。Au 5 nmの画像と人手マスクのHDF5をCIで外部取得する。",
"- v8：Gabor結晶周期性＋暗部エンベロープ。v9候補：より強い結晶周期性条件に加え、細長い擬似粒子・画像端候補を保守的に除外。",
"- **v9の後処理条件はこの人手GTに合わせて最適化していない。**",
"- 人手GTは同一のHDF5から取得、画像/マスク配列のサイズが違えばエラー停止。",
"",
"## 旧版の実DM3での課題",
"",
"![実DM3のv8 HRTEMベースライン：原画素・周期性・輪郭・粒径分布](../v8/results_hrtem/NP-TEM-Image1/overview.jpg)",
"",
"![別視野のv8ベースライン](../v8/results_hrtem/NP-TEM-Image2/overview.jpg)",
"",
"**注意：** 上記のv8採用数41/106および粒径中央値はGT未照合であり、精度が確認された値ではない。",
"",
"## 人手マスクに対する独立評価",
"",
]
if real.exists():
 d=json.loads(real.read_text());a,b=d["v8"],d["v9"]
 lines += [
 f"実HRTEM **{len(d['indices'])}視野**を検証。人手GTからマスクDice/IoUを計算した。",
 "",
 "| 指標 | v8 | v9 |","|---|---:|---:|",
 f"| 粒子あり視野の平均Dice | {a['mean_nonblank_dice']} | {b['mean_nonblank_dice']} |",
 f"| 粒子あり視野の平均IoU | {a['mean_nonblank_iou']} | {b['mean_nonblank_iou']} |",
 f"| 空背景の偽陽性画素合計 | {a['blank_false_positive_pixels']} | {b['blank_false_positive_pixels']} |",
 "",
 "これらは**領域マスクの一致率**であり、接触粒子ごとのインスタンスPrecision/Recallや粒径MAEではない。",
 ""]
 da=a["mean_nonblank_dice"];db=b["mean_nonblank_dice"]
 if da is not None and db is not None:
  if db>da:
   lines += ["**判定：** この評価サンプルではv9のDiceが改善。ただし他試料・撮影条件への汎化は未評価。",""]
  else:
   lines += ["**判定：** v9は実人手GTでv8を上回らず。**自動的な本番置換は見送り**。",""]
 for p in sorted((root/"results_human").glob("patch_*.jpg")):
  lines += [f"![原HRTEM・手動GT・experiments/v8/v9重ね合わせ：{p.stem}](results_human/{p.name})",""]
else:
 lines += [
  "**未検証：CIで独立マスク評価が完了していない。実画像のDice・IoU改善はまだ主張しない。**",
  f"公開データ取得：\`{status.get('download','not_run')}\` / 評価：\`{status.get('benchmark','not_run')}\`。",
  "Dryad側のアクセス制限やHDF5フォーマットに問題があれば、そのまま失敗を記録する。",""]
lines += [
"## 再現方法",
"",
"- [精度評価コード](real_gt_benchmark.py)：HDF5を読み、GTと同じ座標で2方式の輪郭を比較。",
"- [GitHub Actions（公開HDF5取得と解析）](../.github/workflows/v9-human-gt.yml)。",
"- 元HDF5は巨大なためGitHubでは再配布せず、派生した図・計算値・出典を記録。",
"- **人手GTは1人のアノテータによるラベル**であり、顕微鏡の真の立体的粒子境界とは限らない。",
"- 今後の課題：大径/小径・接触粒子の層別指標、異なる撮影セッションでの再検証、過剰除外の定量評価。",
]
(root/"REPORT.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
print("v9 report written, human GT evaluated:",real.exists())
