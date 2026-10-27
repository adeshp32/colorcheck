"""Fit browser-portable palette/tone rules from TST100K expert edits.

Only train and validation rows are opened. The final partition in the mounted
preflight is deliberately ignored. This is a pilot, not a release decision.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from .adaptive_rules_core import (
    BASELINE, FEATURE_NAMES, STRENGTHS, clipping, features, gain_interval, match,
)
from .data import DATASET_REVISION, TripletDataset, stage_images
from .prepare_selector import checksum
from .prepare_v4 import mounted_file

PREFLIGHT = "colorcheck-tst100k-final-decision-preflight"
EXPECTED_MANIFEST_SHA256 = "b7c4b0a0977c2cdf6d998351d9fcc4a95d5b18eb4070defa6b6ac5637c1fee08"
COUNTS = {"train": 192, "validation": 64}
REGULARIZATION = (1.0, 10.0, 100.0)


def gpu_training_label(source: np.ndarray, reference: np.ndarray,
                       expert: np.ndarray) -> np.ndarray:
    """Score the fixed strength grid in parallel; the expert is never a model input."""
    device = torch.device("cuda")
    source_t, reference_t, expert_t = (
        torch.as_tensor(image, dtype=torch.float32, device=device)
        for image in (source, reference, expert)
    )
    values = torch.tensor(STRENGTHS, device=device)
    palette, tone = torch.meshgrid(values, values, indexing="ij")
    strengths = torch.stack((palette.flatten(), tone.flatten()), dim=1)
    source_mean = source_t.mean((1, 2))[:, None, None]
    reference_mean = reference_t.mean((1, 2))[:, None, None]
    gain = (reference_t.std((1, 2), unbiased=False)
            / source_t.std((1, 2), unbiased=False).clamp_min(0.015)).clamp(0.65, 1.5)
    proposed = (source_t[None]
                + (reference_mean - source_mean)[None] * strengths[:, 0, None, None, None]
                + ((source_t - source_mean) * (gain - 1)[:, None, None])[None]
                * strengths[:, 1, None, None, None]).clamp(0, 1)
    error = (proposed - expert_t).abs().mean((1, 2, 3))
    clipped = ((proposed <= 1 / 255) | (proposed >= 254 / 255)).any(dim=1).float().mean((1, 2))
    original = ((source_t <= 1 / 255) | (source_t >= 254 / 255)).any(dim=0).float().mean()
    baseline = torch.as_tensor(BASELINE, device=device)
    score = error + 0.03 * (clipped - original).clamp_min(0) \
        + 0.003 * (strengths - baseline).abs().sum(dim=1)
    return strengths[score.argmin()].cpu().numpy().astype(np.float64)


def rows_as_arrays(rows: list[dict], root: Path) -> list[tuple[np.ndarray, ...]]:
    """Small 64-pixel aligned images; never stage the full dataset locally."""
    dataset = TripletDataset(rows, root, 64)
    return [tuple(dataset[index][name].numpy().astype(np.float64)
                  for name in ("source", "reference", "expected"))
            for index in range(len(dataset))]


def predicted_strengths(feature: np.ndarray, scaler: StandardScaler, model: Ridge) -> np.ndarray:
    return np.clip(model.predict(scaler.transform(feature)), 0, 1)


def score_validation(
    images: list[tuple[np.ndarray, ...]],
    scaler: StandardScaler,
    model: Ridge,
) -> dict:
    """Use reference-free expert metrics only for evaluation, not prediction."""
    errors = {name: [] for name in ("adaptive", "baseline", "identity", "wrongReference")}
    clipping_rates = {name: [] for name in ("adaptive", "baseline")}
    predictions = []
    for index, (source, reference, expert) in enumerate(images):
        policy = predicted_strengths(features(source, reference)[None], scaler, model)[0]
        wrong_reference = images[(index + 1) % len(images)][1]
        wrong_policy = predicted_strengths(features(source, wrong_reference)[None], scaler, model)[0]
        candidates = {
            "adaptive": match(source, reference, policy),
            "baseline": match(source, reference, BASELINE),
            "identity": source,
            "wrongReference": match(source, wrong_reference, wrong_policy),
        }
        for name, result in candidates.items():
            errors[name].append(float(np.mean(np.abs(result - expert))))
        for name in clipping_rates:
            clipping_rates[name].append(clipping(candidates[name]))
        predictions.append(policy.tolist())
    gain = np.array(errors["baseline"]) - np.array(errors["adaptive"])
    summary = {
        "meanRgbMae": {name: float(np.mean(values)) for name, values in errors.items()},
        "meanClipping": {name: float(np.mean(values)) for name, values in clipping_rates.items()},
        "meanGainVsFixedMatcher": float(gain.mean()),
        "gainVsFixedCi95": gain_interval(gain),
        "fractionWithin002OfFixed": float(np.mean(gain >= -0.02)),
        "worstLossVsFixed": float(max(0, -gain.min())),
        "correctReferenceAdvantage": float(np.mean(errors["wrongReference"]) - np.mean(errors["adaptive"])),
        "meanStrengths": np.mean(predictions, axis=0).tolist(),
        "sampleCount": len(images),
    }
    summary["pilotGatesPass"] = bool(
        summary["meanGainVsFixedMatcher"] >= 0.002
        and summary["gainVsFixedCi95"][0] > 0
        and summary["fractionWithin002OfFixed"] >= 0.9
        and summary["worstLossVsFixed"] <= 0.08
        and summary["correctReferenceAdvantage"] > 0
        and summary["meanClipping"]["adaptive"] <= summary["meanClipping"]["baseline"] + 0.01
    )
    return summary


def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("This GPU-assisted pilot requires CUDA")
    print({"gpu": torch.cuda.get_device_name(0)}, flush=True)
    output = Path("/kaggle/working/colorcheck-adaptive-rules")
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(mounted_file(PREFLIGHT, "splits.json").read_text())
    if manifest["datasetRevision"] != DATASET_REVISION or checksum(manifest) != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("Pinned training/validation manifest changed")
    selected = {name: manifest["splits"][name][:count] for name, count in COUNTS.items()}
    scratch = Path("/kaggle/working/colorcheck-adaptive-images")
    print(json.dumps({"staged": stage_images(selected, scratch)}), flush=True)
    train = rows_as_arrays(selected["train"], scratch)
    validation = rows_as_arrays(selected["validation"], scratch)
    train_features = np.stack([features(source, reference) for source, reference, _ in train])
    labels = np.stack([gpu_training_label(*images) for images in train])
    scaler = StandardScaler().fit(train_features)
    attempts = []
    for alpha in REGULARIZATION:
        model = Ridge(alpha=alpha).fit(scaler.transform(train_features), labels)
        attempts.append((score_validation(validation, scaler, model), alpha, model))
    # Choose by validation mean error only; the final partition remains unopened.
    summary, alpha, model = min(attempts, key=lambda row: row[0]["meanRgbMae"]["adaptive"])
    summary.update({"regularization": alpha, "trainingScenes": len(train),
                    "validationScenes": len(validation), "datasetRevision": DATASET_REVISION,
                    "manifestSha256": EXPECTED_MANIFEST_SHA256,
                    "note": "Pilot validation only; no final scenes opened or site deployment authorized."})
    package = {
        "featureNames": FEATURE_NAMES,
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "coefficients": model.coef_.tolist(),
        "intercepts": model.intercept_.tolist(),
        "researchOnly": True,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    (output / "adaptive-rules.json").write_text(json.dumps(package, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
