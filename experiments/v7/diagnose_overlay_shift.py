#!/usr/bin/env python3
"""Diagnose constant XY misregistration in a two-color contour screenshot.

The generated 'registered' image is VISUAL DIAGNOSTIC ONLY. This command
never modifies segmentation model predictions, labels, particle diameters,
or GT masks. True fix requires shared original-image coordinate transforms.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from scipy.signal import fftconvolve


def color_masks(image_bgr):
    hsv=cv2.cvtColor(image_bgr,cv2.COLOR_BGR2HSV)
    h,s=hsv[:,:,0],hsv[:,:,1]
    blue=((h>=97)&(h<=135)&(s>80)).astype(np.uint8)
    red=(((h<=13)|(h>=170))&(s>80)).astype(np.uint8)
    return blue,red


def best_translation(blue,red, max_shift=55):
    """Return (dx,dy) required to move RED onto BLUE in screenshot pixels."""
    if blue.shape != red.shape or blue.ndim != 2:
        raise ValueError('blue/red raster shapes do not match')
    b=cv2.GaussianBlur(blue.astype('float32'),(5,5),1.)
    r=cv2.GaussianBlur(red.astype('float32'),(5,5),1.)
    cross=fftconvolve(b,r[::-1,::-1],mode='same')
    yc,xc=np.array(cross.shape)//2
    y0=max(0,yc-max_shift);y1=min(cross.shape[0],yc+max_shift+1)
    x0=max(0,xc-max_shift);x1=min(cross.shape[1],xc+max_shift+1)
    iy,ix=np.unravel_index(np.argmax(cross[y0:y1,x0:x1]),(y1-y0,x1-x0))
    return int(x0+ix-xc),int(y0+iy-yc)


def shifted(mask,dx,dy):
    h,w=mask.shape
    M=np.array([[1,0,dx],[0,1,dy]],dtype='float32')
    return cv2.warpAffine(mask,M,(w,h),flags=cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT,borderValue=0)


def near_overlap_score(blue,red,radius=2):
    b=cv2.dilate(blue,np.ones((2*radius+1,2*radius+1),dtype=np.uint8))>0
    r=red>0
    return float((b&r).sum()/max(int(r.sum()),1))


def diagnostic(path,outdir,max_shift=55):
    p=Path(path);rgb=cv2.imread(str(p))
    if rgb is None:raise FileNotFoundError(path)
    blue,red=color_masks(rgb)
    if blue.sum()<500 or red.sum()<500:raise ValueError('Not enough blue/red contour pixels')
    H,W=blue.shape
    margin=min(60,H//10,W//10)
    dx,dy=best_translation(blue[margin:-margin,margin:-margin],red[margin:-margin,margin:-margin],max_shift)
    before=near_overlap_score(blue,red)
    corrected=shifted(red,dx,dy)
    after=near_overlap_score(blue,corrected)
    tiles={}
    for name,(y0,y1,x0,x1) in {'top_left':(margin,H//2,margin,W//2),
        'top_right':(margin,H//2,W//2,W-margin),
        'bottom_left':(H//2,H-margin,margin,W//2),
        'bottom_right':(H//2,H-margin,W//2,W-margin)}.items():
        tiles[name]=best_translation(blue[y0:y1,x0:x1],red[y0:y1,x0:x1],max_shift)
    summary={'image':p.name,'width_px':W,'height_px':H,
             'red_shift_to_blue_dx_px':dx,'red_shift_to_blue_dy_px':dy,
             'near_overlap_before':before,'near_overlap_after':after,
             'tile_offsets':tiles,'interpretation':'constant translation indicative of image-frame mismatch, not identified source code',
             'warning':'visual diagnostic; do NOT apply this shift to model masks without tracing source transforms'}
    output=Path(outdir);output.mkdir(parents=True,exist_ok=True)
    # Reconstruct a clean-ish underlying screenshot with inpainting, avoiding
    # colorful line remnants. For visualization ONLY (JPEG loses image detail).
    ink=np.uint8((blue|red)>0)*255
    underlying=cv2.inpaint(rgb,cv2.dilate(ink,np.ones((3,3),np.uint8)),3,cv2.INPAINT_TELEA)
    clean=cv2.cvtColor(underlying,cv2.COLOR_BGR2RGB)
    bcontours,_=cv2.findContours(blue,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    rcontours,_=cv2.findContours(corrected,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(clean,bcontours,-1,(20,65,230),1,lineType=cv2.LINE_AA)
    cv2.drawContours(clean,rcontours,-1,(230,40,45),1,lineType=cv2.LINE_AA)
    orig=cv2.cvtColor(rgb,cv2.COLOR_BGR2RGB)
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(1,2,figsize=(15,7))
    axs[0].imshow(orig);axs[0].set_title('User screenshot: apparent contour offset');axs[0].axis('off')
    axs[1].imshow(clean);axs[1].set_title(f'VISUAL DIAGNOSTIC: red shift ({dx:+d},{dy:+d}) px');axs[1].axis('off')
    fig.tight_layout();fig.savefig(output/'alignment_before_after.jpg',dpi=130)
    plt.close(fig)
    (output/'alignment_diagnostic.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('image');p.add_argument('--out',required=True)
    args=p.parse_args();print(json.dumps(diagnostic(args.image,args.out),ensure_ascii=False,indent=2))
