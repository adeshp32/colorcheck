"""Small, data-free checks for the TST100K experiment contract."""

from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader

from tools.ml.reference_matcher.model import ReferenceLutModel
from tools.ml.tst100k.data import TripletDataset, _download_one, scene_id, scene_split, select_triplets
from tools.ml.tst100k.fresh_evaluation import fresh_rows
from tools.ml.tst100k.prepare_v4 import FINAL_COUNT, select_final_rows
from tools.ml.tst100k.review import example_groups, render_group
from tools.ml.tst100k.train import edit_emphasis_loss, evaluate, train_epoch
from tools.ml.tst100k.train_v4 import validation_gates


class TstPilotTests(unittest.TestCase):
    def test_v4_loss_and_validation_gates(self):
        source = torch.zeros(2, 3, 4, 4)
        expected = torch.stack((torch.full((3, 4, 4), 0.05), torch.full((3, 4, 4), 0.3)))
        self.assertEqual(float(edit_emphasis_loss(expected, expected, source)), 0)
        self.assertGreater(float(edit_emphasis_loss(source, expected, source)), 0)
        baseline = {"model": {"deltaE2000": {"mean": 10.0}, "ssim": {"mean": 0.90}, "clippingPercent": {"mean": 2.0}}}
        candidate = {
            "model": {"deltaE2000": {"mean": 10.05}, "ssim": {"mean": 0.896}, "clippingPercent": {"mean": 2.8}},
            "modelVsWrongReference": {"mean": 0.2},
        }
        self.assertTrue(all(validation_gates(candidate, baseline, 8.0, 8.6, 59).values()))
        self.assertFalse(validation_gates(candidate, baseline, 8.2, 8.6, 59)["strongEditGain"])

    def test_v4_final_set_excludes_every_prior_scene(self):
        rows = [
            {
                "content": f"content_images/00/{index:05d}.jpg",
                "reference": f"style_images/000/{index + 10000:05d}_1000.png",
                "gt": f"style_images/000/{index:05d}_1000.png",
            }
            for index in range(300)
        ]
        old = {"train": rows[:8], "validation": rows[8:12], "test": rows[12:16]}
        audit = rows[16:24]
        final = select_final_rows(rows, old, audit)
        self.assertEqual(len(final), FINAL_COUNT)
        self.assertEqual(final, select_final_rows(rows, old, audit))
        seen = {scene_id(row[key]) for sample in (*old.values(), audit) for row in sample for key in ("content", "reference")}
        self.assertTrue(all(scene_id(row[key]) not in seen for row in final for key in ("content", "reference")))
        self.assertEqual(len({scene_id(row["content"]) for row in final}), FINAL_COUNT)

    def test_fresh_evaluation_excludes_old_targets_and_references(self):
        rows = [
            {
                "content": f"content_images/00/{index:05d}.jpg",
                "reference": f"style_images/000/{index + 100:05d}_1000.png",
                "gt": f"style_images/000/{index:05d}_1000.png",
            }
            for index in range(8)
        ]
        old = {"train": [rows[0]], "validation": [rows[1]], "test": [rows[2]]}
        candidates = rows + [
            {**rows[3], "reference": rows[0]["content"]},
            {**rows[4], "content": rows[1]["reference"]},
        ]
        selected = fresh_rows(candidates, old, 5, seed=7)
        self.assertEqual({scene_id(row["content"]) for row in selected}, {f"{i:05d}" for i in range(3, 8)})
        excluded = {"00000", "00001", "00002", "00100", "00101", "00102"}
        self.assertTrue(all(scene_id(row[key]) not in excluded for row in selected for key in ("content", "reference")))
        self.assertEqual(selected, fresh_rows(candidates, old, 5, seed=7))

    def test_visual_review_shows_weak_random_and_strong_scenes(self):
        scores = [{"scene": str(index), "gain": float(index)} for index in range(20)]
        groups = example_groups(scores)
        self.assertEqual(groups["worst"], ["0", "1", "2", "3"])
        self.assertEqual(groups["best"], ["16", "17", "18", "19"])
        self.assertEqual(len(set(sum(groups.values(), []))), 12)

    def test_visual_review_renders_side_by_side_sheet(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            rows = []
            for index in range(2):
                paths = {
                    "content": f"content_images/00/{index:05d}.png",
                    "reference": f"style_images/000/{index + 10:05d}_1000.png",
                    "gt": f"style_images/000/{index:05d}_1000.png",
                }
                for path in paths.values():
                    file = root / path
                    file.parent.mkdir(parents=True, exist_ok=True)
                    Image.new("RGB", (16, 16), (80 + index, 100, 120)).save(file)
                rows.append(paths)
            destination = root / "review.png"
            render_group(ReferenceLutModel(lut_size=5), rows, root, ["00000", "00001"], destination)
            with Image.open(destination) as sheet:
                self.assertEqual(sheet.size, (1280, 604))

    def test_rate_limit_pauses_all_image_requests_before_retry(self):
        class Pacer:
            waits = 0
            pauses = []

            def wait(self):
                self.waits += 1

            def pause_for(self, seconds):
                self.pauses.append(seconds)

        buffer = BytesIO()
        Image.new("RGB", (2, 2), "red").save(buffer, format="PNG")
        blocked = HTTPError("https://example.test/photo.png", 429, "rate limited", {"Retry-After": "1"}, None)
        pacer = Pacer()
        with tempfile.TemporaryDirectory() as folder:
            with patch("tools.ml.tst100k.data.urlopen", side_effect=[blocked, BytesIO(buffer.getvalue())]):
                count = _download_one(Path(folder), "photo.png", 1000, pacer)
            self.assertEqual(count, len(buffer.getvalue()))
            self.assertEqual(pacer.waits, 2)
            self.assertGreaterEqual(pacer.pauses[0], 20)

    def test_split_never_reuses_scene_across_partitions(self):
        rows = [
            {
                "content": f"content_images/00/{index:05d}.jpg",
                "reference": f"style_images/000/{index + 20000:05d}_1000.png",
                "gt": f"style_images/000/{index:05d}_1000.png",
            }
            for index in range(2000)
        ]
        selected = select_triplets(rows, (30, 8, 8), seed=42)
        seen = {}
        for split, samples in selected.items():
            for row in samples:
                for name in ("content", "reference", "gt"):
                    identifier = scene_id(row[name])
                    self.assertEqual(scene_split(identifier, 42), split)
                    self.assertEqual(seen.setdefault(identifier, split), split)
        self.assertEqual(selected, select_triplets(rows, (30, 8, 8), seed=42))

    def test_train_and_evaluate_tiny_real_image_triplets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            rows = []
            for index in range(4):
                source = np.full((16, 16, 3), 50 + index * 20, dtype=np.uint8)
                reference = np.full((16, 16, 3), 100 + index * 20, dtype=np.uint8)
                target = np.clip(source.astype(np.int16) + 10, 0, 255).astype(np.uint8)
                paths = {
                    "content": f"content_images/00/{index:05d}.png",
                    "reference": f"style_images/000/{index + 10:05d}_1000.png",
                    "gt": f"style_images/000/{index:05d}_1000.png",
                }
                for key, pixels in (("content", source), ("reference", reference), ("gt", target)):
                    path = root / paths[key]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    Image.fromarray(pixels).save(path)
                rows.append(paths)
            loader = DataLoader(TripletDataset(rows, root, 16), batch_size=2)
            model = ReferenceLutModel(lut_size=5)
            optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
            scaler = torch.amp.GradScaler("cuda", enabled=False)
            before = model.basis.detach().clone()
            record = train_epoch(model, loader, optimizer, scaler, torch.device("cpu"), 1)
            self.assertTrue(np.isfinite(record["loss"]))
            self.assertFalse(torch.equal(before, model.basis))
            emphasized = train_epoch(model, loader, optimizer, scaler, torch.device("cpu"), 2, emphasize_edits=True)
            self.assertTrue(np.isfinite(emphasized["loss"]))
            report = evaluate(model, loader, torch.device("cpu"), 42)
            self.assertEqual(report["model"]["deltaE2000"]["n"], 4)
            self.assertEqual(report["model"]["ssim"]["n"], 4)
            self.assertEqual(report["model"]["edgeMae"]["n"], 4)
            self.assertEqual(report["model"]["clippingPercent"]["n"], 4)
            self.assertEqual(report["modelVsWrongReference"]["n"], 4)
            self.assertEqual(report["modelVsStatisticsSsim"]["n"], 4)


if __name__ == "__main__":
    unittest.main()
