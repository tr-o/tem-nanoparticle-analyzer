# Real TEM v2: supervised adaptation and conservative particle selection

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
| Pt-1 | dense | unseen | 588 | 459 | 36 | 4 | 419 | 7.0 |
| Pt-2 | medium | weak train | 420 | 512 | 291 | 47 | 174 | 8.5 |
| Pt-3 | medium | unseen | 309 | 379 | 166 | 27 | 186 | 7.8 |
| Ag-1 | isolated | weak train | 56 | 56 | 50 | 0 | 6 | 26.5 |
| Ag-2 | noisy | weak train | 1148 | 7 | 6 | 0 | 1 | 47.4 |
| Ag-3 | sparse | unseen | 21 | 15 | 8 | 4 | 3 | 25.4 |

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

### Pt-1 | dense

![Pt-1 | dense](results/web_image_2bed876c2a14_500/overview.jpg)

[Accepted CSV](results/web_image_2bed876c2a14_500/particles_accepted.csv) | [All candidates](results/web_image_2bed876c2a14_500/particles_all.csv)

### Pt-2 | medium

![Pt-2 | medium](results/web_image_9828c4ba32bc_500/overview.jpg)

[Accepted CSV](results/web_image_9828c4ba32bc_500/particles_accepted.csv) | [All candidates](results/web_image_9828c4ba32bc_500/particles_all.csv)

### Pt-3 | medium

![Pt-3 | medium](results/web_image_6af295ebd363_500/overview.jpg)

[Accepted CSV](results/web_image_6af295ebd363_500/particles_accepted.csv) | [All candidates](results/web_image_6af295ebd363_500/particles_all.csv)

### Ag-1 | isolated

![Ag-1 | isolated](results/web_image_b9ecc5092cc1_500/overview.jpg)

[Accepted CSV](results/web_image_b9ecc5092cc1_500/particles_accepted.csv) | [All candidates](results/web_image_b9ecc5092cc1_500/particles_all.csv)

### Ag-2 | noisy

![Ag-2 | noisy](results/web_image_82853817b188_500/overview.jpg)

[Accepted CSV](results/web_image_82853817b188_500/particles_accepted.csv) | [All candidates](results/web_image_82853817b188_500/particles_all.csv)

### Ag-3 | sparse

![Ag-3 | sparse](results/web_image_8222294b2379_500/overview.jpg)

[Accepted CSV](results/web_image_8222294b2379_500/particles_accepted.csv) | [All candidates](results/web_image_8222294b2379_500/particles_all.csv)

## Held-out synthetic validation (same simulated generator; four images)

| Pixel segmentation | v1 | v2 |
|---|---:|---:|
| Mean Dice | 0.9108 | 0.9043 |
| Mean IoU | 0.8363 | 0.8254 |

**Important:** Adding these weakly labeled real images slightly **reduced** synthetic test accuracy; improved behavior on the noisy real Ag training image does not prove a universally better model. A manually annotated **independent real** test set is needed before claiming improvement in real TEM generalization.

## Regression checks

```bash
python v2/checks.py
```

The `checks.json` file records the two-circle split assertion, the excluded metadata ROI assertion, and synthetic test segmentation scores.
