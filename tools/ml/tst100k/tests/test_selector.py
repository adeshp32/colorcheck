"""Guard the selector's inference-only feature contract and scoring gates."""

import unittest

import numpy as np
import torch

from tools.ml.tst100k.selector import FEATURE_NAMES, selector_features
from tools.ml.tst100k.train_selector import labels_from_errors, validation_metrics


class SelectorFeatureTests(unittest.TestCase):
    def test_fixed_schema_and_no_expert_image_argument(self):
        source = torch.full((2, 3, 4, 4), 0.4)
        reference = torch.full_like(source, 0.6)
        lut = source + 0.1
        statistics = source + 0.2
        result = selector_features(source, reference, lut, statistics)
        self.assertEqual(result.shape, (2, len(FEATURE_NAMES)))
        self.assertTrue(torch.isfinite(result).all())
        self.assertAlmostEqual(result[0, FEATURE_NAMES.index("candidate_disagreement_mae")].item(), 0.1, places=5)

    def test_mismatched_shape_rejected(self):
        image = torch.zeros((1, 3, 4, 4))
        with self.assertRaises(ValueError):
            selector_features(image, image, image[:, :, :2], image)

    def test_tie_labels_are_not_used_for_fitting(self):
        labels, included = labels_from_errors(
            np.array([1.0, 2.0, 1.0]), np.array([2.0, 1.0, 1.1])
        )
        self.assertEqual(labels.tolist(), [1, 0, 0])
        self.assertEqual(included.tolist(), [True, True, False])

    def test_always_baseline_fails_usefulness_gate(self):
        measured = validation_metrics(
            np.array([2.0, 3.0]), np.array([1.0, 1.0]),
            np.array([2.0, 3.0]), np.array([1.0, 1.0]),
            np.array([0.9, 0.9]), np.array([0.9, 0.9]),
            np.array([1.0, 1.0]), np.array([1.0, 1.0]),
            np.array([False, False]), np.array([False, False]),
        )
        self.assertFalse(measured["gates"]["selectsLutOftenEnough"])
        self.assertFalse(measured["allGatesPass"])


if __name__ == "__main__":
    unittest.main()
