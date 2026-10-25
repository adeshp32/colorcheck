"""Pure manifest checks before a remote training run consumes resources."""

import unittest

from tools.ml.tst100k.prepare_selector import checksum, scene_set, select_rows


class SelectorPreflightTests(unittest.TestCase):
    def test_partitions_have_disjoint_target_and_reference_scenes(self):
        rows = [
            {"content": f"content/{index}.jpg", "reference": f"style/{index + 100}.jpg",
             "gt": f"edited/{index}_edit.jpg"}
            for index in range(20)
        ]
        selected = select_rows(rows, {"0", "100"}, {"train": 5, "validation": 3, "final": 2})
        self.assertEqual([len(group) for group in selected.values()], [5, 3, 2])
        groups = [scene_set(group) for group in selected.values()]
        self.assertTrue(all(not left & right for i, left in enumerate(groups)
                            for right in groups[i + 1:]))
        self.assertTrue(all(not group & {"0", "100"} for group in groups))

    def test_rejects_insufficient_unseen_rows(self):
        row = {"content": "1.jpg", "reference": "2.jpg", "gt": "1_edit.jpg"}
        with self.assertRaisesRegex(ValueError, "Insufficient unseen final"):
            select_rows([row], set(), {"train": 1, "final": 1})

    def test_checksum_is_independent_of_key_order(self):
        self.assertEqual(checksum({"a": 1, "b": 2}), checksum({"b": 2, "a": 1}))


if __name__ == "__main__":
    unittest.main()
