"""Small arithmetic checks that run without Kaggle or image downloads."""

import unittest

import numpy as np

from tools.ml.tst100k.adaptive_rules_core import BASELINE, FEATURE_NAMES, features, match, training_label


class AdaptiveRulesCoreTests(unittest.TestCase):
    def setUp(self):
        self.source = np.array([
            [[0.1, 0.2], [0.3, 0.4]],
            [[0.2, 0.3], [0.4, 0.5]],
            [[0.3, 0.4], [0.5, 0.6]],
        ], dtype=np.float64)

    def test_feature_schema_matches_browser_order(self):
        reference = self.source + 0.1
        result = features(self.source, reference)
        self.assertEqual(len(result), len(FEATURE_NAMES))
        np.testing.assert_allclose(result[:3], self.source.mean(axis=(1, 2)))
        np.testing.assert_allclose(result[12:15], [0.1, 0.1, 0.1])

    def test_identity_and_clamping(self):
        np.testing.assert_allclose(match(self.source, self.source, BASELINE), self.source)
        result = match(self.source, self.source + 1, np.array([1, 1]))
        self.assertTrue(np.all((result >= 0) & (result <= 1)))

    def test_label_prefers_existing_behavior_on_ties(self):
        np.testing.assert_allclose(training_label(self.source, self.source, self.source), BASELINE)


if __name__ == "__main__":
    unittest.main()
