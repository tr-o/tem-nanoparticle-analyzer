"""Run: python -m unittest v2/test_scale_calibration.py"""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from scale_calibration import detect_scale,exclusion_mask,transfer_calibration,SCALE_RE,TO_NM

class ScaleTests(unittest.TestCase):
    def test_unit_parsing(self):
        for label,expected in [('5nm',5),('10 nm',10),('0.2um',200),('150pm',.15),('1Å',.1)]:
            m=SCALE_RE.search(label)
            self.assertIsNotNone(m,label)
            self.assertAlmostEqual(float(m[1])*TO_NM[m[2].lower()],expected)

    def fake_white_label(self,bar_width=10):
        a=np.full((500,500),160,np.uint8)
        cv2.rectangle(a,(407,433),(491,489),255,-1)
        cv2.rectangle(a,(445-bar_width//2,443),(445-bar_width//2+bar_width-1,449),0,-1)
        cv2.putText(a,'5 nm',(412,478),cv2.FONT_HERSHEY_SIMPLEX,.78,0,2,cv2.LINE_AA)
        return a

    def test_short_bar_fails_closed(self):
        img=self.fake_white_label(10)
        with patch('scale_calibration._ocr_text',return_value=('5nm',[413,456,490,489],'')):
            r=detect_scale(img)
        self.assertEqual(r.status,'review_required')
        self.assertIsNone(r.nm_per_px)
        self.assertIsNotNone(r.exclusion_bbox)
        self.assertTrue(exclusion_mask(img.shape,r).any())

    def test_confirm_short_bar(self):
        img=self.fake_white_label(10)
        with patch('scale_calibration._ocr_text',return_value=('5nm',[413,456,490,489],'')):
            r=detect_scale(img,confirm_short_bar=True)
        self.assertEqual(r.status,'accepted')
        self.assertAlmostEqual(r.nm_per_px,5/r.bar_width_px)

    def test_missing_text_no_nm(self):
        img=self.fake_white_label(10)
        with patch('scale_calibration._ocr_text',return_value=('??',None,'')):
            r=detect_scale(img)
        self.assertEqual(r.status,'not_found')
        self.assertIsNone(r.nm_per_px)

    def test_same_field_resize(self):
        src=self.fake_white_label(22)
        dst=cv2.resize(src,(250,250),interpolation=cv2.INTER_AREA)
        with patch('scale_calibration._ocr_text',return_value=('5nm',None,'')):
            r=detect_scale(src)
        self.assertEqual(r.status,'accepted')
        out=transfer_calibration(r,src,dst)
        self.assertAlmostEqual(out.nm_per_px,2*r.nm_per_px)
        self.assertGreater(out.exclusion_bbox[0],int(dst.shape[1]*.5))

    def test_wrong_field_rejected(self):
        src=self.fake_white_label(22)
        dst=np.random.default_rng(0).integers(0,256,size=(250,250),dtype=np.uint8)
        with patch('scale_calibration._ocr_text',return_value=('5nm',None,'')):
            r=detect_scale(src)
        with self.assertRaises(ValueError):
            transfer_calibration(r,src,dst)

if __name__=='__main__':unittest.main()
