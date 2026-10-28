# TEM Analyzer v2: reproducible research extension

This directory extends the existing `tem_particle_ml.py` model rather than replacing it.

- `tem_v2.py`: learn ExtraTrees from synthetic + three *weak* real annotations; detect and split particle candidates; conservative shape/contrast screening; CSV and annotated images.
- `prepare_weak_labels.py`: reproducible *heuristic-assisted* annotation recipes for Ag and Pt screenshots, with one manually selected set of obvious particle centers on a noisy Ag TEM.
- `checks.py`: small unit/regression tests and four held-out simulated tests.
- `build_report.py`: make `REPORT.md`, montage, and six-image count table.
- `REPORT.md`: visual comparison and interpretation, limitations and attribution.

### Setup

```bash
pip install -r requirements.txt
# Manually supply previously collected TEM source screenshots to real_tests/resized_inputs/.
python v2/prepare_weak_labels.py
python v2/tem_v2.py train
python v2/tem_v2.py predict --image real_tests/resized_inputs/web_image_82853817b188_500.png
python v2/checks.py
python v2/build_report.py
```

The external real source images are **not** assumed redistributable. If not stored in this repo, download the images with appropriate permission from the [Ag source](https://nanocomposix.com/products/10-nm-silver-nanospheres) and [Pt source](https://nanocomposix.com/products/5-nm-platinum-nanoparticles). Paths are for the original research screenshots and the demo's fixed ROI expects 500x500 vendor images; new inputs can be predicted, but real-weak retraining requires the matching research imagery.

### Interpretation caution

- No authoritative ground-truth real-TEM validation exists yet.
- `split_touching` is a plausible instance separation, not proof of no projection overlap.
- Severe Pt clustering causes conservative false rejections.
- Data in nm require calibrated pixel size and no false precision should be inferred from vendor figure thumbnails.
