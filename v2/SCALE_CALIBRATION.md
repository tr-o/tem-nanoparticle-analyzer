# TEM scale calibration: real-image demonstration

**Analysis status:** exploratory. Not an instrument-grade calibration. OCR and bar geometry tested on bottom-right annotated vendor figure images. The measured widths refer to a 500×500 resized working image, but bar endpoints were located in the corresponding original 1000×1000 image to reduce rounding error.

![Scale bar detection and text mask](calibration_6_images.jpg)

| Image | OCR | Original bar (px) | 500px bar (px) | nm/px at 500px | Status |
|---|---|---:|---:|---:|---|
| Pt densely clustered | 5nm | 12.000 | 6.000 | — | review_required |
| Pt semi-dense | 5nm | 23.000 | 11.500 | 0.435 | accepted |
| Pt medium | 5nm | 20.000 | 10.000 | 0.500 | accepted |
| Ag isolated | 10nm | 46.000 | 23.000 | 0.435 | accepted |
| Ag noisy background | 10nm | 86.000 | 43.000 | 0.233 | accepted |
| Ag sparse | 10nm | 46.000 | 23.000 | 0.435 | accepted |

## How this works

1. Detect a lower-right annotation (white-backed if present). OCR only the label area; parse numeric value and nm/µm/pm/Å.
2. Find a compact dark horizontal stroke or rectangle directly above the text; reject incompatible candidate shapes.
3. Detect from the original image if available, verify the resized image matches the same view (pixel correlation >= 0.97), and transfer the calibration with correct scaling.
4. Exclude ONLY the detected scale-text patch, not the entire bottom-right corner. Save the exclusion as a mask; do not use scale or lettering as particle candidates.
5. For short bars (<18 pixels at *reference* resolution) retain the suggested nm/px as `tentative_nm_per_px`, not as accepted measurement. Manual confirmation is explicit.

## Limitations

- OCR was tested on six images from two product pages, not a general TEM corpus. Other annotation locations/layouts, multi-panel images or low-quality screenshots can fail.
- Estimated endpoint error of ±2 pixels for the complete bar length is a heuristic; this does not establish physical calibration uncertainty.
- Calibration may be accepted even if the particle segmentation is wrong. A physical scale is not a performance score for the segmentation model.
- A manufacturer-supplied metadata pixel size is preferable when available. Do not infer pixel scale from the nominal particle size.
- Strong overlaps remain excluded or flagged; contact splitting is not proof of separate particles.

## Reproduce

```bash
python v2/tem_v2.py predict --image analysis_500.png --scale-reference original_1000.png --model v2/model_rf_real_weak.joblib
python v2/app_v3.py
python -m unittest v2/test_scale_calibration.py
```

Sources: [Pt nanoparticle TEM](https://nanocomposix.com/products/5-nm-platinum-nanoparticles), [Ag nanoparticle TEM](https://nanocomposix.com/products/10-nm-silver-nanospheres). Experimental source images are NOT relicensed by this project.