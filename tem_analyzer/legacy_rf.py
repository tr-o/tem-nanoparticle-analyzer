#!/usr/bin/env python3
"""Supervised TEM nanoparticle analyzer.

Research prototype: RF semantic segmentation + marker watershed.
Demo images are SYNTHETIC, not experimental TEM.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path

import cv2
import joblib
import numpy as np
from scipy import ndimage as ndi
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist
from skimage import measure, morphology, segmentation
from sklearn.ensemble import RandomForestClassifier


def read_gray(path):
    im = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if im is None:
        raise FileNotFoundError(path)
    if im.ndim == 3:
        im = cv2.cvtColor(im[:, :, :3], cv2.COLOR_BGR2GRAY)
    if im.dtype == np.uint8:
        return im.astype(np.float32)/255.0
    if im.dtype == np.uint16:
        return im.astype(np.float32)/65535.0
    im = im.astype(np.float32)
    return (im-im.min())/max(float(np.ptp(im)), 1e-6)


def normalize(image):
    lo, hi = np.percentile(image, [1, 99.5])
    return np.clip((image-lo)/max(float(hi-lo), 1e-5), 0, 1).astype(np.float32)


def feature_stack(image):
    x = normalize(image)
    f = [x]
    for sigma in (1., 2., 4., 8.):
        g = ndi.gaussian_filter(x, sigma)
        f.extend([g, x-g, -ndi.gaussian_laplace(x, sigma)*sigma**2])
        if sigma <= 4:
            gx = ndi.gaussian_filter(x, sigma, order=(0, 1))
            gy = ndi.gaussian_filter(x, sigma, order=(1, 0))
            f.append(np.hypot(gx, gy))
    bg = ndi.gaussian_filter(x, 20)
    f.extend([x-bg, bg, np.sqrt(np.maximum(ndi.gaussian_filter(x*x, 2)-ndi.gaussian_filter(x, 2)**2, 0))])
    return np.stack(f, axis=-1).astype(np.float32)


def pairs(images, masks):
    root = Path(masks)
    ps = []
    for im in sorted(Path(images).iterdir()):
        if im.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp'):
            continue
        mask = next((root / (im.stem+ext) for ext in ('.png', '.tif', '.tiff', '.jpg', '.bmp') if (root/(im.stem+ext)).exists()), None)
        if mask:
            ps.append((im, mask))
    if not ps:
        raise ValueError('No matching image/mask basename pairs')
    return ps


def read_mask(path):
    a = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if a is None:
        raise FileNotFoundError(path)
    return a > 127


def fit_model(images, masks, modelpath, seed=2026, max_per_image=7000, trees=55):
    rng = np.random.default_rng(seed)
    xx, yy = [], []
    pp = pairs(images, masks)
    for imp, mp in pp:
        im, mask = read_gray(imp), read_mask(mp)
        if im.shape != mask.shape:
            raise ValueError(f'Image/mask mismatch: {imp}')
        feature_img = feature_stack(im)
        feat = feature_img.reshape(-1, feature_img.shape[-1])
        labels = mask.ravel().astype(np.uint8)
        selections = []
        for cls in (0, 1):
            idx = np.flatnonzero(labels == cls)
            if idx.size:
                selections.append(rng.choice(idx, size=min(idx.size, max_per_image//2), replace=False))
        idx = np.concatenate(selections)
        xx.append(feat[idx])
        yy.append(labels[idx])
        print(f'Training image: {imp.name}, sampled pixels: {len(idx)}', flush=True)
    x, y = np.concatenate(xx), np.concatenate(yy)
    forest = RandomForestClassifier(n_estimators=trees, max_depth=19,
        min_samples_leaf=3, class_weight='balanced_subsample',
        max_features='sqrt', n_jobs=-1, random_state=seed)
    forest.fit(x, y)
    dest = Path(modelpath)
    dest.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({'clf': forest, 'source_count': len(pp), 'feature_count': x.shape[1]}, dest, compress=3)
    return forest


def predict_probability(model, image):
    clf = joblib.load(model)['clf'] if isinstance(model, (str, Path)) else model
    fs = feature_stack(image)
    x = fs.reshape(-1, fs.shape[-1])
    pred = np.empty(len(x), np.float32)
    for start in range(0, len(x), 120000):
        end = min(start+120000, len(x))
        pred[start:end] = clf.predict_proba(x[start:end])[:, 1]
    return pred.reshape(image.shape)


def split_instances(prob, threshold=.52, min_area=22, min_distance=6, prominence=2.):
    binary = ndi.gaussian_filter(prob, .7) > threshold
    cc, _ = ndi.label(binary)
    binary &= np.bincount(cc.ravel())[cc] >= int(min_area)
    binary = ndi.binary_fill_holes(binary)
    dist = ndi.distance_transform_edt(binary)
    peaks = morphology.h_maxima(dist, h=prominence) if np.max(dist)>0 else np.zeros_like(binary)
    peak_labels, n = ndi.label(peaks)
    markers = np.zeros(binary.shape, np.int32)
    accepted = []
    if n:
        centers = ndi.center_of_mass(dist, peak_labels, list(range(1, n+1)))
        centers = sorted(((int(round(y)), int(round(x))) for y,x in centers),
            key=lambda c: dist[c] if 0 <= c[0]<dist.shape[0] and 0<=c[1]<dist.shape[1] else 0, reverse=True)
        for cy,cx in centers:
            if not (0<=cy<binary.shape[0] and 0<=cx<binary.shape[1] and binary[cy,cx]):
                continue
            if any((cy-y)**2+(cx-x)**2 < min_distance**2 for y,x in accepted):
                continue
            accepted.append((cy,cx))
            markers[cy,cx] = len(accepted)
    if not accepted:
        return measure.label(binary), binary
    labels = segmentation.watershed(-dist, markers, mask=binary)
    sizes = np.bincount(labels.ravel())
    labels[sizes[labels] < int(min_area)] = 0
    unique = np.unique(labels)
    unique = unique[unique>0]
    lookup = np.zeros(labels.max()+1, np.int32)
    lookup[unique] = np.arange(1, len(unique)+1)
    return lookup[labels], binary


def measure_particles(labels, nm_per_px=None, min_area=22):
    h,w = labels.shape
    rows = []
    for p in measure.regionprops(labels):
        area = int(p.area)
        if area < min_area:
            continue
        r0,c0,r1,c1 = p.bbox
        if r0<=0 or c0<=0 or r1>=h or c1>=w:
            continue
        cy,cx = p.centroid
        diameter = math.sqrt(4*area/math.pi)
        feret = float(p.feret_diameter_max)
        perimeter = float(p.perimeter_crofton)
        circularity = 4*math.pi*area/(perimeter*perimeter) if perimeter>0 else float('nan')
        row = dict(id=int(p.label),x_px=round(cx,2),y_px=round(cy,2),area_px2=area,
            diameter_px=round(diameter,3),feret_max_px=round(feret,3),
            circularity=round(circularity,3),
            aspect_ratio=round(float(p.axis_major_length/max(p.axis_minor_length,1e-6)),3),
            touching_or_irregular=bool(circularity<.72),edge_excluded=False)
        if nm_per_px is not None:
            row.update(diameter_nm=round(diameter*nm_per_px,3),
                feret_max_nm=round(feret*nm_per_px,3),area_nm2=round(area*nm_per_px**2,3))
        rows.append(row)
    return rows


def draw_overlay(image, labels, rows):
    rgb = cv2.cvtColor((normalize(image)*255).astype(np.uint8), cv2.COLOR_GRAY2RGB)
    included = {r['id']:r for r in rows}
    for p in measure.regionprops(labels):
        if p.label not in included:
            continue
        mask = labels==p.label
        hue = (p.label*53)%180
        shade = cv2.cvtColor(np.uint8([[[hue,190,240]]]),cv2.COLOR_HSV2RGB)[0,0]
        rgb[mask] = (.73*rgb[mask]+.27*shade).astype(np.uint8)
        for contour in measure.find_contours(mask.astype(float),.5):
            pts = np.round(contour[:,::-1]).astype(np.int32).reshape(-1,1,2)
            cv2.polylines(rgb,[pts],True,(0,245,240) if included[p.label]['touching_or_irregular'] else (38,226,95),1)
        if len(rows)<140:
            cy,cx=p.centroid
            cv2.putText(rgb,str(p.label),(int(cx)+2,int(cy)-2),cv2.FONT_HERSHEY_SIMPLEX,.27,(235,235,20),1)
    return rgb


def save_inference(imagepath, modelpath, outdir, nm_per_px=None, threshold=.52,
                   min_area=22, min_distance=6, prominence=2.):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    im = read_gray(imagepath)
    prob = predict_probability(modelpath, im)
    labels, mask = split_instances(prob, threshold, min_area, min_distance, prominence)
    rows = measure_particles(labels, nm_per_px, min_area)
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out/'probability.png'),np.uint8(np.clip(prob*255,0,255)))
    cv2.imwrite(str(out/'mask.png'),np.uint8(mask)*255)
    np.save(out/'instance_labels.npy',labels)
    overlay = draw_overlay(im,labels,rows)
    cv2.imwrite(str(out/'overlay.png'),cv2.cvtColor(overlay,cv2.COLOR_RGB2BGR))
    columns = list(rows[0]) if rows else ['id','x_px','y_px','diameter_px']
    with (out/'particles.csv').open('w',newline='',encoding='utf8') as f:
        writer = csv.DictWriter(f,fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    key = 'diameter_nm' if nm_per_px is not None else 'diameter_px'
    ds = [r[key] for r in rows]
    fig,ax = plt.subplots(1,2,figsize=(11,4.8))
    ax[0].imshow(overlay)
    ax[0].axis('off')
    ax[0].set_title('RF + watershed overlay')
    ax[1].hist(ds,bins=min(20,max(5,int(np.sqrt(max(len(ds),1))))),edgecolor='white')
    ax[1].set_xlabel('Equivalent diameter (nm)' if nm_per_px is not None else 'Equivalent diameter (px)')
    ax[1].set_ylabel('Particles')
    ax[1].set_title(f'N={len(ds)} mean={np.mean(ds):.2f}' if ds else 'No particles')
    fig.tight_layout()
    fig.savefig(out/'overview.png',dpi=170)
    plt.close(fig)
    result = dict(image=str(imagepath),model=str(modelpath),n_measured=len(rows),
        mean_diameter=float(np.mean(ds)) if ds else None,
        std_diameter=float(np.std(ds,ddof=1)) if len(ds)>1 else None,
        diameter_unit='nm' if nm_per_px is not None else 'px',nm_per_px=nm_per_px,
        threshold=threshold,min_area=min_area)
    (out/'summary.json').write_text(json.dumps(result,indent=2))
    return result


def synth_image(seed, shape=(320,320), n=72):
    """Synthetic BF-TEM-like training image and known ground truth."""
    rng=np.random.default_rng(seed)
    h,w=shape
    yy,xx=np.mgrid[:h,:w]
    low=ndi.gaussian_filter(rng.normal(size=shape),sigma=42)
    low/=np.std(low)+1e-6
    med=ndi.gaussian_filter(rng.normal(size=shape),sigma=8)
    med/=np.std(med)+1e-6
    bg=(.82+rng.uniform(.010,.045)*low+rng.uniform(.009,.035)*med+
        rng.uniform(-.07,.07)*xx/w+rng.uniform(-.045,.045)*yy/h)
    mask=np.zeros(shape,bool)
    absorb=np.zeros(shape,np.float32)
    centers=[]
    for _ in range(n):
        r=float(np.clip(rng.lognormal(np.log(9.),.39),4,20))
        cx=float(rng.uniform(2,w-2))
        cy=float(rng.uniform(2,h-2))
        aspect=float(rng.uniform(.80,1.20))
        theta=float(rng.uniform(0,np.pi))
        xr=(xx-cx)*np.cos(theta)+(yy-cy)*np.sin(theta)
        yr=-(xx-cx)*np.sin(theta)+(yy-cy)*np.cos(theta)
        rho=np.sqrt((xr/(r*aspect))**2+(yr/(r/aspect))**2)
        phase=np.arctan2(yr,xr)
        rho=rho/(1+rng.uniform(.005,.052)*np.cos(3*phase+rng.uniform(0,6)))
        mask|=rho<=1
        contrast=float(rng.uniform(.14,.32))
        absorb+=contrast*np.clip(1.2-rho,0,1).astype(np.float32)
        centers.append([cy,cx,r])
    for _ in range(int(rng.integers(1,5))):
        cy=rng.uniform(0,h);cx=rng.uniform(0,w)
        radius=rng.uniform(18,46)
        bg-=rng.uniform(.02,.075)*np.exp(-((xx-cx)**2+(yy-cy)**2)/(2*radius**2))
    im=ndi.gaussian_filter(bg-absorb,sigma=float(rng.uniform(.65,1.15)))
    im+=rng.normal(0,rng.uniform(.018,.041),size=shape)
    return np.clip(im,0,1).astype(np.float32),mask,centers


def generate_demo(out, train=16, test=4, seed=900):
    root=Path(out)
    for group,count in (('train',train),('test',test)):
        for sub in ('images','masks','instances'):
            (root/group/sub).mkdir(parents=True,exist_ok=True)
        for i in range(count):
            image,mask,instances = synth_image(seed+(i if group=='train' else 1000+i),
                n=70 if group=='train' else 82)
            name=f'{group}_{i:02d}'
            cv2.imwrite(str(root/group/'images'/f'{name}.png'),np.uint8(image*255))
            cv2.imwrite(str(root/group/'masks'/f'{name}.png'),np.uint8(mask)*255)
            (root/group/'instances'/f'{name}.json').write_text(json.dumps(instances))
    (root/'README_DATA.txt').write_text(
        'SYNTHETIC, NOT EXPERIMENTAL TEM\n'
        'Masks are exact procedural semantic labels, not manually traced.\n'
        'Instance center files are simulator truth; overlaps are possible.\n'
        'Train/test use different seeds but the same image simulator.\n'
        '0.4 nm/pixel in demos is invented scale metadata.\n')


def evaluation(modelpath, images, masks, out=None):
    details=[]
    for imp, mp in pairs(images,masks):
        image, truth = read_gray(imp), read_mask(mp)
        pred = predict_probability(modelpath, image) > .52
        tp=int(np.sum(pred & truth))
        fp=int(np.sum(pred & ~truth))
        fn=int(np.sum(~pred & truth))
        result=dict(image=imp.name,dice=round(2*tp/max(2*tp+fp+fn,1),4),
            iou=round(tp/max(tp+fp+fn,1),4))
        instances,_ = split_instances(predict_probability(modelpath,image))
        rows = measure_particles(instances)
        result['measured_particles']=len(rows)
        truth_file=imp.parent.parent/'instances'/(imp.stem+'.json')
        if truth_file.exists() and rows:
            allcenters=json.loads(truth_file.read_text())
            visible=[(cy,cx,r) for cy,cx,r in allcenters
                 if cy-r>0 and cx-r>0 and cy+r<image.shape[0] and cx+r<image.shape[1]]
            if visible:
                d=cdist(np.array([[cy,cx] for cy,cx,r in visible]),
                        np.array([[r['y_px'],r['x_px']] for r in rows]))
                tolerances=np.array([max(4,.75*r) for cy,cx,r in visible])[:,None]
                costs=np.where(d<=tolerances,d,100000)
                ii,jj=linear_sum_assignment(costs)
                correct=int(np.sum(costs[ii,jj]<100000))
                result.update(center_detection_precision=round(correct/len(rows),4),
                    center_detection_recall=round(correct/len(visible),4),
                    true_fully_visible_particles=len(visible),center_matched=correct)
        details.append(result)
    summary=dict(n_images=len(details),
        mean_dice=float(np.mean([r['dice'] for r in details])),
        mean_iou=float(np.mean([r['iou'] for r in details])),
        caveat='Synthetic train and test use the same generator; not TEM validation.')
    for key in ('center_detection_precision','center_detection_recall'):
        values=[r[key] for r in details if key in r]
        if values:
            summary['mean_'+key.replace('center_detection_','center_')]=float(np.mean(values))
    if out:
        Path(out).write_text(json.dumps(dict(summary=summary,images=details),indent=2))
    return summary


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('generate-demo')
    p.add_argument('--out',default='demo_data')
    p.add_argument('--train',type=int,default=16)
    p.add_argument('--test',type=int,default=4)
    p=sub.add_parser('train')
    p.add_argument('--images',required=True)
    p.add_argument('--masks',required=True)
    p.add_argument('--model',required=True)
    p.add_argument('--trees',type=int,default=55)
    p=sub.add_parser('predict')
    p.add_argument('--image',required=True)
    p.add_argument('--model',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--nm-per-px',type=float)
    p.add_argument('--threshold',type=float,default=.52)
    p.add_argument('--min-area',type=int,default=22)
    p.add_argument('--prominence',type=float,default=2.)
    p=sub.add_parser('evaluate')
    p.add_argument('--images',required=True)
    p.add_argument('--masks',required=True)
    p.add_argument('--model',required=True)
    p.add_argument('--out',default='test_metrics.json')
    a=ap.parse_args()
    if a.cmd=='generate-demo':
        generate_demo(a.out,a.train,a.test)
    elif a.cmd=='train':
        fit_model(a.images,a.masks,a.model,trees=a.trees)
    elif a.cmd=='predict':
        print(json.dumps(save_inference(a.image,a.model,a.out,a.nm_per_px,a.threshold,
            a.min_area,prominence=a.prominence),indent=2))
    elif a.cmd=='evaluate':
        print(json.dumps(evaluation(a.model,a.images,a.masks,a.out),indent=2))


if __name__=='__main__':
    main()
