from pathlib import Path
import json
root=Path(__file__).resolve().parent
lines=['# HRTEM用の別経路 — 結晶格子テクスチャに基づく粒子候補抽出','',
'> **暫定的な探索結果。教師あり明視野モデルでの大量誤検出を受け、別アルゴリズムを試験したもの。正解マスク未照合。**','',
'## 旧モデルの失敗を記録','',
'旧明視野モデルが格子縞とノイズを粒子と誤認し、画像1で1,436候補・径中央値0.40 nm、画像2で1,364候補・径中央値0.44 nmとなった。**これらの値は測定結果として採用しない。**',
'', '## HRTEMテクスチャ方式','',
'Gaborフィルタ群の位相を組み合わせて局所的な周期縞の優勢方向を計算し、暗い粒子エンベロープと交差させる。サイズ下限は**今回の方式の検出条件**であって試料の物理的な下限を意味しない。',
'', '| Image | Accept | Review | Reject | Provisional median |', '|---|---:|---:|---:|---:|']
for p in sorted((root/'results_hrtem').glob('*/summary.json')):
    s=json.loads(p.read_text());med=s['median_diameter_nm'];med='—' if med is None else f'{med:.2f} nm'
    lines += [f"| {s['file']} | {s['accepted']} | {s['review']} | {s['rejected']} | {med} |"]
lines += ['']
for p in sorted((root/'results_hrtem').glob('*/summary.json')):
    name=p.parent.name;rel=p.parent.relative_to(root)
    lines += [f'### {name}','',f'![実DM3原画像、結晶テクスチャ、輪郭、ヒストグラム]({rel}/overview.jpg)','',
              f'![原画像]({rel}/raw_preview.png)','',f'![結晶周期性特徴マップ]({rel}/texture.png)','',
              f'![粒子周囲の暗いコントラスト特徴]({rel}/darkness.png)','',
              f'![採用・要確認・除外の輪郭]({rel}/overlay.png)','',
              f'[全候補CSV]({rel}/particles.csv) / [実行情報]({rel}/summary.json)','','']
lines += ['## 解釈','',
'- この方式は**教師あり学習済みモデルではなく**、HRTEM向けの物理的特徴に基づく探索的処理。',
'- 粒子数は候補数、粒径は採用候補の円相当径。真の精度・再現率や分布を示すものではない。',
'- 特に格子縞の方向・焦点・支持膜の構造で誤検出するため、独立した人手の正解と比較する必要がある。',
'- 元のDM3ピクセル校正に基づいてnm換算を行った。元データはGitHubに再配布しない。',
'', '[DM3インポート全体レポート](REPORT.md)']
(root/'HRTEM_EXPERIMENT.md').write_text('\n'.join(lines)+'\n')
