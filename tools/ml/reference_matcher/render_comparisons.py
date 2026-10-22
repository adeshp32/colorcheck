"""Render a held-out comparison sheet for qualitative photographic review.

Metrics decide whether a model is eligible for deployment, but a compact contact
sheet helps a person spot objectionable casts, flattened skin, clipped skies, or
other failures that one aggregate number can hide. The sheet is an experiment
artifact only; dataset photographs are never committed to the repository.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from PIL import Image, ImageDraw, ImageFont

from .dataset import FiveKReferenceDataset, SplitManifest
from .evaluation import statistics_match
from .model import ReferenceLutModel, apply_lut


def load_splits(path: Path) -> SplitManifest:
    """Reconstruct the immutable scene split recorded by training."""
    payload = json.loads(path.read_text())
    return SplitManifest(
        train=tuple(payload["train"]),
        validation=tuple(payload["validation"]),
        test=tuple(payload["test"]),
    )


def tensor_to_image(tensor: torch.Tensor, tile_size: int) -> Image.Image:
    """Convert one bounded CHW tensor into a consistently sized RGB tile."""
    pixels = (
        tensor.detach().float().clamp(0, 1).mul(255).round().byte().permute(1, 2, 0)
    )
    image = Image.fromarray(pixels.cpu().numpy())
    return image.resize((tile_size, tile_size), Image.Resampling.LANCZOS)


def sample_indices(dataset_size: int, count: int) -> list[int]:
    """Choose reproducible, evenly distributed examples across scenes/experts."""
    if dataset_size < 1 or count < 1:
        raise ValueError("Dataset size and sample count must both be positive")
    count = min(count, dataset_size)
    if count == 1:
        return [0]
    return [round(index * (dataset_size - 1) / (count - 1)) for index in range(count)]


@torch.no_grad()
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--splits", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dataset-zip", type=Path)
    source.add_argument("--dataset-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--tile-size", type=int, default=192)
    args = parser.parse_args()

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    config = checkpoint["config"]
    model = ReferenceLutModel(config["basis_count"], config["lut_size"])
    model.load_state_dict(checkpoint["model"])
    model.eval()

    splits = load_splits(args.splits)
    dataset = FiveKReferenceDataset(
        args.dataset_zip or args.dataset_root,
        splits.test,
        image_size=config["image_size"],
        training=False,
        seed=config["seed"],
    )

    labels = ("Source", "Reference", "Expected", "Learned", "Statistics")
    header_height = 30
    row_height = args.tile_size + header_height
    row_count = min(args.samples, len(dataset))
    sheet = Image.new(
        "RGB",
        (len(labels) * args.tile_size, header_height + row_height * row_count),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for column, label in enumerate(labels):
        draw.text((column * args.tile_size + 8, 10), label, fill="black", font=font)

    for row, index in enumerate(sample_indices(len(dataset), args.samples)):
        sample = dataset[index]
        source_image = sample["source"].unsqueeze(0)
        reference = sample["reference"].unsqueeze(0)
        lut, _ = model(source_image, reference)
        learned = apply_lut(source_image, lut)[0]
        baseline = statistics_match(source_image, reference)[0]
        tiles = (
            sample["source"],
            sample["reference"],
            sample["expected"],
            learned,
            baseline,
        )
        row_top = header_height + row * row_height
        draw.text(
            (8, row_top + 9),
            f"{sample['scene']} | expert {sample['expert']}",
            fill="black",
            font=font,
        )
        for column, tile in enumerate(tiles):
            sheet.paste(
                tensor_to_image(tile, args.tile_size),
                (column * args.tile_size, row_top + header_height),
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output, format="JPEG", quality=92, optimize=True)
    print(f"Wrote held-out comparison sheet: {args.output}")


if __name__ == "__main__":
    main()
