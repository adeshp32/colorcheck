"""Run the predeclared strong-edit experiment without opening final test data.

The v3 checkpoint is warm-started on its original training split. Validation
alone selects the v4 checkpoint and decides whether a later final audit is
allowed. This command never reads final-holdout.json or its images.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from tools.ml.reference_matcher.evaluation import metric_samples
from tools.ml.reference_matcher.model import ReferenceLutModel, apply_lut
from .data import TripletDataset, stage_images
from .prepare_v4 import mounted_file
from .train import evaluate, image_batch, train_epoch

EXPECTED_PREFLIGHT_SHA256 = "a1f9bdb468707e729703e4b8915283d0314b82b355ffb87e1d3cf94afa740b8a"
STRONG_EDIT_THRESHOLD = 0.08
SEED = 9103


@torch.inference_mode()
def strong_edit_delta_e(model: ReferenceLutModel, loader: DataLoader, device: torch.device) -> tuple[float, int]:
    """Score only predeclared large edits in the old validation split."""
    model.eval()
    errors = []
    for batch in loader:
        source, reference, expected = image_batch(batch, device)
        strong = (expected - source).abs().flatten(1).mean(1) >= STRONG_EDIT_THRESHOLD
        if not strong.any():
            continue
        lut, _ = model(source, reference)
        output = apply_lut(source, lut).float()
        errors.extend(metric_samples(output[strong], expected[strong])["deltaE2000"].cpu().tolist())
    return (float(np.mean(errors)) if errors else float("nan"), len(errors))


def validation_gates(candidate: dict, baseline: dict, strong_candidate: float, strong_baseline: float, count: int) -> dict:
    """Apply only the thresholds written before this GPU run."""
    return {
        "strongEditCoverage": count >= 20,
        "strongEditGain": count >= 20 and strong_baseline - strong_candidate >= 0.5,
        "overallColor": candidate["model"]["deltaE2000"]["mean"]
        <= baseline["model"]["deltaE2000"]["mean"] + 0.1,
        "structure": candidate["model"]["ssim"]["mean"]
        >= baseline["model"]["ssim"]["mean"] - 0.005,
        "clipping": candidate["model"]["clippingPercent"]["mean"]
        <= baseline["model"]["clippingPercent"]["mean"] + 1.0,
        "correctReference": candidate["modelVsWrongReference"]["mean"] > 0,
    }


def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("The v4 training experiment requires Kaggle CUDA")
    torch.set_num_threads(4)
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    torch.backends.cuda.matmul.allow_tf32 = True

    output = Path("/kaggle/working/colorcheck-tst100k-v4")
    scratch = Path("/kaggle/temp/colorcheck-tst100k-v4")
    output.mkdir(parents=True, exist_ok=True)
    preflight = json.loads(mounted_file("colorcheck-tst100k-v4-preflight", "preflight.json").read_text())
    if not preflight["ready"] or preflight["manifestSha256"] != EXPECTED_PREFLIGHT_SHA256:
        raise RuntimeError("Preflight failed or sealed final-holdout checksum changed")
    old = json.loads(mounted_file("colorcheck-tst100k-expanded-validation", "splits.json").read_text())
    selected = {name: old["splits"][name] for name in ("train", "validation")}
    if (len(selected["train"]), len(selected["validation"])) != (1024, 160):
        raise RuntimeError("The v3 training/validation split changed")
    print(json.dumps({"staged": stage_images(selected, scratch)}), flush=True)

    device = torch.device("cuda")
    loaders = {
        name: DataLoader(
            TripletDataset(rows, scratch, 128), batch_size=8,
            shuffle=name == "train", num_workers=2, pin_memory=True,
            drop_last=name == "train",
        )
        for name, rows in selected.items()
    }
    old_checkpoint = torch.load(
        mounted_file("colorcheck-tst100k-expanded-validation", "best.pt"),
        map_location=device, weights_only=True,
    )
    if old_checkpoint["epoch"] != 8:
        raise RuntimeError("Expected the selected v3 epoch-8 checkpoint")
    model = ReferenceLutModel().to(device)
    model.load_state_dict(old_checkpoint["state_dict"])
    baseline_model = ReferenceLutModel().to(device)
    baseline_model.load_state_dict(old_checkpoint["state_dict"])
    baseline_model.eval()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=1e-4)
    scaler = torch.amp.GradScaler("cuda", enabled=not torch.cuda.is_bf16_supported())

    history = []
    best_score = float("inf")
    for epoch in range(1, 5):
        training = train_epoch(model, loaders["train"], optimizer, scaler, device, epoch, emphasize_edits=True)
        validation = evaluate(model, loaders["validation"], device, SEED)
        score = validation["model"]["deltaE2000"]["mean"] - validation["modelVsWrongReference"]["mean"]
        history.append({"epoch": epoch, "train": training, "validation": validation, "selectionScore": score})
        (output / "history.json").write_text(json.dumps(history, indent=2))
        print(json.dumps({"epoch": epoch, "selectionScore": score}), flush=True)
        if score < best_score:
            best_score = score
            torch.save({"epoch": epoch, "state_dict": model.state_dict(), "warmStartEpoch": 8}, output / "best.pt")

    checkpoint = torch.load(output / "best.pt", map_location=device, weights_only=True)
    model.load_state_dict(checkpoint["state_dict"])
    candidate = evaluate(model, loaders["validation"], device, SEED)
    baseline = evaluate(baseline_model, loaders["validation"], device, SEED)
    strong_candidate, count = strong_edit_delta_e(model, loaders["validation"], device)
    strong_baseline, old_count = strong_edit_delta_e(baseline_model, loaders["validation"], device)
    if count != old_count or count != preflight["strongValidationTargets"]:
        raise RuntimeError("Strong-edit validation membership changed")
    gates = validation_gates(candidate, baseline, strong_candidate, strong_baseline, count)
    result = {
        "selectedEpoch": checkpoint["epoch"], "warmStartEpoch": 8,
        "preflightManifestSha256": EXPECTED_PREFLIGHT_SHA256,
        "strongEditCount": count, "strongEditDeltaE2000": {
            "v4": strong_candidate, "v3": strong_baseline,
        },
        "validation": {"v4": candidate, "v3": baseline},
        "gates": gates, "allGatesPass": all(gates.values()),
        "note": "Validation only. Final-holdout files and images are not read by this run.",
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({"gates": gates, "selectedEpoch": checkpoint["epoch"]}), flush=True)


if __name__ == "__main__":
    main()
