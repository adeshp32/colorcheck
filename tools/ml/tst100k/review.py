"""Create honest, held-out visual comparisons without using a GPU.

The existing Kaggle checkpoint and split manifest are mounted as a kernel
source. This script never trains or chooses a checkpoint from test examples.
It ranks examples only to make both strong and weak cases easy to inspect.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageOps
from torch.utils.data import DataLoader

from tools.ml.reference_matcher.evaluation import metric_samples, statistics_match
from tools.ml.reference_matcher.model import ReferenceLutModel, apply_lut
from .data import TripletDataset, scene_id, stage_images


def find_source_file(name: str) -> Path:
    """Find one mounted file from the pinned training run's Kaggle output."""
    matches = sorted(Path("/kaggle/input").rglob(name))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one mounted {name}, found {len(matches)}: {matches[:4]}")
    return matches[0]


def full_image(path: Path, size: int = 256) -> torch.Tensor:
    """Decode one file for a larger visual comparison, not model selection."""
    with Image.open(path) as loaded:
        image = ImageOps.exif_transpose(loaded).convert("RGB")
        image = image.resize((size, size), Image.Resampling.BILINEAR)
        array = np.asarray(image).copy()
    return torch.from_numpy(array).permute(2, 0, 1).float().div_(255).unsqueeze(0)


def to_image(tensor: torch.Tensor) -> Image.Image:
    pixels = tensor.squeeze(0).detach().clamp(0, 1).mul(255).byte().permute(1, 2, 0).numpy()
    return Image.fromarray(pixels)


@torch.inference_mode()
def score_test_rows(model: ReferenceLutModel, rows: list[dict], root: Path) -> list[dict]:
    """Measure paired gains for every test scene before choosing examples."""
    loader = DataLoader(TripletDataset(rows, root, 128), batch_size=8, num_workers=2)
    scores = []
    for batch in loader:
        source, reference, expected = (batch[key] for key in ("source", "reference", "expected"))
        lut, _ = model(source, reference)
        predicted = apply_lut(source, lut).float()
        baseline = statistics_match(source, reference)
        model_error = metric_samples(predicted, expected)["deltaE2000"].tolist()
        baseline_error = metric_samples(baseline, expected)["deltaE2000"].tolist()
        for identifier, model_value, baseline_value in zip(batch["scene"], model_error, baseline_error):
            scores.append({
                "scene": identifier,
                "modelDeltaE2000": model_value,
                "baselineDeltaE2000": baseline_value,
                "gain": baseline_value - model_value,
            })
    if len(scores) != len(rows):
        raise RuntimeError("Review did not score every held-out target")
    return scores


def example_groups(scores: list[dict]) -> dict[str, list[str]]:
    """Show weak, random, and strong cases without hiding failures."""
    ordered = sorted(scores, key=lambda row: row["gain"])
    worst = [row["scene"] for row in ordered[:4]]
    best = [row["scene"] for row in ordered[-4:]]
    remaining = [row["scene"] for row in scores if row["scene"] not in set(worst + best)]
    typical = random.Random(2027).sample(remaining, 4)
    return {"worst": worst, "random": typical, "best": best}


@torch.inference_mode()
def render_group(
    model: ReferenceLutModel, rows: list[dict], root: Path, scenes: list[str], output: Path
) -> None:
    """Render source, reference, current matcher, model, and expected edit."""
    by_scene = {scene_id(row["content"]): row for row in rows}
    names = ("Source", "Reference", "Current", "Trained", "Expected")
    tile = 256
    label_height = 46
    sheet = Image.new("RGB", (tile * len(names), (tile + label_height) * len(scenes)), "#eeeeee")
    draw = ImageDraw.Draw(sheet)
    for row_index, identifier in enumerate(scenes):
        row = by_scene[identifier]
        source, reference, expected = (
            full_image(root / row[key]) for key in ("content", "reference", "gt")
        )
        small_source = torch.nn.functional.interpolate(source, size=(128, 128), mode="bilinear")
        small_reference = torch.nn.functional.interpolate(reference, size=(128, 128), mode="bilinear")
        lut, _ = model(small_source, small_reference)
        current = statistics_match(source, reference)
        trained = apply_lut(source, lut).float()
        for column, (name, tensor) in enumerate(zip(names, (source, reference, current, trained, expected))):
            left = column * tile
            top = row_index * (tile + label_height)
            draw.text((left + 8, top + 7), f"{name} | scene {identifier}", fill="#111111")
            sheet.paste(to_image(tensor), (left, top + label_height))
    sheet.save(output, optimize=True)


def main() -> None:
    torch.set_num_threads(4)
    checkpoint_path = find_source_file("best.pt")
    split_path = find_source_file("splits.json")
    rows = json.loads(split_path.read_text())["splits"]["test"]
    output = Path("/kaggle/working/colorcheck-tst100k-review")
    scratch = Path("/kaggle/temp/colorcheck-tst100k-review")
    output.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"checkpoint": str(checkpoint_path), "testScenes": len(rows)}), flush=True)
    staged = stage_images({"test": rows}, scratch)
    print(json.dumps({"staged": staged}), flush=True)

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    model = ReferenceLutModel()
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    scores = score_test_rows(model, rows, scratch)
    groups = example_groups(scores)
    by_scene = {row["scene"]: row for row in scores}
    for name, identifiers in groups.items():
        render_group(model, rows, scratch, identifiers, output / f"{name}.png")
    review = {
        "checkpointEpoch": checkpoint["epoch"],
        "testScenes": len(rows),
        "worseThanCurrentCount": sum(row["gain"] < 0 for row in scores),
        "groups": {name: [by_scene[identifier] for identifier in scenes] for name, scenes in groups.items()},
        "note": "Examples are for human quality review, not checkpoint or hyperparameter selection.",
    }
    (output / "review.json").write_text(json.dumps(review, indent=2))
    print(json.dumps({"worseThanCurrentCount": review["worseThanCurrentCount"], "groups": groups}), flush=True)


if __name__ == "__main__":
    main()
