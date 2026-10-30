"""Check the supported package entry points and distributed synthetic RF.

These tests intentionally DO NOT attribute v13/v15 EMPS benchmark scores to
the old synthetic or weak-label models.
"""
from __future__ import annotations
import unittest
from pathlib import Path
import numpy as np
from tem_analyzer.cli import ROOT
from tem_analyzer.legacy_rf import feature_stack, predict_probability, split_instances, measure_particles
from tem_analyzer.geometry import MaskROI, CoordinateFrameError


class SupportedCoreTests(unittest.TestCase):
    def test_root_is_clean(self):
        stray = [p.name for p in ROOT.iterdir()
                 if p.is_file() and p.suffix in (".py", ".joblib", ".json")]
        self.assertEqual(stray, [])

    def test_model_registry(self):
        self.assertTrue((ROOT/"models"/"synthetic_rf.joblib").is_file())
        self.assertTrue((ROOT/"models"/"weak_tem_rf.joblib").is_file())
        self.assertTrue((ROOT/"models"/"README.md").is_file())

    def test_real_serialized_synthetic_model_predicts(self):
        image = np.full((42, 48), 0.80, dtype=np.float32)
        image[15:26, 18:30] = 0.36
        features = feature_stack(image)
        prob = predict_probability(ROOT/"models"/"synthetic_rf.joblib", image)
        self.assertEqual(prob.shape, image.shape)
        self.assertEqual(features.shape[:2], image.shape)
        self.assertTrue(np.isfinite(prob).all())
        self.assertGreaterEqual(float(prob.min()), 0)
        self.assertLessEqual(float(prob.max()), 1)
        labels, _ = split_instances(prob)
        self.assertEqual(labels.shape, image.shape)
        self.assertIsInstance(measure_particles(labels), list)

    def test_geometry_rejects_wrong_source(self):
        m = MaskROI(np.ones((5,5), np.uint8), (4,7), (30,40), "source-a")
        with self.assertRaises(CoordinateFrameError):
            m.to_full(expected_key="source-b", expected_shape_hw=(30,40))


if __name__ == "__main__":
    unittest.main()
