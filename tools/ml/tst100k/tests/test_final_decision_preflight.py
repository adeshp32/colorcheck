"""A new decision experiment must not recycle old photos."""

import unittest

from tools.ml.tst100k.prepare_final_decision import excluded_scenes
from tools.ml.tst100k.prepare_selector import scene_set, select_rows


def row(target: int, reference: int) -> dict:
    return {"content": f"content/{target}.jpg", "reference": f"style/{reference}.jpg",
            "gt": f"edited/{target}_edit.jpg"}


class FinalDecisionPreflightTests(unittest.TestCase):
    def test_excludes_all_old_roles_and_sealed_scenes(self):
        revision = "63bf13833b75407c862d608c3d81281d0a35b61f"
        excluded = excluded_scenes(
            {"datasetRevision": revision, "splits": {"train": [row(1, 2)]}},
            {"rows": [row(3, 4)]},
            {"datasetRevision": revision, "rows": [row(5, 6)]},
            {"datasetRevision": revision, "splits": {
                "train": [row(7, 8)], "validation": [row(9, 10)],
                "final": [row(11, 12)],
            }},
        )
        self.assertEqual(excluded, {str(value) for value in range(1, 13)})
        fresh = [row(1, 20), row(21, 2), row(22, 23), row(24, 25)]
        splits = select_rows(fresh, excluded, {"train": 1, "final": 1}, seed=8413)
        self.assertEqual(sum(len(group) for group in splits.values()), 2)
        self.assertFalse(scene_set([item for group in splits.values() for item in group]) & excluded)

    def test_rejects_revision_mismatch(self):
        with self.assertRaisesRegex(RuntimeError, "different dataset revision"):
            excluded_scenes(
                {"datasetRevision": "other", "splits": {}}, {"rows": []},
                {"datasetRevision": "other", "rows": []},
                {"datasetRevision": "other", "splits": {}},
            )


if __name__ == "__main__":
    unittest.main()
