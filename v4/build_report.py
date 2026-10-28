#!/usr/bin/env python3
"""Build a self-contained illustrated GitHub report from generated outputs."""
from pathlib import Path
import pandas as pd
import numpy as np
from PIL import Image,ImageDraw
import json, cv2
ROOT=Path(__file__).resolve().parents[1]
V4=ROOT/'v4';OUT=V4/'docs';OUT.mkdir(parents=True,exist_ok=True)
names=['web_image_2bed876c2a14_500','web_image_9828c4ba32bc_500','web_image_6af295ebd363_500','web_image_b9ecc5092cc1_500','web_image_82853817b188_500','web_image_8222294b2379_500']
short=['Pt-1: high density','Pt-2: medium density','Pt-3: medium density','Ag-1: isolated','Ag-2: noisy background','Ag-3: slight contacts']
old_dirs=[names[0],'Pt_reference',names[2],'Ag_isolated',names[4],names[5]]
imgs=[];rows=[]
for i,(name,title,old) in enumerate(zip(names,short,old_dirs)):
    v4=V4/'results'/name
    result=json.loads((v4/'summary.json').read_text())
    oldrow=json.loads((ROOT/'v3_calibration'/old/'summary.json').read_text())
    new_src=Image.open(v4/'overview.png').convert('RGB')
    new_src.thumbnail((1250,440));new_src.save(OUT/f'{name}_overview.jpg',quality=72,optimize=True)
    src=(ROOT/'v3_calibration'/old/'overview.png')
    if src.exists():
        old_img=Image.open(src).convert('RGB');old_img.thumbnail((950,350));old_img.save(OUT/f'{name}_v3.jpg',quality=57,optimize=True)
    # for a compact side-by-side gallery, focus on the contour panels
    raw=Image.open(v4/'decision_overlay.png').convert('RGB').resize((430,430),Image.Resampling.LANCZOS)
    imgs.append((title,raw))
    rows.append(dict(id=name,view=title,old_accept=oldrow['accepted']+oldrow['split_touching'],
                     new_accept=result['accepted'],isolated=result['counts'].get('accepted_isolated',0),
                     touching=result['counts'].get('accepted_touching',0),
                     resolved=result['counts'].get('accepted_resolved',0),
                     review=result['review'],reject=result['rejected'],calibration=result['scale_status'],nm_per_px=result['nm_per_px'],
                     diameter_nm=result['median_diameter_nm'],diameter_px=result['median_diameter_px']))
# montage with text headers and each color-coded overlay (postprocessing derived from vendor image)
out=Image.new('RGB',(3*446,2*474),'white');draw=ImageDraw.Draw(out)
for j,(title,im) in enumerate(imgs):
    x=(j%3)*446;y=(j//3)*474
    draw.text((x+12,y+8),title,fill=(20,20,20))
    out.paste(im,(x+8,y+31))
out.save(OUT/'v4_all_six_audit.jpg',quality=77,optimize=True)
# detailed crop for hard dense Pt
img=Image.open(ROOT/'real_tests/resized_inputs'/f'{names[0]}.png').convert('RGB')
seg=Image.open(V4/'results'/names[0]/'decision_overlay.png').convert('RGB')
box=(40,85,280,300)
a=img.crop(box).resize((480,430))
b=seg.crop(box).resize((480,430))
detail=Image.new('RGB',(980,478),'white');d=ImageDraw.Draw(detail)
d.text((10,6),'Original TEM crop (Pt dense)',fill='black');d.text((500,6),'v4: green/blue/purple accepted; orange review; red rejected',fill='black')
detail.paste(a,(10,31));detail.paste(b,(500,31));detail.save(OUT/'pt1_zoom_audit.jpg',quality=83,optimize=True)
pd.DataFrame(rows).to_csv(V4/'counts_v3_vs_v4.csv',index=False)
bench=json.loads((V4/'synthetic_center_benchmark.json').read_text())['aggregated']
lines=[
'# TEM粒径解析 v4 — 過剰除外の改善・粒子中心再検出・採否の可視化',
'',
'> 2026-10-28 / 研究用プロトタイプ。**実測TEMの人手インスタンス正解は未作成**。このレポートの「採用数増加」は正解率・再現率の向上を意味しません。模擬データの精度と実験画像の探索結果を区別します。',
'',
'[統合レポート（v1〜v3.1）](../docs/RESEARCH_REPORT.md) · [ソース（v4）](tem_v4.py) · [ベンチマークコード](evaluate_holdout.py)',
'',
'## 1. 6視野の採否をすべて画像で確認',
'',
'色：**緑＝孤立粒子を採用、シアン＝接触分離を採用、紫＝密集塊から再分離して条件付き採用、橙＝要確認、赤＝除外**。橙は粒径ヒストグラム・CSV採用集計に含めません。',
'',
'![Pt・Ag6枚の色分け採否マップ](docs/v4_all_six_audit.jpg)',
'',
'### 特に困難な高密度Ptの拡大',
'',
'![高密度Ptの拡大：原画像と色分け輪郭](docs/pt1_zoom_audit.jpg)',
'',
'## 2. v3.1 と v4 の集計',
'',
'| 視野 | v3.1採用 | v4採用 | 内訳：孤立 / 接触 / 再分離 | v4要確認 | v4除外 | スケール状態 |',
'|---|---:|---:|---|---:|---:|---|'
]
for row in rows:
    lines.append(f"| {row['view']} | {row['old_accept']} | **{row['new_accept']}** | {row['isolated']} / {row['touching']} / {row['resolved']} | {row['review']} | {row['reject']} | {row['calibration']} |")
lines+=['',
'**重要：v4は大きな連結領域を多数の候補に分割するため、候補総数そのものがv3と異なります。** 候補の採用率をバージョン間で単純比較できません。高密度Ptは34→192個の自動採用になりましたが、さらに916候補は**未採用・要確認**です。現段階で完全自動化の達成とは主張しません。',
'',
'## 3. 解析画像：v3.1とv4の比較',
'']
for row in rows:
    name=row['id'];lines+= [
        f"### {row['view']}",
        f"**v3.1**（旧版、採用{row['old_accept']}）",
        f"![{row['view']} v3.1 輪郭とヒストグラム](docs/{name}_v3.jpg)",
        f"**v4**（新しい採否理由、採用{row['new_accept']}・要確認{row['review']}）",
        f"![{row['view']} v4 原画像、採否輪郭、粒径分布](docs/{name}_overview.jpg)",
        ''
    ]
lines +=[
'## 4. アルゴリズムの変更点',
'',
'1. **画像ごとに孤立粒子の代表直径を推定。** LoG/局所暗点を一律3 pxで分割しない。これにより大きなAg単粒子内部の濃淡を複数粒子と誤認しにくくなった。',
'2. **不足分割の再探索。** 十分大きく、凹凸・細長さのある連結領域に限り、局所暗点の中心を追加し、マーカー制御Watershedを再実行。',
'3. **強制除外より「要確認」。** 境界が不確かな粒子は橙で保持してレビューCSVへ出す。従来の非円形・凹形状だけで大量除外する規則を置き換える。',
'4. **再分離粒子は厳しい採用条件。** 円形度≥0.80、solidity≥0.89、長短軸比≤1.4、SNR≥2、画素分類確率≥0.77、隣接中心距離/直径≥0.80、隣接粒子間の明るい谷≥0.05、かつ径が孤立粒子代表径の1.7倍以下に限り紫で採用。それ以外は橙のレビューへ。**この判定は真の重なりなしを保証しない**。',
'5. **nm換算はv3の機能を保持。** OCRでスケール値を読みバー長を測定、元画像1000px→解析500pxの比率を転送する。バーの短いPt-1は物理単位を保留し、pxのみを出力。',
'',
'採否の内訳や除外理由、中心座標、局所コントラスト、モデル確率、隣接中心距離、明るさ谷の深さは `particles_all.csv` に保持。**「要確認」は測定値の集計から除く。**',
'',
'## 5. 独立した模擬TEM4枚に対する退行テスト',
'',
'学習に使用していない**人工生成TEM**4枚の合成中心328点について、ハンガリアン割当で最大 `max(4.5 px, 0.75×生成半径)` 内の予測中心と1対1対応させた。これは実像精度の検証ではなく、**模擬生成方式での中心検出の退行テスト**。',
'',
'| 指標 | v3.1 | v4 |',
'|---|---:|---:|',
 f"| 対応する中心 | {bench['v3']['tp']}/328 | **{bench['v4']['tp']}/328** |",
 f"| この条件でのPrecision | {bench['v3']['precision']:.3f} | {bench['v4']['precision']:.3f} |",
 f"| この条件でのRecall | {bench['v3']['recall']:.3f} | {bench['v4']['recall']:.3f} |",
'',
'模擬画像の真の中心には、重なりで画像から見えない粒子も含まれる。中心照合はインスタンス輪郭精度を測っていない。v4の改良による有意な性能改善を主張できるデータではない。',
'',
'## 6. データ来歴・再現方法・限界',
'',
'- Ptの3画像：[nanoComposix 5 nm Platinum Nanoparticles](https://nanocomposix.com/products/5-nm-platinum-nanoparticles)。Agの3画像：[nanoComposix 10 nm Silver Nanospheres](https://nanocomposix.com/products/10-nm-silver-nanospheres)。メーカーの図の二次利用・再配布権を保証しない。元データは出典先を参照。',
'- **v2/3/4モデルは模擬16枚+実画像3枚の弱教師データで訓練した15本のExtraTrees軽量モデル**を使用。Pt-2、Ag-1、Ag-2の3視野は学習にも含まれるので独立評価ではない。',
'- 実画像の判定結果には独立した人手正解マスクがない。自動的な精度改善は未証明。今後はPt-1の一部を専門家が孤立/接触/重なり/非粒子とラベルし、採用し過ぎ・除外し過ぎを同時評価する必要がある。',
'- v4が行うのは**再判定・追加の中心分離**で、独立した新しい教師ありインスタンス学習ではない。スケールバーOCRは右下以外を網羅していない。',
'',
'### 再現コマンド',
'',
'```bash',
'pip install -r requirements.txt',
'pip install pytesseract  # OCRでは別途OS側にtesseractが必要',
'python v4/tem_v4.py --image path/to/tem_500.png \\',
'   --scale-reference path/to/same_field_1000.png \\',
'   --model v2/model_rf_real_weak_portable.joblib \\',
'   --out v4/results/my_test',
'python v4/evaluate_holdout.py  # 模擬4枚：追加モデル学習を要求しない',
'```',
'',
'最終成果物はGitHubの本レポートと、再現可能なコード。ZIPは配布しない。',
]
(V4/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
print('wrote',V4/'REPORT.md','images',len(rows)*2+2)
