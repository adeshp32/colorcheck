"""Export the preserved V11 checkpoint for honest browser research use.

V11 learned a useful global color transform, but its held-out evaluation did not
prove that the correct reference was consistently more useful than a shuffled
reference. This exporter therefore labels the artifact as research-only. It
performs no calibration and does not need the FiveK photographs: the checkpoint,
its matching training-era model code, and its saved evaluation summary are enough
to create and verify the FP32 ONNX graph.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch


class LutOnly(torch.nn.Module):
    """Expose only the browser-consumed LUT and keep training heads out of ONNX."""

    def __init__(self, model: torch.nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(self, source, reference):
        return self.model(source, reference)[0]


def load_training_module(path: Path):
    """Load the exact architecture saved beside the Kaggle V11 output."""
    spec = importlib.util.spec_from_file_location("colorcheck_v11_model", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load V11 model code from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def probe_inputs(size: int) -> tuple[np.ndarray, np.ndarray]:
    """Create repeatable, non-photographic inputs for cross-runtime comparison."""
    pixel = np.arange(size * size, dtype=np.int64).reshape(size, size)
    source = np.stack(
        [((pixel * (channel * 2 + 3) + channel * 37) % 251) / 250 for channel in range(3)]
    ).astype(np.float32)
    reference = np.stack(
        [
            ((pixel * (channel * 2 + 5) + channel * 53 + 19) % 251) / 250
            for channel in range(3)
        ]
    ).astype(np.float32)
    return source[None], reference[None]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--model-code", type=Path, required=True)
    parser.add_argument("--evaluation-summary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    summary = json.loads(args.evaluation_summary.read_text())
    if checkpoint["epoch"] != summary["bestEpoch"]:
        raise RuntimeError("Checkpoint epoch does not match the saved V11 evaluation.")

    training_module = load_training_module(args.model_code)
    config = checkpoint["config"]
    model = training_module.ReferenceLutModel(
        config["basis_count"], config["lut_size"]
    )
    model.load_state_dict(checkpoint["model"])
    model.eval()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifact = args.output_dir / "colorcheck-v11-fp32.onnx"
    size = config["image_size"]
    example = torch.zeros(1, 3, size, size)
    wrapped = LutOnly(model).eval()
    torch.onnx.export(
        wrapped,
        (example, example),
        artifact,
        input_names=["source", "reference"],
        output_names=["lut"],
        opset_version=18,
        external_data=False,
    )
    onnx.checker.check_model(str(artifact))

    source, reference = probe_inputs(size)
    with torch.inference_mode():
        expected = wrapped(torch.from_numpy(source), torch.from_numpy(reference)).numpy()
    session = ort.InferenceSession(str(artifact), providers=["CPUExecutionProvider"])
    actual = session.run(None, {"source": source, "reference": reference})[0]
    maximum_error = float(np.abs(expected - actual).max())
    if maximum_error > 1e-5:
        raise RuntimeError(f"PyTorch-ONNX parity failed: {maximum_error}")

    flat = actual.reshape(-1)
    indices = np.linspace(0, len(flat) - 1, 64, dtype=np.int64)
    manifest = {
        "id": "colorcheck-v11-reference-research",
        "artifact": artifact.name,
        "bytes": artifact.stat().st_size,
        "sha256": sha256(artifact),
        "training": "ColorCheck-trained reference-conditioned 3D LUT predictor",
        "dataset": "MIT-Adobe FiveK research dataset",
        "checkpointEpoch": checkpoint["epoch"],
        "input": {
            "source": [1, 3, size, size],
            "reference": [1, 3, size, size],
            "colorSpace": "sRGB",
            "range": [0, 1],
        },
        "output": {
            "shape": [1, 3, config["lut_size"], config["lut_size"], config["lut_size"]],
            "order": "batch,channel,blue,green,red",
        },
        "evaluation": {
            "testDeltaE76": summary["test"]["delta_e76"],
            "identityDeltaE76": summary["identityTestBaseline"]["delta_e76"],
            "testClippingPercent": summary["test"]["clipping_percent"],
            "identityClippingPercent": summary["identityTestBaseline"]["clipping_percent"],
            "allDeploymentEvidenceGatesPass": summary["allDeploymentEvidenceGatesPass"],
            "limitation": "Correct-reference discrimination did not pass the held-out deployment gate.",
        },
        "promotion": {
            "role": "Optional non-commercial research comparison",
            "productionReferenceMatcher": False,
        },
        "parity": {"maximumAbsoluteError": maximum_error, "tolerance": 1e-5},
        "browserProbe": {
            "inputGeneration": "colorcheck-modulo-v1",
            "sampleIndices": indices.tolist(),
            "expectedLutValues": flat[indices].astype(float).tolist(),
            "maximumAllowedAbsoluteError": 1e-4,
        },
        "versions": {
            "torch": torch.__version__,
            "onnx": onnx.__version__,
            "onnxruntime": ort.__version__,
        },
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
