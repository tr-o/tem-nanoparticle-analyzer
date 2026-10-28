from pathlib import Path
import sys,json,csv
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
V2=ROOT/'v2';resultdir=V2/'results'
images={
'web_image_2bed876c2a14_500':'Pt-1 | dense',
'web_image_9828c4ba32bc_500':'Pt-2 | medium',
'web_image_6af295ebd363_500':'Pt-3 | medium',
'web_image_b9ecc5092cc1_500':'Ag-1 | isolated',
'web_image_82853817b188_500':'Ag-2 | noisy',
'web_image_8222294b2379_500':'Ag-3 | sparse'}
oldname={
'web_image_2bed876c2a14_500':'pt_img1_500',
'web_image_9828c4ba32bc_500':'pt_img2_500',
'web_image_6af295ebd363_500':'pt_img3_500',
'web_image_b9ecc5092cc1_500':'web_image_b9ecc5092cc1_500',
'web_image_82853817b188_500':'web_image_82853817b188_500',
'web_image_8222294b2379_500':'web_image_8222294b2379_500'}
rows=[]
fig,axs=plt.subplots(6,3,figsize=(12.2,22),gridspec_kw={'width_ratios':[1,1,1]})
for i,(name,label) in enumerate(images.items()):
    old=ROOT/'real_tests'/oldname[name]
    new=resultdir/name
    d=json.loads((new/'summary.json').read_text())
    base=json.loads((old/'summary.json').read_text())
    rows.append({'image':label,'subset':'weak train' if name in {'web_image_9828c4ba32bc_500','web_image_b9ecc5092cc1_500','web_image_82853817b188_500'} else 'unseen',
                 'v1_raw':base['n_measured'],'v2_raw':d['raw_instances'],'v2_accepted':d['accepted']+d['split_touching'],
                 'v2_direct':d['accepted'],'v2_split':d['split_touching'],'v2_rejected':d['rejected'],'v2_median_d_px':d['median_diameter_px']})
    for j,f in enumerate([ROOT/'real_tests/resized_inputs'/f'{name}.png',old/'overlay.png',new/'overlay.png']):
        im=Image.open(f)
        axs[i,j].imshow(im,cmap='gray' if j==0 else None)
        axs[i,j].axis('off')
        if j==0:axs[i,j].set_ylabel(label)
        axs[i,j].set_title(['Original',f'v1 raw N={base["n_measured"]}',f'v2 kept={d["accepted"]+d["split_touching"]} / rejected={d["rejected"]}'][j],fontsize=10)
fig.suptitle('TEM analysis: original vs v1 baseline vs v2 real weak supervision\nGreen: accepted, cyan: plausible contact split, red: discarded',fontsize=13)
fig.tight_layout(rect=(0,0,1,.965));fig.savefig(V2/'comparison_6_images.jpg',dpi=145);plt.close(fig)
df=pd.DataFrame(rows);df.to_csv(V2/'comparison_counts.csv',index=False)
header='''# Real TEM v2: supervised adaptation and conservative particle selection

**Evaluation status: exploratory. No independent manual ground truth on six experimental TEM images.**

- v1: synthetic-trained Random Forest, conservative circularity-only filter in separate CSV.
- v2: ExtraTrees classifier trained on **16 synthetic + 3 weakly labeled real images** (Ag isolated, Ag noisy, Pt medium). Pixel labels: 255 particle cores, 0 confident background, 128 ignore uncertain boundaries. These real labels are **weak assisted**, not expert manually validated ground truth.
- New: metadata/scale-label bottom-right region excluded, context/contrast-based particle rejection, marker watershed on distance peaks for contacts, explicit rejected reasons for ambiguous shapes.
- Image size: all 500 x 500; diameter in pixels; no physical-unit calibration. Counts are *algorithm decisions*, not particle-detection recall. No comparison to published diameters is intended.
- Real-image data source: [Pt 5 nm](https://nanocomposix.com/products/5-nm-platinum-nanoparticles) and [Ag 10 nm](https://nanocomposix.com/products/10-nm-silver-nanospheres). External images may have copyright restrictions; check rights before redistribution. Original images are not automatically considered public domain.

![Six field comparison](comparison_6_images.jpg)

## Image-wise counts

| Image | Model training | v1 raw | v2 raw | v2 accepted | v2 contact splits accepted | v2 rejected | median d (px) |
|---|---|---:|---:|---:|---:|---:|---:|
'''
for row in rows:
    header+=f"| {row['image']} | {row['subset']} | {row['v1_raw']} | {row['v2_raw']} | {row['v2_direct']} | {row['v2_split']} | {row['v2_rejected']} | {row['v2_median_d_px']:.1f} |\n"
header+='''
## What this establishes — and does not

- v2 has drastically fewer false detections on the *training* noisy Ag image. It shows successful fitting of this domain, **not out-of-sample accuracy**.
- v2 still rejects many particles in densely aggregated Pt fields, including potentially valid touching particles. These results prioritize precision over recall.
- Contact split statuses are heuristic plausible splits, not ground-truth proof. Optical overlap cannot be confidently identified from one projected TEM image.
- `particles_all.csv` contains every candidate and a reason (`weak_contrast`, `concave`, `dense_aggregate`, etc.). Only `particles_accepted.csv` is included in the numeric distribution.
- The scale-label exclusion uses a fixed normalized bottom-right rectangle (last 13% vertically, last 25% horizontally). It can also exclude legitimate particles in that rectangle.
- Real sample sources must be credited. No real-image labels were used to compute accuracy or to tune hyperparameters on independent validation.

## Next rigorous step

Create human-reviewed per-instance labels for several **completely separate TEM fields**, then measure precision/recall, contact-splitting errors, diameter error, and exclusion/coverage curves. Without those independent labels, v1 vs v2 counts alone cannot prove correctness.

## Reproduction

```bash
python v2/prepare_weak_labels.py
python v2/tem_v2.py train
python v2/tem_v2.py predict --image path/to/real_tem.png --out path/to/result
python v2/build_report.py
```

**Important:** `prepare_weak_labels.py` expects research-reference downloaded images in `real_tests/resized_inputs/`; those externally owned images may be distributed separately subject to their licenses. The source images used here were resized and this is not a 16-bit original TEM micrograph analysis.

## Detail pages
'''
for name,label in images.items():
    header+=f'\n### {label}\n\n![{label}](results/{name}/overview.png)\n\n[Accepted CSV](results/{name}/particles_accepted.csv) | [All candidates](results/{name}/particles_all.csv)\n'
(V2/'REPORT.md').write_text(header,encoding='utf8')
print(df.to_string(index=False));print('Saved',V2/'REPORT.md')
