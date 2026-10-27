"""The final decision must reject severe individual regressions."""

import unittest

import numpy as np

from tools.ml.tst100k.train_final_decision import measured_gates, route
from tools.ml.tst100k.selector import FEATURE_NAMES


def measurements(count: int = 64) -> dict[str, np.ndarray]:
    values = {
        "lutError": np.full(count, 8.0), "statsError": np.full(count, 10.0),
        "wrongLutError": np.full(count, 12.0), "wrongStatsError": np.full(count, 12.0),
        "lutSsim": np.full(count, 0.92), "statsSsim": np.full(count, 0.90),
        "lutClipping": np.full(count, 1.0), "statsClipping": np.full(count, 2.0),
        "strongEdit": np.arange(count) < 40,
    }
    return values


class FinalDecisionTrainingTests(unittest.TestCase):
    def test_route_uses_exported_linear_math(self):
        width = len(FEATURE_NAMES)
        package = {
            "featureNames": FEATURE_NAMES, "mean": [0] * width, "scale": [1] * width,
            "coefficients": [1] + [0] * (width - 1), "intercept": 0,
        }
        rows = np.zeros((2, width))
        rows[:, 0] = [0.3, 0.2]
        np.testing.assert_array_equal(route(rows, package), [True, False])

    def test_severe_tail_blocks_otherwise_good_average(self):
        data = measurements()
        chosen = np.ones(64, dtype=bool)
        baseline = np.zeros(64, dtype=bool)
        result = measured_gates(data, chosen, chosen, baseline)
        self.assertTrue(result["allFinalGatesPass"])
        data["lutError"][0] = 17.0
        result = measured_gates(data, chosen, chosen, baseline)
        self.assertFalse(result["finalGates"]["worstCase"])
        self.assertFalse(result["allFinalGatesPass"])


if __name__ == "__main__":
    unittest.main()
