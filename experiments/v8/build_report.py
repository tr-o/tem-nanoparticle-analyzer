"""Build Markdown report *after real .dm3 inference*, not mocked output."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parent
report=ROOT/'REPORT.md'
items=[]
for p in sorted((ROOT/'results').glob('*/summary.json')):
    info=json.loads(p.read_text())
    items.append((p.parent,info))
rows=['# DM3/DM4生画像対応 — 公開TEM実データ検証','',
'> **実行結果（GitHub Actions生成）**。これは実験TEMからの暫定推論であり、独立正解マスクによる精度検証ではありません。',
'', '## 元データと方法', '',
'- 公開DM3画像: [Gumbiowski et al. ANTEMA Testimages](https://github.com/ngumb/ANTEMA/tree/main/Testimages)。実DM3は再配布せず、実行時に取得。',
'- 形式読取: RosettaSciIO / `rsciio.digitalmicrograph.file_reader`。生画素は保存したまま、解析用にロバスト正規化。',
'- 元のDM3タグにX/Yの実空間校正がある場合のみnmへ変換。無ければpx単位で止める。',
'- 既存の教師ありRandom Forest（模擬TEM学習）を追加学習なしで適用。**モデルはこのDM3に対して未検証**。',
'- 輪郭の緑=自動採用、橙=要確認、赤=除外。重なり疑いを自動集計に入れない。',
'- 画像端の粒子は除外。縮小時はx/yのnm/pxを倍率で再計算。',
'', '## 実行一覧', '',
'| DM3 file | Original size | Analysis size | Calibration | Accepted | Review | Rejected | Median |',
'|---|---|---|---|---:|---:|---:|---|']
for folder,s in items:
    calibrated=s['calibration_status']=='calibrated'
    med=f"{s['median_equivalent_diameter_nm']:.2f} nm" if calibrated and s['median_equivalent_diameter_nm'] is not None else (f"{s['median_equivalent_diameter_px']:.2f} px" if s['median_equivalent_diameter_px'] is not None else '—')
    rows.append(f"| {folder.name} | {s['shape_original']} | {s['shape_analysis']} | {s['calibration_status']} | {s['accepted']} | {s['review']} | {s['rejected']} | {med} |")
rows+=['','## 画像別の輪郭と粒径分布','']
for folder,s in items:
    rel=folder.relative_to(ROOT)
    rows+= [f"### {folder.name}", '',f"![{folder.name} 実DM3から生成した生画像・粒子分類輪郭・分布]({rel}/overview.jpg)",'',
            f"![{folder.name} 元画素からのグレースケールプレビュー]({rel}/raw_preview.png)", '',
            f"![{folder.name} 教師あり粒子確率マップ]({rel}/probability.png)",'',
            f"![{folder.name} 候補粒子を色分けした輪郭画像]({rel}/overlay.png)",'',
            f"- 元ファイルSHA256: `{s['sha256']}`", 
            f"- 実寸校正: x={s['x_nm_per_px']} nm/px, y={s['y_nm_per_px']} nm/px; status={s['calibration_status']}",
            f"- [候補全件CSV]({rel}/particles_all.csv) / [採用候補CSV]({rel}/particles_accepted.csv) / [取得メタデータ]({rel}/source_metadata.json)", '']
rows += ['## 信頼性と課題','',
'- **本結果の粒子数・粒径中央値はモデルによる候補推定であり、正解率や実測粒径精度を示さない。**',
'- DM3内のデータが複数ある場合、解析対象dataset indexを実行ログに明記すること。スペクトルや回折像をナノ粒子像と混同しない。',
'- 複数フレーム/傾斜系列の3Dデータは必ずフレーム番号を指定する。',
'- 本番の校正にはDigitalMicrographのタグを独立に確認する。非正方ピクセルでは面積に `sx*sy` を使う。',
'- 定量的な精度評価には画像と同じ視野の人手インスタンス正解マスクが必要。',
'', '## 再実行', '', '```bash',
'pip install -r requirements.txt', 'pip install rosettasciio==0.15.0',
'python experiments/v8/inspect_dm.py example.dm3 --out experiments/v8/inspect.json',
'python experiments/v8/analyze_dm.py --image example.dm3 --dataset-index 0 --model models/synthetic_rf.joblib --output experiments/v8/results/example',
'```','',
'GitHub Actions: [DM3 real image validation workflow](../.github/workflows/dm3-real-data.yml)',
'', '出典: Gumbiowski et al., Nanoscale Advances 2023, DOI: [10.1039/d2na00781a](https://doi.org/10.1039/d2na00781a).']
report.write_text('\n'.join(rows)+'\n',encoding='utf-8')
print('Wrote',report,'images=',4*len(items),'datasets=',len(items))
