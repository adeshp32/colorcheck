"""Guard the one-time selector audit against accidental model changes."""

import unittest

import numpy as np

from tools.ml.tst100k.final_selector import frozen_probability, review_groups
from tools.ml.tst100k.selector import FEATURE_NAMES


class FinalSelectorTests(unittest.TestCase):
    def test_frozen_probability_uses_saved_standardization(self):
        count = len(FEATURE_NAMES)
        package = {
            "featureNames": list(FEATURE_NAMES),
            "mean": [2.0] * count,
            "scale": [2.0] * count,
            "coefficients": [1.0] + [0.0] * (count - 1),
            "intercept": -0.5,
        }
        features = np.full((2, count), 2.0)
        features[1, 0] = 4.0
        expected = 1 / (1 + np.exp(-np.array([-0.5, 0.5])))
        np.testing.assert_allclose(frozen_probability(features, package), expected)

    def test_frozen_probability_rejects_feature_schema_drift(self):
        count = len(FEATURE_NAMES)
        package = {
            "featureNames": list(reversed(FEATURE_NAMES)),
            "mean": [0.0] * count,
            "scale": [1.0] * count,
            "coefficients": [0.0] * count,
            "intercept": 0.0,
        }
        with self.assertRaisesRegex(RuntimeError, "schema"):
            frozen_probability(np.zeros((1, count)), package)

    def test_review_groups_are_fixed_and_nonoverlapping(self):
        rows = [{} for _ in range(32)]
        gains = np.arange(32, dtype=float)
        groups = review_groups(rows, gains)
        self.assertEqual(groups["worst"], [0, 1, 2, 3])
        self.assertEqual(groups["best"], [28, 29, 30, 31])
        self.assertEqual(groups, review_groups(rows, gains))
        self.assertEqual(len(set(sum(groups.values(), []))), 12)


if __name__ == "__main__":
    unittest.main()
