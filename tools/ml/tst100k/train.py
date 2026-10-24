"""Train a compact reference-conditioned LUT on TST100K triplets.

This pilot measures whether a correct reference improves a held-out target,
not merely whether generic retouching looks pleasant. Only validation selects
the checkpoint; the test set is evaluated once after training.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from contextlib import nullcontext
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from tools.ml.reference_matcher.evaluation import metric_samples, statistics_match
from tools.ml.reference_matcher.losses import ReferenceMatchLoss, reference_ranking_loss
from tools.ml.reference_matcher.model import ReferenceLutModel, apply_lut
from .data import SPLITS, TripletDataset, fetch_manifest, save_split_manifest, select_triplets, stage_images


def mean_interval(values: list[float], seed: int) -> dict:
    """Report a 95% bootstrap interval across distinct target photographs."""
    samples = np.asarray(values, dtype=np.float64)
    if not len(samples):
        raise ValueError("Cannot report an empty evaluation set")
    generator = np.random.default_rng(seed)
    estimates = samples[generator.integers(0, len(samples), (1000, len(samples)))].mean(1)
    low, high = np.percentile(estimates, [2.5, 97.5])
    return {"mean": float(samples.mean()), "ci95": [float(low), float(high)], "n": len(samples)}


def image_batch(batch: dict, device: torch.device) -> tuple[torch.Tensor, ...]:
    """Move the three image tensors to GPU; keep metadata on the CPU."""
    return tuple(batch[key].to(device, non_blocking=True) for key in ("source", "reference", "expected"))


def autocast_context(device: torch.device):
    """Use a fast CUDA format while keeping local CPU checks in full precision."""
    if device.type != "cuda":
        return nullcontext()
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    return torch.autocast("cuda", dtype=dtype)


@torch.no_grad()
def evaluate(model: ReferenceLutModel, loader: DataLoader, device: torch.device, seed: int) -> dict:
    """Measure correct, wrong, identity, and existing statistics matching."""
    model.eval()
    metrics = {
        name: {metric: [] for metric in ("deltaE2000", "mae", "ssim", "edgeMae", "clippingPercent")}
        for name in ("model", "wrongReference", "identity", "statistics")
    }
    difference = []
    started = time.perf_counter()
    for batch in loader:
        source, reference, expected = image_batch(batch, device)
        if len(source) < 2:
            raise ValueError("Evaluation needs at least two references per batch")
        wrong_reference = reference.roll(1, 0)
        with autocast_context(device):
            lut, _ = model(source, reference)
            wrong_lut, _ = model(source, wrong_reference)
            output = apply_lut(source, lut).float()
            wrong = apply_lut(source, wrong_lut).float()
        images = {
            "model": output,
            "wrongReference": wrong,
            "identity": source,
            "statistics": statistics_match(source, reference),
        }
        for name, image in images.items():
            samples = metric_samples(image, expected)
            for metric in metrics[name]:
                metrics[name][metric].extend(samples[metric].cpu().tolist())
        difference.extend((output - wrong).abs().flatten(1).mean(1).cpu().tolist())
    results = {
        name: {
            ("rgbMae" if metric == "mae" else metric): mean_interval(values, seed)
            for metric, values in sample_metrics.items()
        }
        for name, sample_metrics in metrics.items()
    }
    results["modelVsWrongReference"] = mean_interval(
        (np.asarray(metrics["wrongReference"]["deltaE2000"]) - np.asarray(metrics["model"]["deltaE2000"])).tolist(), seed
    )
    results["modelVsStatistics"] = mean_interval(
        (np.asarray(metrics["statistics"]["deltaE2000"]) - np.asarray(metrics["model"]["deltaE2000"])).tolist(), seed
    )
    results["modelVsIdentity"] = mean_interval(
        (np.asarray(metrics["identity"]["deltaE2000"]) - np.asarray(metrics["model"]["deltaE2000"])).tolist(), seed
    )
    results["modelVsStatisticsSsim"] = mean_interval(
        (np.asarray(metrics["model"]["ssim"]) - np.asarray(metrics["statistics"]["ssim"])).tolist(), seed
    )
    results["referenceSensitivityRgbMae"] = mean_interval(difference, seed)
    results["elapsedSeconds"] = time.perf_counter() - started
    return results


def edit_emphasis_loss(output: torch.Tensor, expected: torch.Tensor, source: torch.Tensor) -> torch.Tensor:
    """Give stronger expert edits more weight without changing inference.

    The batch-relative weights are bounded and renormalized. The channel-mean
    term asks the LUT to reach the intended global shift, not invent geometry.
    """
    edit_size = (expected - source).abs().flatten(1).mean(1).detach()
    weights = (0.75 + edit_size / edit_size.mean().clamp_min(1e-6)).clamp(0.75, 2.0)
    weights = weights / weights.mean()
    per_image = (output - expected).abs().flatten(1).mean(1)
    weighted_pixel = (weights * per_image).mean()
    channel_mean = (output.mean(dim=(2, 3)) - expected.mean(dim=(2, 3))).abs().mean()
    return 0.25 * weighted_pixel + 0.25 * channel_mean


def train_epoch(model, loader, optimizer, scaler, device, epoch: int, *, emphasize_edits: bool = False) -> dict:
    """Update the model using real triplets and explicit reference controls."""
    model.train()
    criterion = ReferenceMatchLoss()
    totals = {"loss": 0.0, "reconstruction": 0.0, "ranking": 0.0, "identity": 0.0}
    started = time.perf_counter()
    for step, batch in enumerate(loader):
        source, reference, expected = image_batch(batch, device)
        wrong_reference = reference.roll(1, 0)
        optimizer.zero_grad(set_to_none=True)
        with autocast_context(device):
            lut, _ = model(source, reference)
            wrong_lut, _ = model(source, wrong_reference)
            output = apply_lut(source, lut).float()
            wrong_output = apply_lut(source, wrong_lut).float()
            reconstruction, _ = criterion(output, expected, source, lut.float())
            ranking = reference_ranking_loss(output, wrong_output, expected, margin=0.01)
            # On every fourth step, teach a neutral reference to preserve the
            # source. This is a counterfactual training example, not a label.
            identity = source.new_zeros(())
            if step % 4 == 0:
                neutral_lut, _ = model(source, source)
                identity = (apply_lut(source, neutral_lut).float() - source).abs().mean()
            loss = reconstruction + 2 * ranking + 0.25 * identity
            if emphasize_edits:
                loss = loss + edit_emphasis_loss(output, expected, source)
        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scaler.step(optimizer)
        scaler.update()
        for key, value in (("loss", loss), ("reconstruction", reconstruction), ("ranking", ranking), ("identity", identity)):
            totals[key] += float(value.detach())
        if (step + 1) % 16 == 0:
            print(json.dumps({"epoch": epoch, "step": step + 1, "steps": len(loader), "loss": round(totals["loss"] / (step + 1), 5)}), flush=True)
    return {**{key: value / len(loader) for key, value in totals.items()}, "elapsedSeconds": time.perf_counter() - started}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("/kaggle/working/colorcheck-tst100k"))
    parser.add_argument("--scratch-dir", type=Path, default=Path("/kaggle/temp/colorcheck-tst100k"))
    parser.add_argument("--train-pairs", type=int, default=256)
    parser.add_argument("--validation-pairs", type=int, default=64)
    parser.add_argument("--test-pairs", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--size", type=int, default=128)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("This controlled Kaggle pilot requires a CUDA GPU")
    if args.batch_size < 2 or any(value < 2 for value in (args.train_pairs, args.validation_pairs, args.test_pairs)):
        raise ValueError("Each split and batch must contain at least two references")

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    torch.backends.cuda.matmul.allow_tf32 = True
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records = fetch_manifest()
    selected = select_triplets(
        records, (args.train_pairs, args.validation_pairs, args.test_pairs), args.seed
    )
    save_split_manifest(selected, args.output_dir / "splits.json", args.seed)
    staged = stage_images(selected, args.scratch_dir)
    print(json.dumps({"staged": staged, "pairs": {key: len(value) for key, value in selected.items()}}), flush=True)

    device = torch.device("cuda")
    loaders = {
        split: DataLoader(
            TripletDataset(selected[split], args.scratch_dir, args.size),
            batch_size=args.batch_size,
            shuffle=split == "train",
            num_workers=args.workers,
            pin_memory=True,
            drop_last=split == "train",
        )
        for split in SPLITS
    }
    model = ReferenceLutModel().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-4)
    scaler = torch.amp.GradScaler("cuda", enabled=not torch.cuda.is_bf16_supported())
    history = []
    best_score = float("inf")
    for epoch in range(1, args.epochs + 1):
        training = train_epoch(model, loaders["train"], optimizer, scaler, device, epoch)
        validation = evaluate(model, loaders["validation"], device, args.seed)
        # Checkpoint choice rewards correct-reference quality and penalizes
        # a model that ignores which reference was supplied.
        score = validation["model"]["deltaE2000"]["mean"] - validation["modelVsWrongReference"]["mean"]
        history.append({"epoch": epoch, "train": training, "validation": validation, "selectionScore": score})
        (args.output_dir / "history.json").write_text(json.dumps(history, indent=2))
        print(json.dumps({"epoch": epoch, "validationDeltaE2000": validation["model"]["deltaE2000"]["mean"], "correctReferenceGain": validation["modelVsWrongReference"]["mean"], "score": score}), flush=True)
        if score < best_score:
            best_score = score
            torch.save({"epoch": epoch, "state_dict": model.state_dict(), "seed": args.seed}, args.output_dir / "best.pt")

    checkpoint = torch.load(args.output_dir / "best.pt", map_location=device, weights_only=True)
    model.load_state_dict(checkpoint["state_dict"])
    test = evaluate(model, loaders["test"], device, args.seed + 1)
    gates = {
        "beatsIdentity": test["modelVsIdentity"]["ci95"][0] > 0,
        "beatsCurrentMatcher": test["modelVsStatistics"]["ci95"][0] > 0
        and test["modelVsStatistics"]["mean"] >= 0.5,
        "usesCorrectReference": test["modelVsWrongReference"]["ci95"][0] > 0
        and test["modelVsWrongReference"]["mean"] >= 0.25,
    }
    result = {
        "dataset": "ToneStyle/TST100K",
        "selectedCheckpointEpoch": checkpoint["epoch"],
        "parameters": sum(parameter.numel() for parameter in model.parameters()),
        "test": test,
        "gates": gates,
        "allGatesPass": all(gates.values()),
        "note": "Research pilot only. No model is promoted to the site by this command.",
    }
    (args.output_dir / "summary.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({"gates": gates, "test": {key: test[key]["mean"] for key in ("modelVsIdentity", "modelVsStatistics", "modelVsWrongReference")}}), flush=True)


if __name__ == "__main__":
    main()
