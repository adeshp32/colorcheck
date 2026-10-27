"""Train a small quality selector on fresh scenes without opening final data.

Frozen v3 and the existing statistics matcher make candidate images. The
expert edit labels which candidate is closer, but is never a model feature.
Only validation selects regularization and a conservative routing threshold.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from tools.ml.reference_matcher.evaluation import metric_samples, statistics_match
from tools.ml.reference_matcher.model import ReferenceLutModel, apply_lut
from .data import TripletDataset, stage_images
from .prepare_selector import checksum
from .prepare_v4 import mounted_file
from .selector import FEATURE_NAMES, selector_features
from .train import mean_interval

EXPECTED_SPLIT_SHA256 = "5cf65a621ca1c33475a1f3579b22caa4f0e3f33ec563df176202950e7272afa8"
EXPECTED_FINAL_SHA256 = "a0e8940a69c494bef7648949364d6fefe0a7187ef0ab575d41a0a54d280fe399"
SEED = 7201
TIE_BAND = 0.25
REGULARIZATION = (0.1, 1.0, 10.0)
THRESHOLDS = tuple(round(value / 100, 2) for value in range(50, 96, 5))


def labels_from_errors(lut_error: np.ndarray, statistics_error: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Training labels use expert error; ties are omitted, not forced."""
    advantage = statistics_error - lut_error
    return (advantage > TIE_BAND).astype(np.int64), np.abs(advantage) > TIE_BAND


def validation_metrics(
    lut_error: np.ndarray, stats_error: np.ndarray,
    wrong_lut_error: np.ndarray, wrong_stats_error: np.ndarray,
    lut_ssim: np.ndarray, stats_ssim: np.ndarray,
    lut_clipping: np.ndarray, stats_clipping: np.ndarray,
    select_lut: np.ndarray, wrong_select_lut: np.ndarray,
) -> dict:
    """Evaluate one fixed threshold with photo-level paired comparisons."""
    chosen_error = np.where(select_lut, lut_error, stats_error)
    wrong_error = np.where(wrong_select_lut, wrong_lut_error, wrong_stats_error)
    gain = stats_error - chosen_error
    chosen_ssim = np.where(select_lut, lut_ssim, stats_ssim)
    chosen_clipping = np.where(select_lut, lut_clipping, stats_clipping)
    interval = mean_interval(gain.tolist(), SEED)
    result = {
        "deltaEGainVsStatistics": interval,
        "nonregressionFraction": float(np.mean(gain >= -0.5)),
        "largeLossFraction": float(np.mean(gain < -2.0)),
        "correctReferenceGain": float(np.mean(wrong_error - chosen_error)),
        "lutSelectionFraction": float(np.mean(select_lut)),
        "meanSsim": float(np.mean(chosen_ssim)),
        "statisticsMeanSsim": float(np.mean(stats_ssim)),
        "meanClippingPercent": float(np.mean(chosen_clipping)),
        "statisticsMeanClippingPercent": float(np.mean(stats_clipping)),
        "meanDeltaE": float(np.mean(chosen_error)),
        "statisticsMeanDeltaE": float(np.mean(stats_error)),
    }
    result["gates"] = {
        "nonregression": result["nonregressionFraction"] >= 0.9,
        "practicalColorGain": interval["mean"] >= 0.5 and interval["ci95"][0] > 0,
        "correctReference": result["correctReferenceGain"] > 0,
        "selectsLutOftenEnough": result["lutSelectionFraction"] >= 0.2,
        "structure": result["meanSsim"] >= result["statisticsMeanSsim"] - 0.005,
        "clipping": result["meanClippingPercent"] <= result["statisticsMeanClippingPercent"] + 1.0,
    }
    result["allGatesPass"] = all(result["gates"].values())
    return result


@torch.inference_mode()
def extract_split(model: ReferenceLutModel, rows: list[dict], scratch: Path,
                  device: torch.device) -> dict[str, np.ndarray]:
    """Create features and evaluation columns without saving any photographs."""
    loader = DataLoader(TripletDataset(rows, scratch, 128), batch_size=8,
                        num_workers=2, pin_memory=device.type == "cuda")
    columns: dict[str, list[np.ndarray]] = {name: [] for name in (
        "features", "wrongFeatures", "lutError", "statsError", "wrongLutError",
        "wrongStatsError", "lutSsim", "statsSsim", "lutClipping", "statsClipping",
        "strongEdit",
    )}
    model.eval()
    for batch in loader:
        source, reference, expected = (
            batch[key].to(device, non_blocking=True)
            for key in ("source", "reference", "expected")
        )
        if len(source) < 2:
            raise RuntimeError("Wrong-reference control needs batches of at least two")
        wrong_reference = reference.roll(1, 0)
        lut = apply_lut(source, model(source, reference)[0]).float()
        wrong_lut = apply_lut(source, model(source, wrong_reference)[0]).float()
        stats = statistics_match(source, reference)
        wrong_stats = statistics_match(source, wrong_reference)
        lut_metrics = metric_samples(lut, expected)
        stats_metrics = metric_samples(stats, expected)
        wrong_lut_metrics = metric_samples(wrong_lut, expected)
        wrong_stats_metrics = metric_samples(wrong_stats, expected)
        for name, value in (
            ("features", selector_features(source, reference, lut, stats)),
            ("wrongFeatures", selector_features(source, wrong_reference, wrong_lut, wrong_stats)),
            ("lutError", lut_metrics["deltaE2000"]),
            ("statsError", stats_metrics["deltaE2000"]),
            ("wrongLutError", wrong_lut_metrics["deltaE2000"]),
            ("wrongStatsError", wrong_stats_metrics["deltaE2000"]),
            ("lutSsim", lut_metrics["ssim"]),
            ("statsSsim", stats_metrics["ssim"]),
            ("lutClipping", lut_metrics["clippingPercent"]),
            ("statsClipping", stats_metrics["clippingPercent"]),
            ("strongEdit", (expected - source).abs().mean(dim=(1, 2, 3)) >= 0.08),
        ):
            columns[name].append(value.cpu().numpy())
    return {name: np.concatenate(values) for name, values in columns.items()}


def main() -> None:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import log_loss
    from sklearn.preprocessing import StandardScaler

    if not torch.cuda.is_available():
        raise RuntimeError("Enable Kaggle GPU for candidate generation")
    torch.set_num_threads(4)
    output = Path("/kaggle/working/colorcheck-tst100k-selector-training")
    scratch = Path("/kaggle/temp/colorcheck-tst100k-selector-training")
    output.mkdir(parents=True, exist_ok=True)
    preflight = json.loads(mounted_file("colorcheck-tst100k-selector-preflight", "preflight.json").read_text())
    splits = json.loads(mounted_file("colorcheck-tst100k-selector-preflight", "selector-splits.json").read_text())
    if (not preflight["ready"] or checksum(splits) != EXPECTED_SPLIT_SHA256
            or preflight["finalSha256"] != EXPECTED_FINAL_SHA256
            or checksum({"rows": splits["splits"]["final"]}) != EXPECTED_FINAL_SHA256):
        raise RuntimeError("Selector split preflight or sealed-final checksum changed")
    selected = {name: splits["splits"][name] for name in ("train", "validation")}
    if tuple(len(selected[name]) for name in selected) != (1024, 256):
        raise RuntimeError("Selector training and validation sizes changed")
    print(json.dumps({"staged": stage_images(selected, scratch)}), flush=True)

    device = torch.device("cuda")
    print(json.dumps({"gpu": torch.cuda.get_device_name(0)}), flush=True)
    checkpoint = torch.load(
        mounted_file("colorcheck-tst100k-expanded-validation", "best.pt"),
        map_location=device, weights_only=True,
    )
    if checkpoint["epoch"] != 8:
        raise RuntimeError("Expected the frozen v3 epoch-8 checkpoint")
    matcher = ReferenceLutModel().to(device).eval()
    matcher.load_state_dict(checkpoint["state_dict"])
    train = extract_split(matcher, selected["train"], scratch, device)
    validation = extract_split(matcher, selected["validation"], scratch, device)
    train_labels, train_keep = labels_from_errors(train["lutError"], train["statsError"])
    validation_labels, validation_keep = labels_from_errors(validation["lutError"], validation["statsError"])
    if len(set(train_labels[train_keep])) != 2 or len(set(validation_labels[validation_keep])) != 2:
        raise RuntimeError("Both selector classes must appear in training and validation")

    scaler = StandardScaler().fit(train["features"][train_keep])
    training_features = scaler.transform(train["features"][train_keep])
    validation_features = scaler.transform(validation["features"])
    candidates = []
    for strength in REGULARIZATION:
        candidate = LogisticRegression(C=strength, max_iter=1000, random_state=SEED)
        candidate.fit(training_features, train_labels[train_keep])
        probability = candidate.predict_proba(validation_features)[:, 1]
        score = log_loss(validation_labels[validation_keep], probability[validation_keep], labels=[0, 1])
        candidates.append((float(score), strength, candidate))
    loss, strength, selector = min(candidates, key=lambda row: (row[0], row[1]))
    correct_probability = selector.predict_proba(validation_features)[:, 1]
    wrong_probability = selector.predict_proba(scaler.transform(validation["wrongFeatures"]))[:, 1]
    reviewed = []
    for threshold in THRESHOLDS:
        measured = validation_metrics(
            validation["lutError"], validation["statsError"],
            validation["wrongLutError"], validation["wrongStatsError"],
            validation["lutSsim"], validation["statsSsim"],
            validation["lutClipping"], validation["statsClipping"],
            correct_probability >= threshold, wrong_probability >= threshold,
        )
        reviewed.append({"threshold": threshold, **measured})
    passing = [row for row in reviewed if row["allGatesPass"]]
    selected_threshold = max(
        passing, key=lambda row: (row["deltaEGainVsStatistics"]["mean"], row["threshold"])
    ) if passing else None
    result = {
        "dataset": "ToneStyle/TST100K", "splitSha256": EXPECTED_SPLIT_SHA256,
        "sealedFinalSha256": EXPECTED_FINAL_SHA256,
        "trainTargets": len(selected["train"]), "validationTargets": len(selected["validation"]),
        "trainingLabelsUsed": int(train_keep.sum()), "validationLabelsUsed": int(validation_keep.sum()),
        "chosenC": strength, "validationLogLoss": loss,
        "thresholds": reviewed,
        "selectedThreshold": selected_threshold["threshold"] if selected_threshold else None,
        "allGatesPass": selected_threshold is not None,
        "note": "Validation only; final-holdout photographs were not fetched or evaluated.",
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2))
    (output / "selector-model.json").write_text(json.dumps({
        "featureNames": FEATURE_NAMES, "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(), "coefficients": selector.coef_[0].tolist(),
        "intercept": float(selector.intercept_[0]),
        "threshold": result["selectedThreshold"], "chosenC": strength,
        "splitSha256": EXPECTED_SPLIT_SHA256,
        "researchOnly": True,
    }, indent=2))
    print(json.dumps({"allGatesPass": result["allGatesPass"],
                      "selectedThreshold": result["selectedThreshold"],
                      "chosenC": strength}), flush=True)


if __name__ == "__main__":
    main()
