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


## v3: Scale-bar calibration and image exclusion

- `scale_calibration.py`: single-pass Tesseract OCR of nm labels, horizontal-bar/square detection, automatic mask of only the annotation, uncertainty-based acceptance, and full-resolution to resized-image field matching.
- `tem_v2.py predict` automatically reports `calibration.json` and `scale_annotation.png`. Accepted calibrations add `diameter_nm`, `area_nm2` to the measurement CSV, and switch the histogram to nm. Failed/short bars do not silently apply physical units.
- `app_v3.py`: Gradio GUI for uploading an analysis image and optional higher-resolution same-field reference image; optional manual nm/px override.

Install optional OCR support: system `tesseract-ocr` plus `pip install pytesseract` (also `gradio pandas` for GUI).

```bash
# Original and analysis image must be exactly the same field of view; the program checks correlation.
python v2/tem_v2.py predict --image analysis_500.png \
  --scale-reference original_1000.png --model v2/model_rf_real_weak.joblib
# For short bars: review scale_annotation.png and choose manual override only when justified.
python v2/tem_v2.py predict --image image.png --nm-per-px 0.35
python v2/app_v3.py
```

**Scope and limitations:** the automatic text-location strategy was evaluated on vendor images with bottom-right scale bars only; other formats, bars elsewhere, tilt/rotation, multi-panel figures, overlay graphics, and image crops may need a manual scale. For weakly resolved bars, apparent precision of nm/px is not an instrument uncertainty. Original microscopy calibration/metadata are preferable to OCR from publication figures. Do not assume a scale label is present for simulated training images.

### Model distribution

`v2/model_rf_real_weak_portable.joblib` is a reduced **15-tree** ExtraTrees model for easy checkout and GUI demonstration. The original 48-tree experimental model is not equivalent and has not been uploaded. All v3 preview inferences use the portable model. Training via `tem_v2.py train` creates a separate full model `v2/model_rf_real_weak.joblib` and requires real source images where licensing permits.
