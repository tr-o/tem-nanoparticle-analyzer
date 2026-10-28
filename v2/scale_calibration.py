#!/usr/bin/env python3
"""Conservative scale-bar reader for TEM micrographs.

A scale value is *never* inferred from a vendor product name or particle size.
Physical units are exported only when an OCR text value and a plausible drawn bar
agree spatially, and the bar is sufficiently resolved. Tiny bars remain review-only.
OCR requires the optional system binary `tesseract` and `pytesseract`.
"""
from __future__ import annotations
import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
import cv2
import numpy as np

SCALE_RE = re.compile(r'(?<!\d)(\d+(?:\.\d+)?)\s*(nm|µm|μm|um|pm|mm|Å|A)(?![a-z])',re.I)
TO_NM = {'nm':1.,'um':1000.,'µm':1000.,'μm':1000.,'pm':.001,'mm':1e6,'å':.1,'a':.1}

@dataclass
class ScaleResult:
    status: str = 'not_found'  # accepted / review_required / not_found / manual
    text: str = ''
    value: float | None = None
    unit: str | None = None
    bar_width_px: float | None = None
    nm_per_px: float | None = None
    tentative_nm_per_px: float | None = None
    bar_bbox: list[int] | None = None
    text_bbox: list[int] | None = None
    annotation_bbox: list[int] | None = None
    exclusion_bbox: list[int] | None = None
    uncertainty_relative: float | None = None
    reason: str = ''
    method: str = 'ocr_and_geometry'


def _white_label(gray):
    h,w=gray.shape
    x0=int(w*.60);y0=int(h*.70)
    patch=gray[y0:,x0:]
    m=(patch>220).astype(np.uint8)
    n,_,stats,_=cv2.connectedComponentsWithStats(m)
    candidates=[]
    for x,y,bw,bh,area in stats[1:]:
        x+=x0;y+=y0
        if (bw>=w*.095 and bh>=h*.045 and bw < .35*w and bh < .20*h
            and area>=.68*bw*bh and x>=.6*w and y>=.72*h):
            candidates.append((area,(int(x),int(y),int(x+bw),int(y+bh))))
    return max(candidates)[1] if candidates else None


def _ocr_text(gray,box):
    try:
        import pytesseract
    except ImportError:
        return '',None,'missing pytesseract; install pytesseract + tesseract-ocr'
    h,w=gray.shape
    if box:
        x0,y0,x1,y1=box
        # Drop the bar at the top of the white-backed annotation.
        y0+=int((y1-y0)*.26)
        patch=gray[y0:y1,x0:x1]
        textbox=[x0,y0,x1,y1]
    else:
        x0=int(w*.67);x1=int(w*.99);y0=int(h*.87);y1=h
        patch=gray[y0:y1,x0:x1]
        textbox=[x0,y0,x1,y1]
    if patch.size==0:
        return '',textbox,'empty OCR crop'
    # A single OCR pass per image. Border helps OCR separate text from image edge.
    patch=cv2.resize(patch,None,fx=5,fy=5,interpolation=cv2.INTER_CUBIC)
    patch=cv2.copyMakeBorder(patch,12,12,12,12,cv2.BORDER_CONSTANT,value=255)
    try:
        s=pytesseract.image_to_string(patch,lang='eng',config='--psm 7 -c tessedit_char_whitelist=0123456789.nmupµμÅA').strip()
    except Exception as e:
        return '',textbox,'OCR unavailable: '+str(e)[:110]
    return s,textbox,''


def _find_bar(gray,box):
    h,w=gray.shape
    if box:
        x0,y0,x1,y1=box
        # Search only the upper half of a solid white annotation box.
        x0=max(0,x0-3);x1=min(w,x1+3)
        y1=min(h,y0+int((y1-y0)*.36))
        min_w=4;max_h=max(3,int(h*.024));min_aspect=.63
        threshold=105
    else:
        x0=int(.68*w);x1=int(.99*w)
        y0=int(.77*h);y1=int(.923*h)
        min_w=max(9,int(w*.020));max_h=max(3,int(h*.024));min_aspect=2.4
        threshold=75
    crop=gray[y0:y1,x0:x1]
    black=(crop<threshold).astype('uint8')
    n,_,stats,_=cv2.connectedComponentsWithStats(black)
    candidates=[]
    for bx,by,bw,bh,area in stats[1:]:
        if bw<min_w or bh<2 or bh>max_h or bw/bh<min_aspect or area/(bw*bh)<.70:continue
        # Wide text glyph groups, interference, and long decorations are rejected.
        if bw>min(w*.27,(x1-x0)*.90):continue
        if box:
            bxcenter=x0+bx+bw/2
            boxcenter=(box[0]+box[2])/2
            if abs(bxcenter-boxcenter)>(box[2]-box[0])*.32:continue
        scores=(area if box else bw/bh)*min(area/(bw*bh),1.)
        candidates.append((scores,[int(x0+bx),int(y0+by),int(x0+bx+bw),int(y0+by+bh)]))
    return max(candidates)[1] if candidates else None


def detect_scale(image, min_reliable_bar_px=18, confirm_short_bar=False):
    """Return scale metadata; a short bar is a TENTATIVE calibration only.

    min_reliable_bar_px: at least 18 actual pixels at the image being measured.
    A ±1 px endpoint uncertainty each implies ~2/18 = 11% relative uncertainty;
    this explicit uncertainty is reported, not represented as instrument accuracy.
    """
    if isinstance(image,(str,Path)):
        gray=cv2.imread(str(image),cv2.IMREAD_GRAYSCALE)
        if gray is None:raise FileNotFoundError(image)
    else:
        gray=np.asarray(image)
        if gray.ndim==3:gray=cv2.cvtColor(gray,cv2.COLOR_BGR2GRAY)
        if gray.dtype!=np.uint8:
            lo,hi=np.percentile(gray,[1,99]);gray=np.uint8(np.clip((gray-lo)/max(hi-lo,1e-6)*255,0,255))
    h,w=gray.shape
    box=_white_label(gray)
    text,text_bbox,ocr_error=_ocr_text(gray,box)
    bar=_find_bar(gray,box)
    result=ScaleResult(text=text,text_bbox=text_bbox,bar_bbox=bar,annotation_bbox=list(box) if box else None)
    match=SCALE_RE.search(text.replace(' ','').replace('\n',''))
    if match:
        result.value=float(match.group(1));result.unit=match.group(2)
    if box:
        x0,y0,x1,y1=box
        result.exclusion_bbox=[max(0,x0-5),max(0,y0-5),min(w,x1+5),min(h,y1+5)]
    elif bar:
        # Tight label rectangle around the drawn bar and the nearby text glyphs.
        # In particular, do NOT discard the whole bottom-right quadrant.
        bx0,by0,bx1,by1=bar
        xc=(bx0+bx1)/2
        yy0=by1+1; yy1=min(h,by1+max(20,int(.055*h)))
        xx0=max(0,int(xc-.10*w));xx1=min(w,int(xc+.11*w))
        roi=(gray[yy0:yy1,xx0:xx1]<95).astype('uint8')
        n,_,stats,_=cv2.connectedComponentsWithStats(roi)
        xhits=[bx0,bx1];yhits=[by0,by1]
        for x,y,ww,hh,area in stats[1:]:
            if 2<=ww<=.08*w and 4<=hh<=.05*h and area>=7:
                xhits.extend((xx0+x,xx0+x+ww));yhits.extend((yy0+y,yy0+y+hh))
        result.exclusion_bbox=[max(0,min(xhits)-max(6,int(.05*w))),max(0,min(yhits)-6),
                               min(w,max(xhits)+max(6,int(.05*w))),min(h,max(yhits)+6)]
    if not match or not bar:
        result.reason = ('scale text not recognized; '+(ocr_error or repr(text)) if not match else 'bar not found')
        return result
    width=bar[2]-bar[0]
    result.bar_width_px=float(width)
    nm=float(result.value)*TO_NM[result.unit.lower()]
    if not (nm>0 and 0<width<w*.3):
        result.reason='implausible scale value/bar size';return result
    result.tentative_nm_per_px=nm/width
    result.uncertainty_relative=round(2.0/width,3)
    if width<min_reliable_bar_px and not confirm_short_bar:
        result.status='review_required'
        result.reason=f'short bar ({width}px): endpoint uncertainty at least ±2px total; confirm manually'
    else:
        result.status='accepted'
        result.nm_per_px=result.tentative_nm_per_px
        result.reason=('short bar accepted by explicit user override' if width<min_reliable_bar_px else 'OCR+bar geometry accepted')
    return result


def exclusion_mask(shape,result:ScaleResult):
    mask=np.zeros(shape,dtype=bool)
    if result.exclusion_bbox:
        x0,y0,x1,y1=result.exclusion_bbox
        mask[y0:y1,x0:x1]=True
    return mask


def transfer_calibration(cal:ScaleResult, reference_img, analysis_img):
    """Transfer a scale from full-resolution reference to an identical resized view.

    Reject mismatch by matching pixel content, not just matching image dimensions.
    """
    def gray(x):
        if isinstance(x,(str,Path)):
            a=cv2.imread(str(x),cv2.IMREAD_GRAYSCALE)
            if a is None:raise FileNotFoundError(x)
            return a
        a=np.asarray(x)
        return cv2.cvtColor(a,cv2.COLOR_BGR2GRAY) if a.ndim==3 else a
    src=gray(reference_img);dst=gray(analysis_img)
    sy=src.shape[0]/dst.shape[0];sx=src.shape[1]/dst.shape[1]
    if not (abs(sx-sy)<.01 and sx>=1.0):
        raise ValueError('scale-reference aspect ratio differs or reference is lower resolution')
    down=cv2.resize(src,(dst.shape[1],dst.shape[0]),interpolation=cv2.INTER_AREA)
    correlation=float(np.corrcoef(down.ravel(),dst.ravel())[0,1])
    if not np.isfinite(correlation) or correlation<.97:
        raise ValueError(f'scale-reference is not the same visual field (correlation={correlation:.3f})')
    from dataclasses import replace
    cal=replace(cal)
    for field in ('annotation_bbox','exclusion_bbox','bar_bbox','text_bbox'):
        rect=getattr(cal,field)
        if rect is not None:
            setattr(cal,field,[int(round(rect[0]/sx)),int(round(rect[1]/sy)),
                               int(round(rect[2]/sx)),int(round(rect[3]/sy))])
    if cal.bar_width_px is not None:cal.bar_width_px=cal.bar_width_px/sx
    if cal.nm_per_px is not None:cal.nm_per_px*=sx
    if cal.tentative_nm_per_px is not None:cal.tentative_nm_per_px*=sx
    cal.method=f'{cal.method}; reference resized {sx:.4f}x; field_corr={correlation:.4f}'
    return cal


def draw_scale_overlay(image,result:ScaleResult):
    if isinstance(image,(str,Path)):
        out=cv2.imread(str(image))
    else:
        out=np.asarray(image).copy()
        if out.ndim==2:out=cv2.cvtColor(out,cv2.COLOR_GRAY2BGR)
    if result.exclusion_bbox:
        x0,y0,x1,y1=result.exclusion_bbox
        cv2.rectangle(out,(x0,y0),(x1-1,y1-1),(0,165,255),2)
    if result.bar_bbox:
        x0,y0,x1,y1=result.bar_bbox
        cv2.rectangle(out,(x0-2,y0-2),(x1+2,y1+2),(30,220,30),2)
    return out


def main():
    p=argparse.ArgumentParser(description='Read TEM scale bar from image; fail closed for ambiguous calibration')
    p.add_argument('--image',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--confirm-short-bar',action='store_true')
    args=p.parse_args()
    result=detect_scale(args.image,confirm_short_bar=args.confirm_short_bar)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    (out/'calibration.json').write_text(json.dumps(asdict(result),indent=2,ensure_ascii=False),encoding='utf8')
    cv2.imwrite(str(out/'scale_annotation.png'),draw_scale_overlay(args.image,result))
    print(json.dumps(asdict(result),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
