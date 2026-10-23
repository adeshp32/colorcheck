"""Small, data-free checks for the TST100K experiment contract."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader

from tools.ml.reference_matcher.model import ReferenceLutModel
from tools.ml.tst100k.data import TripletDataset, scene_id, scene_split, select_triplets
from tools.ml.tst100k.train import evaluate, train_epoch


class TstPilotTests(unittest.TestCase):
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
            report = evaluate(model, loader, torch.device("cpu"), 42)
            self.assertEqual(report["model"]["deltaE2000"]["n"], 4)
            self.assertEqual(report["model"]["ssim"]["n"], 4)
            self.assertEqual(report["model"]["edgeMae"]["n"], 4)
            self.assertEqual(report["model"]["clippingPercent"]["n"], 4)
            self.assertEqual(report["modelVsWrongReference"]["n"], 4)
            self.assertEqual(report["modelVsStatisticsSsim"]["n"], 4)


if __name__ == "__main__":
    unittest.main()
