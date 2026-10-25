"""One-time audit of a frozen selector on its sealed final photographs.

No fitting, threshold search, or checkpoint choice occurs here. A failed final
gate is a research failure, not a reason to tune against this partition.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw
from torch.utils.data import DataLoader

from tools.ml.reference_matcher.evaluation import metric_samples, statistics_match
from tools.ml.reference_matcher.model import ReferenceLutModel, apply_lut
from .data import TripletDataset, scene_id, stage_images
from .prepare_selector import checksum
from .prepare_v4 import mounted_file
from .review import full_image, to_image
from .selector import FEATURE_NAMES
from .train import mean_interval
from .train_selector import EXPECTED_FINAL_SHA256, EXPECTED_SPLIT_SHA256, extract_split, validation_metrics

FROZEN_THRESHOLD = 0.60


def frozen_probability(features: np.ndarray, package: dict) -> np.ndarray:
    """Use explicit arithmetic that can be reproduced in browser JavaScript."""
    if tuple(package["featureNames"]) != FEATURE_NAMES:
        raise RuntimeError("Selector feature schema changed")
    mean = np.asarray(package["mean"], dtype=np.float64)
    scale = np.asarray(package["scale"], dtype=np.float64)
    weights = np.asarray(package["coefficients"], dtype=np.float64)
    if features.shape[1] != len(weights) or np.any(scale <= 0):
        raise RuntimeError("Invalid frozen selector dimensions or scale")
    score = ((features.astype(np.float64) - mean) / scale) @ weights + float(package["intercept"])
    return 1 / (1 + np.exp(-np.clip(score, -80, 80)))


@torch.inference_mode()
def extra_metrics(model: ReferenceLutModel, rows: list[dict], scratch: Path,
                  device: torch.device) -> dict[str, np.ndarray]:
    """Measure identity and edge fidelity, neither used to choose the model."""
    loader = DataLoader(TripletDataset(rows, scratch, 128), batch_size=8,
                        num_workers=2, pin_memory=device.type == "cuda")
    columns = {name: [] for name in (
        "identityError", "identitySsim", "identityEdge", "lutEdge", "statsEdge",
    )}
    model.eval()
    for batch in loader:
        source, reference, expected = (
            batch[key].to(device, non_blocking=True)
            for key in ("source", "reference", "expected")
        )
        lut = apply_lut(source, model(source, reference)[0]).float()
        stats = statistics_match(source, reference)
        identity_metrics = metric_samples(source, expected)
        lut_metrics = metric_samples(lut, expected)
        stats_metrics = metric_samples(stats, expected)
        for name, value in (
            ("identityError", identity_metrics["deltaE2000"]),
            ("identitySsim", identity_metrics["ssim"]),
            ("identityEdge", identity_metrics["edgeMae"]),
            ("lutEdge", lut_metrics["edgeMae"]),
            ("statsEdge", stats_metrics["edgeMae"]),
        ):
            columns[name].append(value.cpu().numpy())
    return {name: np.concatenate(values) for name, values in columns.items()}


def review_groups(rows: list[dict], gains: np.ndarray) -> dict[str, list[int]]:
    """Expose worst, fixed-random, and best cases without choosing a setting."""
    ranked = np.argsort(gains)
    worst = ranked[:4].tolist()
    best = ranked[-4:].tolist()
    remaining = [index for index in range(len(rows)) if index not in set(worst + best)]
    typical = random.Random(2027).sample(remaining, 4)
    return {"worst": worst, "random": typical, "best": best}


@torch.inference_mode()
def render_sheet(model: ReferenceLutModel, rows: list[dict], root: Path,
                 selected: np.ndarray, indices: list[int], output: Path) -> None:
    """Compare source, reference, both candidates, chosen result, and expert."""
    names = ("Source", "Reference", "Current", "V3 LUT", "Selector", "Expert")
    tile, label = 256, 38
    sheet = Image.new("RGB", (tile * len(names), (tile + label) * len(indices)), "#eeeeee")
    draw = ImageDraw.Draw(sheet)
    model = model.cpu().eval()
    for row_number, index in enumerate(indices):
        row = rows[index]
        source, reference, expert = (full_image(root / row[key]) for key in ("content", "reference", "gt"))
        small = TripletDataset([row], root, 128)[0]
        lut = model(small["source"].unsqueeze(0), small["reference"].unsqueeze(0))[0]
        trained = apply_lut(source, lut).float()
        current = statistics_match(source, reference)
        chosen = trained if selected[index] else current
        for column, (name, tensor) in enumerate(zip(names, (source, reference, current, trained, chosen, expert))):
            left, top = column * tile, row_number * (tile + label)
            draw.text((left + 8, top + 8), f"{name} | {scene_id(row['content'])}", fill="#111111")
            sheet.paste(to_image(tensor), (left, top + label))
    sheet.save(output, quality=86, optimize=True)


def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("Enable Kaggle GPU for the one-time final audit")
    torch.set_num_threads(4)
    output = Path("/kaggle/working/colorcheck-tst100k-selector-final")
    scratch = Path("/kaggle/temp/colorcheck-tst100k-selector-final")
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(mounted_file("colorcheck-tst100k-selector-preflight", "selector-splits.json").read_text())
    package = json.loads(mounted_file("colorcheck-tst100k-selector-validation", "selector-model.json").read_text())
    validation = json.loads(mounted_file("colorcheck-tst100k-selector-validation", "summary.json").read_text())
    if (not validation["allGatesPass"] or validation["selectedThreshold"] != FROZEN_THRESHOLD
            or package["threshold"] != FROZEN_THRESHOLD
            or checksum(manifest) != EXPECTED_SPLIT_SHA256
            or package["splitSha256"] != EXPECTED_SPLIT_SHA256
            or checksum({"rows": manifest["splits"]["final"]}) != EXPECTED_FINAL_SHA256
            or validation["sealedFinalSha256"] != EXPECTED_FINAL_SHA256):
        raise RuntimeError("Frozen validation decision or sealed final manifest changed")
    rows = manifest["splits"]["final"]
    if len(rows) != 256:
        raise RuntimeError("Final holdout must contain exactly 256 targets")
    print(json.dumps({"gpu": torch.cuda.get_device_name(0),
                      "stagedFinal": stage_images({"final": rows}, scratch)}), flush=True)
    device = torch.device("cuda")
    checkpoint = torch.load(mounted_file("colorcheck-tst100k-expanded-validation", "best.pt"),
                            map_location=device, weights_only=True)
    if checkpoint["epoch"] != 8:
        raise RuntimeError("Expected the frozen v3 epoch-8 checkpoint")
    model = ReferenceLutModel().to(device).eval()
    model.load_state_dict(checkpoint["state_dict"])
    measured = extract_split(model, rows, scratch, device)
    supplement = extra_metrics(model, rows, scratch, device)
    selected = frozen_probability(measured["features"], package) >= FROZEN_THRESHOLD
    wrong_selected = frozen_probability(measured["wrongFeatures"], package) >= FROZEN_THRESHOLD
    result = validation_metrics(
        measured["lutError"], measured["statsError"],
        measured["wrongLutError"], measured["wrongStatsError"],
        measured["lutSsim"], measured["statsSsim"],
        measured["lutClipping"], measured["statsClipping"],
        selected, wrong_selected,
    )
    gain = measured["statsError"] - np.where(selected, measured["lutError"], measured["statsError"])
    chosen_edge = np.where(selected, supplement["lutEdge"], supplement["statsEdge"])
    result.update({
        "testScenes": len(rows), "threshold": FROZEN_THRESHOLD,
        "finalSha256": EXPECTED_FINAL_SHA256,
        "identityMeanDeltaE": float(np.mean(supplement["identityError"])),
        "gainVsUnchanged": mean_interval(
            (supplement["identityError"] - np.where(
                selected, measured["lutError"], measured["statsError"])).tolist(), 7203),
        "correctVsWrongReference": mean_interval(
            (np.where(wrong_selected, measured["wrongLutError"], measured["wrongStatsError"])
             - np.where(selected, measured["lutError"], measured["statsError"])).tolist(), 7204),
        "v3MeanDeltaE": float(np.mean(measured["lutError"])),
        "v3GainVsStatistics": mean_interval(
            (measured["statsError"] - measured["lutError"]).tolist(), 7202),
        "meanEdgeMae": float(np.mean(chosen_edge)),
        "statisticsMeanEdgeMae": float(np.mean(supplement["statsEdge"])),
        "v3MeanEdgeMae": float(np.mean(supplement["lutEdge"])),
        "identityMeanEdgeMae": float(np.mean(supplement["identityEdge"])),
        "identityMeanSsim": float(np.mean(supplement["identitySsim"])),
        "perPhotoBetterCount": int(np.sum(gain > 0)),
        "perPhotoWorseCount": int(np.sum(gain < 0)),
        "perPhotoTieCount": int(np.sum(gain == 0)),
        "note": "One-time final audit; no fitting or threshold selection. Not a deployment decision.",
    })
    groups = review_groups(rows, gain)
    result["reviewGroups"] = {
        name: [{"scene": scene_id(rows[index]["content"]), "gain": float(gain[index]),
                "selectedLut": bool(selected[index])} for index in indices]
        for name, indices in groups.items()
    }
    (output / "final-summary.json").write_text(json.dumps(result, indent=2))
    model.cpu()
    for name, indices in groups.items():
        render_sheet(model, rows, scratch, selected, indices, output / f"{name}.jpg")
    print(json.dumps({"allGatesPass": result["allGatesPass"],
                      "gain": result["deltaEGainVsStatistics"],
                      "nonregressionFraction": result["nonregressionFraction"]}), flush=True)


if __name__ == "__main__":
    main()
