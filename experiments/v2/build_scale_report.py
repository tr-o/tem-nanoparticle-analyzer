"""Generate scale-bar calibration diagnostics; requires local source images."""
from __future__ import annotations
import json,sys
from dataclasses import asdict
from pathlib import Path
import cv2,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from scale_calibration import detect_scale,transfer_calibration,draw_scale_overlay
ROOT=Path(__file__).resolve().parents[2]
IMAGES=ROOT/'real_tests/resized_inputs'
SOURCE=Path('/mnt/data/ghostwriter_images/web_context')
OUT=ROOT/'v3_calibration'
OUT.mkdir(exist_ok=True)
ITEMS=[('Pt densely clustered','web_image_2bed876c2a14'),('Pt semi-dense','web_image_9828c4ba32bc'),('Pt medium','web_image_6af295ebd363'),('Ag isolated','web_image_b9ecc5092cc1'),('Ag noisy background','web_image_82853817b188'),('Ag sparse','web_image_8222294b2379')]
records=[]
can=np.full((2*410,3*480,3),255,np.uint8)
for index,(label,stem) in enumerate(ITEMS):
    src=SOURCE/(stem+'.png')
    image=IMAGES/(stem+'_500.png')
    if not src.exists() or not image.exists():
        print('SKIP',src,image);continue
    cal=transfer_calibration(detect_scale(src),src,image)
    rec={'image':stem,'description':label,'reference':str(src),'analysis':str(image),**asdict(cal)}
    records.append(rec)
    target=OUT/stem;target.mkdir(exist_ok=True)
    (target/'calibration.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2))
    overlay=draw_scale_overlay(image,cal)
    cv2.imwrite(str(target/'scale_overlay.png'),overlay)
    crop=overlay[330:500,315:500]
    zoom=cv2.resize(crop,(450,330),interpolation=cv2.INTER_NEAREST)
    x=index%3*480+15;y=index//3*410+40
    can[y:y+330,x:x+450]=zoom
    cv2.putText(can,label,(x,y-12),cv2.FONT_HERSHEY_SIMPLEX,.65,(20,20,20),2,cv2.LINE_AA)
    summary=f"{cal.text} | bar {cal.bar_width_px:.1f}px | {cal.status}"
    cv2.putText(can,summary,(x,y+354),cv2.FONT_HERSHEY_SIMPLEX,.48,(10,10,10),1,cv2.LINE_AA)
    nm=cal.nm_per_px
    cv2.putText(can,(f'{nm:.4f} nm/px' if nm is not None else 'nm/px: confirmation required'),
                (x,y+376),cv2.FONT_HERSHEY_SIMPLEX,.55,(35,75,160) if nm is None else (35,110,35),1,cv2.LINE_AA)
cv2.imwrite(str(OUT/'calibration_6_images.jpg'),can,[cv2.IMWRITE_JPEG_QUALITY,88])
(OUT/'scale_results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
lines=['# TEM scale calibration: real-image demonstration','',
       '**Analysis status:** exploratory. Not an instrument-grade calibration. OCR and bar geometry tested on bottom-right annotated vendor figure images. The measured widths refer to a 500×500 resized working image, but bar endpoints were located in the corresponding original 1000×1000 image to reduce rounding error.','',
       '![Scale bar detection and text mask](calibration_6_images.jpg)','',
       '| Image | OCR | Original bar (px) | 500px bar (px) | nm/px at 500px | Status |','|---|---|---:|---:|---:|---|']
for d in records:
    refw=d['bar_width_px']*2 if d['bar_width_px'] is not None else None
    w=d['bar_width_px']
    fmt=lambda val: f'{val:.3f}' if val is not None else '—'
    lines.append(f"| {d['description']} | {d['text']} | {fmt(refw)} | {fmt(w)} | {fmt(d['nm_per_px'])} | {d['status']} |")
lines+=['','## How this works','',
        '1. Detect a lower-right annotation (white-backed if present). OCR only the label area; parse numeric value and nm/µm/pm/Å.','2. Find a compact dark horizontal stroke or rectangle directly above the text; reject incompatible candidate shapes.','3. Detect from the original image if available, verify the resized image matches the same view (pixel correlation >= 0.97), and transfer the calibration with correct scaling.','4. Exclude ONLY the detected scale-text patch, not the entire bottom-right corner. Save the exclusion as a mask; do not use scale or lettering as particle candidates.','5. For short bars (<18 pixels at *reference* resolution) retain the suggested nm/px as `tentative_nm_per_px`, not as accepted measurement. Manual confirmation is explicit.','',
        '## Limitations','',
        '- OCR was tested on six images from two product pages, not a general TEM corpus. Other annotation locations/layouts, multi-panel images or low-quality screenshots can fail.','- Estimated endpoint error of ±2 pixels for the complete bar length is a heuristic; this does not establish physical calibration uncertainty.','- Calibration may be accepted even if the particle segmentation is wrong. A physical scale is not a performance score for the segmentation model.','- A manufacturer-supplied metadata pixel size is preferable when available. Do not infer pixel scale from the nominal particle size.','- Strong overlaps remain excluded or flagged; contact splitting is not proof of separate particles.','',
        '## Reproduce','',
        '```bash','python experiments/v2/tem_v2.py predict --image analysis_500.png --scale-reference original_1000.png --model experiments/v2/model_rf_real_weak.joblib','python experiments/v2/app_v3.py','python -m unittest experiments/v2/test_scale_calibration.py','```','',
        'Sources: [Pt nanoparticle TEM](https://nanocomposix.com/products/5-nm-platinum-nanoparticles), [Ag nanoparticle TEM](https://nanocomposix.com/products/10-nm-silver-nanospheres). Experimental source images are NOT relicensed by this project.']
(OUT/'SCALE_CALIBRATION.md').write_text('\n'.join(lines),encoding='utf8')
print((OUT/'SCALE_CALIBRATION.md').read_text()[:1600])
