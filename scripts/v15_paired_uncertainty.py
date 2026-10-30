#!/usr/bin/env python3
"""Repeat v15-v13 paired image-level bootstrap on persisted unseen EMPS tests."""
import json,sys,argparse
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0,str(Path(__file__).resolve().parent))
from v14_bootstrap_uncertainty import bootstrap

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--metrics',default='v15/results/metrics.json')
    parser.add_argument('--outdir',default='v15')
    args=parser.parse_args()
    folder=Path(args.outdir);d=json.loads(Path(args.metrics).read_text())
    summary,deltas=bootstrap(d['per_image'],old='v13_28',new='v15_96',iterations=20000,seed=20261115,return_distribution=True)
    (folder/'results/bootstrap_ci.json').write_text(json.dumps(summary,indent=2)+'\n')
    fig,ax=plt.subplots(figsize=(8,4))
    ax.hist(deltas,bins=60)
    ax.axvline(0,linestyle='--',label='No difference')
    ax.axvline(summary['observed_delta_percentage_points'],label='Observed increase')
    ax.set(xlabel='v15 (96 train images) − v13 (28) F1 in percentage points',ylabel='20,000 paired image resamples',title='Same EMPS dataset; held-out 20 test images')
    ax.legend();fig.tight_layout();fig.savefig(folder/'results/bootstrap_ci.jpg',dpi=140);plt.close(fig)
    lo,hi=summary['interval_95_percentile_pp']
    lines=[
        '# v15 — 教師96枚の改善幅：画像単位の不確実性', '',
        '> 実測テスト20視野を単位とするペア・ブートストラップ20,000回。粒子を独立の標本として扱わない。', '',
        '![新しい20画像での教師28枚と96枚のF1差のブートストラップ分布](results/bootstrap_ci.jpg)', '',
        '| 項目 | 数値 |','|---|---:|',
        f'| 観測したmicro F1改善 | +{summary["observed_delta_percentage_points"]:.2f}ポイント |',
        f'| 95% percentile区間 | {lo:+.2f} ～ {hi:+.2f}ポイント |',
        f'| 画像単位復元抽出 | {summary["resamples"]:,}回、seed {summary["seed"]} |', '',
        '**解釈：** この20視野ではF1改善が見られ、今回の再標本化区間も0を上回った。ただしEMPSの撮影条件間の相関と、v10〜v14での探索歴は扱えていない。',
        '', '再標本化で差がプラスだった割合は '+f'{summary["positive_resample_fraction"]:.3f}'+
        '。これはp値でも、他装置での改善確率でもない。', '',
        '![人手GT（黄色）と予測輪郭（シアン）、教師28枚と96枚の比較](results/39b0dc1f52.jpg)', '',
        '**注意：** 評価単位は2Dマスクであり、粒径MAEはIoU≥0.5で対応できた粒子のみを対象とする。真のサイズ誤差と混同しない。', '',
        '[本体レポート](REPORT.md) / [保存した各視野データ](results/metrics.json) / [再現コード](../scripts/v15_paired_uncertainty.py)']
    (folder/'UNCERTAINTY.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary,indent=2))
