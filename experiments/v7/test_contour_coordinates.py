"""Regression tests for incorrect ROI-offset contour overlays."""
from __future__ import annotations
import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import cv2
import numpy as np
from contour_coordinates import MaskROI,render_comparison,draw_roi_contours,CoordinateFrameError
from experiments.v7.diagnose_overlay_shift import best_translation,shifted,near_overlap_score


class TestAbsoluteCoordinates(unittest.TestCase):
    def setUp(self):
        self.image=np.full((140,160,3),190,np.uint8)
        self.mask=np.zeros((26,28),np.uint8)
        cv2.circle(self.mask,(13,12),8,1,-1)

    def test_roi_origin_xy_is_applied_to_drawing(self):
        out=draw_roi_contours(self.image.copy(),self.mask,roi_origin_xy=(24,57),color_rgb=(255,0,0),thickness=2)
        # roi pixel y=69, x=37; its boundary is at +/- 8 pixels
        self.assertGreater(np.sum((out[54:83,22:54,0] == 255)),5)
        self.assertEqual(int(np.count_nonzero(out[:25,:25,0]==255)),0)

    def test_full_reference_frame_comparison_is_not_shifted(self):
        a=MaskROI(self.mask,(24,57),(140,160),'micrograph-a')
        b=MaskROI(self.mask.copy(),(24,57),(140,160),'micrograph-a')
        im=render_comparison(self.image,a,b,source_key='micrograph-a')
        self.assertTrue((im[57:84,24:53,0]!=190).any())
        self.assertFalse((im[:30,:30]!=190).any())

    def test_different_source_is_error(self):
        a=MaskROI(self.mask,(24,57),(140,160),'micrograph-a')
        b=MaskROI(self.mask,(24,57),(140,160),'micrograph-b')
        with self.assertRaises(CoordinateFrameError):
            render_comparison(self.image,a,b,source_key='micrograph-a')

    def test_outside_crop_is_error(self):
        bad=MaskROI(self.mask,(150,120),(140,160),'micrograph-a')
        with self.assertRaises(CoordinateFrameError):
            bad.to_full(expected_key='micrograph-a',expected_shape_hw=(140,160))

    def test_crop_with_wrong_full_shape_is_error(self):
        bad=MaskROI(self.mask,(24,57),(120,160),'micrograph-a')
        with self.assertRaises(CoordinateFrameError):
            bad.to_full(expected_key='micrograph-a',expected_shape_hw=(140,160))

    def test_known_offset_found_and_fixed_for_diagnostic_only(self):
        yy,xx=np.ogrid[:180,:190]
        blue=np.zeros((180,190),np.uint8)
        for cy,cx,r in [(34,42,11),(100,123,18),(135,42,8)]:
            cv2.circle(blue,(cx,cy),r,1,2)
        red=shifted(blue,-10,29)
        dx,dy=best_translation(blue,red,55)
        self.assertEqual((dx,dy),(10,-29))
        self.assertGreater(near_overlap_score(blue,shifted(red,dx,dy)),.9)

if __name__=='__main__':unittest.main()
