"""Train a risk-aware routing rule without opening the final partition.

The image-producing models are frozen. This learns only when to trust v3 over
the current statistics matcher, using features available in the browser.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

from tools.ml.reference_matcher.model import ReferenceLutModel
from .data import DATASET_REVISION, stage_images
from .final_selector import frozen_probability
from .prepare_selector import checksum
from .prepare_v4 import mounted_file
from .selector import FEATURE_NAMES
from .train import mean_interval
from .train_selector import extract_split, validation_metrics

QUANTILES = (0.10, 0.25, 0.40)
ROUTE_THRESHOLD = 0.25
SEED = 8413
MIN_STRONG = 40
PREFLIGHT_KERNEL = "colorcheck-tst100k-final-decision-preflight"


def route(features: np.ndarray, package: dict) -> np.ndarray:
    """Apply the exported linear rule with browser-reproducible arithmetic."""
    if tuple(package["featureNames"]) != FEATURE_NAMES:
        raise RuntimeError("Feature schema changed")
    mean = np.asarray(package["mean"], dtype=np.float64)
    scale = np.asarray(package["scale"], dtype=np.float64)
    coefficients = np.asarray(package["coefficients"], dtype=np.float64)
    if features.ndim != 2 or features.shape[1] != len(FEATURE_NAMES) or np.any(scale <= 0):
        raise RuntimeError("Invalid feature matrix or scaler")
    prediction = ((features.astype(np.float64) - mean) / scale) @ coefficients
    prediction += float(package["intercept"])
    return prediction > ROUTE_THRESHOLD


def measured_gates(data: dict[str, np.ndarray], selected: np.ndarray,
                   wrong_selected: np.ndarray, frozen_selected: np.ndarray) -> dict:
    """Apply the thresholds committed before this experiment was run."""
    result = validation_metrics(
        data["lutError"], data["statsError"], data["wrongLutError"],
        data["wrongStatsError"], data["lutSsim"], data["statsSsim"],
        data["lutClipping"], data["statsClipping"], selected, wrong_selected,
    )
    chosen = np.where(selected, data["lutError"], data["statsError"])
    wrong = np.where(wrong_selected, data["wrongLutError"], data["wrongStatsError"])
    frozen = np.where(frozen_selected, data["lutError"], data["statsError"])
    strong = data["strongEdit"].astype(bool)
    result["gainVsFrozenSelector"] = mean_interval((frozen - chosen).tolist(), SEED)
    result["strongEditCount"] = int(strong.sum())
    result["strongEditGainVsFrozenSelector"] = (
        mean_interval((frozen[strong] - chosen[strong]).tolist(), SEED)
        if strong.any() else None
    )
    result["worstLossVsStatistics"] = float(np.max(chosen - data["statsError"]))
    result["correctReferenceInterval"] = mean_interval((wrong - chosen).tolist(), SEED)
    gain = result["gainVsFrozenSelector"]
    strong_gain = result["strongEditGainVsFrozenSelector"]
    result["finalGates"] = {
        "colorVsStatistics": (result["deltaEGainVsStatistics"]["mean"] >= 0.5
                              and result["deltaEGainVsStatistics"]["ci95"][0] > 0),
        "colorVsFrozenSelector": gain["mean"] >= 0.3 and gain["ci95"][0] > 0,
        "strongEdits": (result["strongEditCount"] >= MIN_STRONG and strong_gain is not None
                        and strong_gain["mean"] >= 0.5 and strong_gain["ci95"][0] > 0),
        "nonregression": result["nonregressionFraction"] >= 0.95,
        "worstCase": result["worstLossVsStatistics"] <= 5.0,
        "correctReference": result["correctReferenceInterval"]["ci95"][0] > 0,
        "structure": result["meanSsim"] >= result["statisticsMeanSsim"] - 0.005,
        "clipping": result["meanClippingPercent"] <= result["statisticsMeanClippingPercent"] + 1.0,
        "learnedUse": result["lutSelectionFraction"] >= 0.20,
    }
    result["allFinalGatesPass"] = all(result["finalGates"].values())
    return result


def main() -> None:
    from sklearn.linear_model import QuantileRegressor
    from sklearn.preprocessing import StandardScaler

    if not torch.cuda.is_available():
        raise RuntimeError("GPU required to generate the frozen candidate outputs")
    torch.set_num_threads(4)
    output = Path("/kaggle/working/colorcheck-tst100k-final-decision-training")
    scratch = Path("/kaggle/temp/colorcheck-tst100k-final-decision-training")
    output.mkdir(parents=True, exist_ok=True)
    preflight = json.loads(mounted_file(PREFLIGHT_KERNEL, "preflight.json").read_text())
    splits = json.loads(mounted_file(PREFLIGHT_KERNEL, "splits.json").read_text())
    if (not preflight["ready"] or splits["datasetRevision"] != DATASET_REVISION
            or checksum(splits) != preflight["manifestSha256"]
            or checksum({"rows": splits["splits"]["final"]}) != preflight["finalSha256"]):
        raise RuntimeError("Preflight manifest or final seal changed")
    selected = {name: splits["splits"][name] for name in ("train", "validation")}
    if tuple(len(selected[name]) for name in selected) != (1024, 256):
        raise RuntimeError("Training or validation target count changed")
    print(json.dumps({"staged": stage_images(selected, scratch)}), flush=True)
    device = torch.device("cuda")
    print(json.dumps({"gpu": torch.cuda.get_device_name(0)}), flush=True)
    checkpoint = torch.load(mounted_file("colorcheck-tst100k-expanded-validation", "best.pt"),
                            map_location=device, weights_only=True)
    if checkpoint["epoch"] != 8:
        raise RuntimeError("Frozen v3 checkpoint changed")
    model = ReferenceLutModel().to(device).eval()
    model.load_state_dict(checkpoint["state_dict"])
    train = extract_split(model, selected["train"], scratch, device)
    validation = extract_split(model, selected["validation"], scratch, device)
    frozen = json.loads(mounted_file("colorcheck-tst100k-selector-validation", "selector-model.json").read_text())
    if frozen["threshold"] != 0.60:
        raise RuntimeError("Frozen selector threshold changed")
    frozen_selected = frozen_probability(validation["features"], frozen) >= 0.60
    scaler = StandardScaler().fit(train["features"])
    training_features = scaler.transform(train["features"])
    validation_features = scaler.transform(validation["features"])
    wrong_features = scaler.transform(validation["wrongFeatures"])
    advantage = train["statsError"] - train["lutError"]
    trials = []
    for quantile in QUANTILES:
        regressor = QuantileRegressor(quantile=quantile, alpha=0.001, solver="highs")
        regressor.fit(training_features, advantage)
        package = {
            "featureNames": FEATURE_NAMES, "mean": scaler.mean_.tolist(),
            "scale": scaler.scale_.tolist(), "coefficients": regressor.coef_.tolist(),
            "intercept": float(regressor.intercept_), "quantile": quantile,
            "threshold": ROUTE_THRESHOLD, "splitSha256": preflight["manifestSha256"],
            "sealedFinalSha256": preflight["finalSha256"], "researchOnly": True,
        }
        selected_lut = regressor.predict(validation_features) > ROUTE_THRESHOLD
        wrong_selected = regressor.predict(wrong_features) > ROUTE_THRESHOLD
        metrics = measured_gates(validation, selected_lut, wrong_selected, frozen_selected)
        trials.append((quantile, package, metrics))
        print(json.dumps({"quantile": quantile, "gates": metrics["finalGates"]}), flush=True)
    passing = [trial for trial in trials if trial[2]["allFinalGatesPass"]]
    winner = max(passing, key=lambda item: (item[2]["deltaEGainVsStatistics"]["mean"], -item[0])) if passing else None
    summary = {
        "preflightSha256": preflight["manifestSha256"],
        "sealedFinalSha256": preflight["finalSha256"],
        "trainTargets": len(selected["train"]), "validationTargets": len(selected["validation"]),
        "trials": [{"quantile": q, "metrics": metrics} for q, _, metrics in trials],
        "selectedQuantile": winner[0] if winner else None,
        "allGatesPass": winner is not None,
        "note": "Validation only; final images were not opened or staged.",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    if winner:
        (output / "selector-model.json").write_text(json.dumps(winner[1], indent=2))
    print(json.dumps({"allGatesPass": summary["allGatesPass"],
                      "selectedQuantile": summary["selectedQuantile"]}), flush=True)


if __name__ == "__main__":
    main()
