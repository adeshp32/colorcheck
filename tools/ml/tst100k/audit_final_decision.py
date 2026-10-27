"""Audit one frozen routing rule on sealed scenes, with no fitting or tuning."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

from tools.ml.reference_matcher.model import ReferenceLutModel
from .data import DATASET_REVISION, scene_id, stage_images
from .final_selector import extra_metrics, frozen_probability, render_sheet, review_groups
from .prepare_selector import checksum
from .prepare_v4 import mounted_file
from .train import mean_interval
from .train_final_decision import PREFLIGHT_KERNEL, measured_gates, route
from .train_selector import extract_split

EXPECTED_MANIFEST_SHA256 = "b7c4b0a0977c2cdf6d998351d9fcc4a95d5b18eb4070defa6b6ac5637c1fee08"
EXPECTED_FINAL_SHA256 = "d2793beaa619e406424d231190f7d4eafea1f24f64cf4c63b72ec7cb564269c3"
VALIDATION_KERNEL = "colorcheck-tst100k-final-decision-training"


def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("Enable Kaggle GPU for the one-time final audit")
    torch.set_num_threads(4)
    output = Path("/kaggle/working/colorcheck-tst100k-final-decision-audit")
    scratch = Path("/kaggle/temp/colorcheck-tst100k-final-decision-audit")
    output.mkdir(parents=True, exist_ok=True)
    preflight = json.loads(mounted_file(PREFLIGHT_KERNEL, "preflight.json").read_text())
    manifest = json.loads(mounted_file(PREFLIGHT_KERNEL, "splits.json").read_text())
    validation = json.loads(mounted_file(VALIDATION_KERNEL, "summary.json").read_text())
    package = json.loads(mounted_file(VALIDATION_KERNEL, "selector-model.json").read_text())
    if (manifest["datasetRevision"] != DATASET_REVISION or not preflight["ready"]
            or checksum(manifest) != EXPECTED_MANIFEST_SHA256
            or preflight["manifestSha256"] != EXPECTED_MANIFEST_SHA256
            or checksum({"rows": manifest["splits"]["final"]}) != EXPECTED_FINAL_SHA256
            or preflight["finalSha256"] != EXPECTED_FINAL_SHA256
            or validation["sealedFinalSha256"] != EXPECTED_FINAL_SHA256
            or package["sealedFinalSha256"] != EXPECTED_FINAL_SHA256
            or not validation["allGatesPass"]
            or validation["selectedQuantile"] != package["quantile"]
            or package["threshold"] != 0.25):
        raise RuntimeError("Validation failed or the frozen final seal changed")
    rows = manifest["splits"]["final"]
    if len(rows) != 256:
        raise RuntimeError("Expected exactly 256 sealed final target scenes")
    print(json.dumps({"gpu": torch.cuda.get_device_name(0),
                      "stagedFinal": stage_images({"final": rows}, scratch)}), flush=True)
    device = torch.device("cuda")
    checkpoint = torch.load(mounted_file("colorcheck-tst100k-expanded-validation", "best.pt"),
                            map_location=device, weights_only=True)
    if checkpoint["epoch"] != 8:
        raise RuntimeError("Frozen v3 checkpoint changed")
    model = ReferenceLutModel().to(device).eval()
    model.load_state_dict(checkpoint["state_dict"])
    measured = extract_split(model, rows, scratch, device)
    extra = extra_metrics(model, rows, scratch, device)
    old_package = json.loads(mounted_file("colorcheck-tst100k-selector-validation", "selector-model.json").read_text())
    if old_package["threshold"] != 0.60:
        raise RuntimeError("Frozen baseline selector changed")
    old_selected = frozen_probability(measured["features"], old_package) >= 0.60
    selected = route(measured["features"], package)
    wrong_selected = route(measured["wrongFeatures"], package)
    result = measured_gates(measured, selected, wrong_selected, old_selected)
    chosen = np.where(selected, measured["lutError"], measured["statsError"])
    gain = measured["statsError"] - chosen
    edge = np.where(selected, extra["lutEdge"], extra["statsEdge"])
    result.update({
        "testScenes": len(rows), "finalSha256": EXPECTED_FINAL_SHA256,
        "selectedQuantile": package["quantile"], "threshold": package["threshold"],
        "meanDeltaEUnchanged": float(np.mean(extra["identityError"])),
        "meanDeltaEAlwaysV3": float(np.mean(measured["lutError"])),
        "gainVsUnchanged": mean_interval((extra["identityError"] - chosen).tolist(), 8414),
        "meanEdgeMae": float(np.mean(edge)),
        "statisticsMeanEdgeMae": float(np.mean(extra["statsEdge"])),
        "v3MeanEdgeMae": float(np.mean(extra["lutEdge"])),
        "betterCount": int(np.sum(gain > 0)), "worseCount": int(np.sum(gain < 0)),
        "tieCount": int(np.sum(gain == 0)),
        "note": "One-time frozen final audit. No model, threshold, or gate may be changed using these scenes.",
    })
    groups = review_groups(rows, gain)
    result["reviewGroups"] = {
        name: [{"scene": scene_id(rows[index]["content"]),
                "gainVsStatistics": float(gain[index]), "selectedLut": bool(selected[index])}
               for index in indices]
        for name, indices in groups.items()
    }
    (output / "final-summary.json").write_text(json.dumps(result, indent=2))
    model.cpu()
    for name, indices in groups.items():
        render_sheet(model, rows, scratch, selected, indices, output / f"{name}.jpg")
    print(json.dumps({"allFinalGatesPass": result["allFinalGatesPass"],
                      "meanGain": result["deltaEGainVsStatistics"]["mean"],
                      "worstLoss": result["worstLossVsStatistics"]}), flush=True)


if __name__ == "__main__":
    main()
