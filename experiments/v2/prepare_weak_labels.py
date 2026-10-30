"""Build *weak* pixel annotations for a first real-image domain adaptation.

This is not a hand-validated ground-truth dataset. Pixel value 128 means IGNORE.
Sources: two nanoComposix Ag TEM figure images downloaded via web image provider.
"""
from pathlib import Path
import cv2
import numpy as np
from scipy import ndimage as ndi
from skimage import measure, morphology

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'real_tests/resized_inputs'
OUT=ROOT/'experiments/v2/weak_labels'
OUT.mkdir(parents=True,exist_ok=True)

def save(name,img,lab,desc):
    dst=OUT/name
    dst.mkdir(parents=True,exist_ok=True)
    cv2.imwrite(str(dst/'image.png'),img)
    cv2.imwrite(str(dst/'labels.png'),lab)
    cv2.imwrite(str(dst/'label_preview.png'),cv2.cvtColor(img,cv2.COLOR_GRAY2BGR)*0+0) if False else None
    show=cv2.cvtColor(img,cv2.COLOR_GRAY2RGB)
    show[lab==255] = (0.45*show[lab==255]+0.55*np.array([10,220,65])).astype('uint8')
    show[lab==0] = (0.7*show[lab==0]+0.3*np.array([30,100,230])).astype('uint8')
    cv2.imwrite(str(dst/'label_preview.png'),cv2.cvtColor(show,cv2.COLOR_RGB2BGR))
    (dst/'provenance.txt').write_text(desc+'\nWhite=positive, black=negative, mid-gray=ignore. Not GT.\n',encoding='utf-8')
    print(name, 'pos',int((lab==255).sum()),'neg',int((lab==0).sum()),'ignore',int((lab==128).sum()))

# Isolated, easy Ag: automatically assisted positives from previous RF segmentation;
# avoid trusting object edges as GT by eroding positives and ignoring an uncertainty ring.
img=cv2.imread(str(SRC/'web_image_b9ecc5092cc1_500.png'),0)
from sys import path
path.insert(0,str(ROOT))
from tem_analyzer import legacy_rf as old
labels=np.load(ROOT/'real_tests/web_image_b9ecc5092cc1_500/instance_labels.npy')
rows=old.measure_particles(labels,min_area=50,image=old.read_gray(SRC/'web_image_b9ecc5092cc1_500.png'))
ids={r['id'] for r in rows if not r['touching_or_irregular'] and r['diameter_px'] > 13 and r['diameter_px'] < 42}
positive=np.isin(labels,list(ids))
positive=ndi.binary_erosion(positive,iterations=2)
ignore=ndi.binary_dilation(np.isin(labels,list(ids)),iterations=7)
# Background pixels far from any old candidates, only high-lightness zones, not border/scale
lab=np.full(img.shape,128,dtype='uint8')
lab[(~ignore)&(img>150)&(np.arange(500)[None,:]<390)&(np.arange(500)[:,None]<440)]=0
lab[positive]=255
save('ag_isolated',img,lab,'Weak assisted annotation: old model high-circularity candidates; eroded positive cores, clear background, edges ignored. SOURCE https://nanocomposix.com/products/10-nm-silver-nanospheres')

# Noisy Ag: human-inspected visible particle centers. Some centers are touching;
# positive inner disk masked by intensity threshold; uncertain edges intentionally ignored.
img=cv2.imread(str(SRC/'web_image_82853817b188_500.png'),0)
centers=[(38,234,22),(55,325,18),(323,213,23),(370,225,24),(335,265,22),(337,377,20)]
lab=np.zeros(img.shape,dtype='uint8')
yy,xx=np.indices(img.shape)
exclude=(yy>435)&(xx>375)
for x,y,r in centers:
    d=np.hypot(xx-x,yy-y)
    lab[d<r+14]=128
    # clearly dark core is positive, avoid drawing possibly unobserved boundaries
    ann=img[(d>r+7)&(d<r+15)]
    bkg=float(np.median(ann))
    pos=(d<r-3)&(img<min(bkg-16,175))
    lab[pos]=255
lab[exclude]=128
# hard negative far from particles includes noisy textured carbon
save('ag_noisy',img,lab,'Weak human-selected 6 centers (x,y,r) and intensity core threshold; textured background negative; uncertain halos and annotations ignored. SOURCE https://nanocomposix.com/products/10-nm-silver-nanospheres')

# Dense Pt: use only separated, round and good-contrast portions as *weak* positives.
# Avoid using all 500x500 background as negative due to dense legitimate particles.
img=cv2.imread(str(SRC/'web_image_9828c4ba32bc_500.png'),0)
labels=np.load(ROOT/'real_tests/pt_img2_500/instance_labels.npy')
rows=old.measure_particles(labels,min_area=20,image=old.read_gray(SRC/'web_image_9828c4ba32bc_500.png'))
ids={r['id'] for r in rows if not r['touching_or_irregular'] and 7 < r['diameter_px'] < 18 and r['circularity'] > .83}
positive=ndi.binary_erosion(np.isin(labels,list(ids)),iterations=2)
lab=np.full(img.shape,128,dtype='uint8')
# do not force background on potentially faint unknown Pt, use only blank rectangle
lab[360:430,65:170]=0
lab[positive]=255
save('pt_semi_dense',img,lab,'Weak RF-assisted candidate cores and conservative background patch; dense/contact regions ignored. SOURCE https://nanocomposix.com/products/5-nm-platinum-nanoparticles')
