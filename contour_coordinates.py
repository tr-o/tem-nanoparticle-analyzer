"""Contour drawing with explicit image coordinates.

All ROI-local contours MUST be translated to the coordinate frame of the
original image before drawing. This module intentionally never auto-registers
predicted masks against ground truth: doing so would hide model errors.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple
import cv2
import numpy as np


class CoordinateFrameError(ValueError):
    """The image/ROI cannot be placed in the same original-image frame."""


@dataclass(frozen=True)
class MaskROI:
    """One 2-D mask and its pixel coordinates in a full-resolution source.

    origin_xy is (x, y), NEVER (row, col). shape_hw is (height, width).
    source_key identifies the exact image/view from which the ROI was cut.
    """
    pixels: np.ndarray
    origin_xy: Tuple[int, int]
    shape_hw: Tuple[int, int]
    source_key: str

    def to_full(self, *, expected_key: str, expected_shape_hw: Tuple[int, int]) -> np.ndarray:
        if not self.source_key or self.source_key != expected_key:
            raise CoordinateFrameError("Mismatched image ID / coordinate frame")
        if self.shape_hw != tuple(expected_shape_hw):
            raise CoordinateFrameError(f"Original shape mismatch: {self.shape_hw} != {expected_shape_hw}")
        pixels = np.asarray(self.pixels)
        if pixels.ndim != 2 or pixels.size == 0:
            raise CoordinateFrameError("MaskROI must contain nonempty 2-D mask")
        h, w = pixels.shape
        x0, y0 = self.origin_xy
        H, W = self.shape_hw
        if type(x0) is not int or type(y0) is not int or not (0 <= x0 and 0 <= y0 and x0+w <= W and y0+h <= H):
            raise CoordinateFrameError("ROI origin is missing, wrong order, or outside full image")
        full = np.zeros(self.shape_hw, dtype=np.uint8)
        full[y0:y0+h, x0:x0+w] = pixels.astype(bool).astype(np.uint8)
        return full


def draw_roi_contours(image_rgb: np.ndarray, roi_mask: np.ndarray,
                      *, roi_origin_xy: Tuple[int,int], color_rgb: Tuple[int,int,int],
                      thickness: int = 1, line_type: int = cv2.LINE_AA) -> np.ndarray:
    """Draw ROI-local contours at the correct absolute position (mutates image).

    Important: coordinates from skimage.find_contours are (y, x). cv2 expects
    vertices as (x, y). We avoid the implicit (x0,y0) vs (r0,c0) trap.
    """
    if image_rgb.ndim != 3 or image_rgb.shape[2] != 3:
        raise CoordinateFrameError("expected a 3-channel RGB image")
    H, W = image_rgb.shape[:2]
    roi = MaskROI(np.asarray(roi_mask), tuple(roi_origin_xy), (H,W), "same-image")
    full = roi.to_full(expected_key="same-image", expected_shape_hw=(H,W))
    contours, _ = cv2.findContours(full, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    if contours:
        cv2.drawContours(image_rgb, contours, -1, tuple(map(int,color_rgb)), thickness, line_type)
    return image_rgb


def render_comparison(image_rgb: np.ndarray, blue: MaskROI, red: MaskROI, *,
                      source_key: str) -> np.ndarray:
    """Render two annotations on the exact same source image coordinate frame."""
    if image_rgb.ndim != 3 or image_rgb.shape[2] != 3:
        raise CoordinateFrameError("source must be RGB")
    H,W=image_rgb.shape[:2]
    blue_full = blue.to_full(expected_key=source_key,expected_shape_hw=(H,W))
    red_full = red.to_full(expected_key=source_key,expected_shape_hw=(H,W))
    result = image_rgb.copy()
    draw_roi_contours(result,blue_full,roi_origin_xy=(0,0),color_rgb=(30,80,230),thickness=2)
    draw_roi_contours(result,red_full,roi_origin_xy=(0,0),color_rgb=(230,45,35),thickness=2)
    return result
