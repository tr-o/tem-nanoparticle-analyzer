#!/usr/bin/env python3
"""Paired *image-level* bootstrap for v14 frozen-test F1 contrast.

Exploratory uncertainty; NOT a p-value for universal model superiority.
The official EMPS images may share acquisition domains, so confidence
intervals do not quantify truly independent microscope sessions.
"""
import argparse,json
from pathlib import Path
import numpy as np

def F1(a):
    tp,fp,fn=a
    return 2*tp/max(1,2*tp+fp+fn)

def bootstrap(rows,old='v13',new='v14',iterations=10000,seed=20261030,return_distribution=False):
    if len(rows)<2:raise ValueError('Need two or more images for bootstrap')
    data=np.array([[q[k][name] for k in (old,new) for name in ('tp','fp','fn')] for q in rows],dtype=np.int64)
    rng=np.random.default_rng(seed)
    diffs=np.empty(iterations,float)
    for i in range(iterations):
        r=data[rng.integers(len(rows),size=len(rows))].sum(axis=0)
        diffs[i]=100*(F1(r[3:])-F1(r[:3]))
    lo,hi=np.percentile(diffs,[2.5,97.5]);base=data.sum(axis=0)
    summary={'n_images':len(rows),'observed_delta_percentage_points':100*(F1(base[3:])-F1(base[:3])),
            'paired_bootstrap_mean_pp':float(diffs.mean()),'interval_95_percentile_pp':[float(lo),float(hi)],
            'resamples':iterations,'seed':seed,'positive_resample_fraction':float(np.mean(diffs>0))}
    return (summary,diffs) if return_distribution else summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--metrics',default='v14/results/metrics.json');p.add_argument('--out',default='v14/results/bootstrap_ci.json');p.add_argument('--plot',default='v14/results/bootstrap_ci.jpg');p.add_argument('--report',default='v14/UNCERTAINTY.md')
    args=p.parse_args();d=json.loads(Path(args.metrics).read_text());out,draws=bootstrap(d['per_image'],return_distribution=True)
    Path(args.out).parent.mkdir(parents=True,exist_ok=True)
    Path(args.out).write_text(json.dumps(out,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(8,4))
    ax.hist(draws,bins=60)
    ax.axvline(0,linestyle='--',label='No difference')
    ax.axvline(out['observed_delta_percentage_points'],label='Observed change')
    ax.set(xlabel='v14 − v13 instance micro F1 (percentage points)',ylabel='Paired bootstrap resamples',title='20 previously unseen EMPS images; resample WHOLE images')
    ax.legend()
    fig.tight_layout();fig.savefig(args.plot,dpi=145);plt.close(fig)
    lo,hi=out['interval_95_percentile_pp']
    md=f'''# v14 — 20画像の差の不確実性（ペア・ブートストラップ）

> **探索的な記述統計。** 新規20枚のテスト画像を単位に、1万回ペアで復元抽出。画像内の数百粒子を独立サンプルとして扱わない。

![v14-v13の画像単位ブートストラップ差の分布](results/bootstrap_ci.jpg)

|指標|値|
|---|---:|
|実測micro F1差（v14−v13）|{out['observed_delta_percentage_points']:+.2f} ポイント|
|95% percentile区間|{lo:+.2f} ～ {hi:+.2f} ポイント|
|新規評価画像|{out['n_images']} 枚|
|ブートストラップ反復|{out['resamples']:,} 回（seed={out['seed']}）|

**結論：区間が0を大きくまたぐ。** 採用基準「F1が下がったら標準置換しない」ではNO-GOだが、20枚でv14の一般性能が低いことまで統計的に確定したわけではない。

再標本化で差がプラスになった比率は{out['positive_resample_fraction']:.3f}。これは**モデル改善のベイズ事後確率でも、有意性のp値でもない**。

## 性能の失敗例も確認する

![EMPS人手GT（黄）とモデル予測（シアン）の比較](results/391ef00939.jpg)

**制限：** EMPSは同一データセット内のTEM/SEM混合。撮影セッションや機種間の依存性を考慮していないため、この区間は研究室間の外挿に使えない。ユーザーが実際に測りたいPtナノ粒子DM3に対する誤差ではない。

[再現スクリプト](../scripts/v14_bootstrap_uncertainty.py) / [元のv14評価](REPORT.md) / [全件数値](results/bootstrap_ci.json)
'''
    Path(args.report).write_text(md,encoding='utf-8')
    print(json.dumps(out,indent=2))
