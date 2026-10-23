"""Export FP32 and calibrated INT8 ONNX models, then measure their divergence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch
from onnxruntime.quantization import (
    CalibrationDataReader,
    QuantFormat,
    QuantType,
    quantize_static,
)
from onnxruntime.quantization.shape_inference import quant_pre_process

from .dataset import FiveKReferenceDataset, SplitManifest
from .model import ReferenceLutModel
from .model import apply_lut


class LutOnly(torch.nn.Module):
    """Keep coefficient logits internal so static quantization can calibrate them."""

    def __init__(self, model: ReferenceLutModel) -> None:
        super().__init__()
        self.model = model

    def forward(self, source, reference):
        return self.model(source, reference)[0]


class QuantizedBasisLutOnly(torch.nn.Module):
    """Store dominant LUT tensors as UINT8 while retaining a float LUT output."""

    def __init__(self, model: ReferenceLutModel) -> None:
        super().__init__()
        self.model = model
        quantized = (model.basis.detach().clamp(0, 1) * 255).round().to(torch.uint8)
        self.register_buffer("quantized_basis", quantized)

    def forward(self, source, reference):
        coefficients = self.model.predict_coefficients(source, reference)
        basis = self.quantized_basis.to(coefficients.dtype) / 255
        return torch.einsum("bk,kcxyz->bcxyz", coefficients, basis)


class FiveKCalibrationReader(CalibrationDataReader):
    def __init__(self, dataset: FiveKReferenceDataset, samples: int) -> None:
        self.dataset = dataset
        self.indices = iter(range(min(samples, len(dataset))))

    def get_next(self):
        try:
            sample = self.dataset[next(self.indices)]
        except StopIteration:
            return None
        return {
            "source": sample["source"].unsqueeze(0).numpy(),
            "reference": sample["reference"].unsqueeze(0).numpy(),
        }


def load_splits(path: Path) -> SplitManifest:
    payload = json.loads(path.read_text())
    return SplitManifest(
        train=tuple(payload["train"]),
        validation=tuple(payload["validation"]),
        test=tuple(payload["test"]),
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deployment_decision(
    checkpoint: dict, evaluation_summary: dict, quantization_accepted: bool
) -> dict:
    """Combine model-quality and artifact-parity evidence into one promotion gate.

    Export is useful during research even when a model is not good enough to ship.
    Promotion is stricter: the summary must describe the same selected epoch, all
    held-out evidence gates must pass, and quantization must remain within the
    declared rendered-pixel tolerances.
    """
    same_checkpoint = evaluation_summary.get("bestEpoch") == checkpoint.get("epoch")
    quality_accepted = bool(
        evaluation_summary.get("allDeploymentEvidenceGatesPass", False)
    )
    return {
        "sameCheckpointAsEvaluation": same_checkpoint,
        "qualityEvidenceAccepted": quality_accepted,
        "quantizationAccepted": quantization_accepted,
        "deploymentReady": same_checkpoint
        and quality_accepted
        and quantization_accepted,
    }


def compare_sessions(fp32_path: Path, int8_path: Path, dataset, samples: int):
    fp32 = ort.InferenceSession(str(fp32_path), providers=["CPUExecutionProvider"])
    int8 = ort.InferenceSession(str(int8_path), providers=["CPUExecutionProvider"])
    maximum = 0.0
    total = 0.0
    values = 0
    image_maximum = 0.0
    image_total = 0.0
    image_values = 0
    for index in range(min(samples, len(dataset))):
        sample = dataset[index]
        inputs = {
            "source": sample["source"].unsqueeze(0).numpy(),
            "reference": sample["reference"].unsqueeze(0).numpy(),
        }
        fp_lut = fp32.run(None, inputs)[0]
        int_lut = int8.run(None, inputs)[0]
        difference = np.abs(fp_lut - int_lut)
        maximum = max(maximum, float(difference.max()))
        total += float(difference.sum())
        values += difference.size
        source = sample["source"].unsqueeze(0)
        fp_image = apply_lut(source, torch.from_numpy(fp_lut))
        int_image = apply_lut(source, torch.from_numpy(int_lut))
        image_difference = (fp_image - int_image).abs()
        image_maximum = max(image_maximum, image_difference.max().item())
        image_total += image_difference.sum().item()
        image_values += image_difference.numel()
    return {
        "samples": min(samples, len(dataset)),
        "lutMaximumAbsoluteError": maximum,
        "lutMeanAbsoluteError": total / values,
        "renderMaximumAbsoluteError": image_maximum,
        "renderMeanAbsoluteError": image_total / image_values,
    }


def browser_probe_inputs(size: int) -> dict[str, np.ndarray]:
    """Build portable deterministic inputs without embedding photographs."""
    pixel = np.arange(size * size, dtype=np.int64).reshape(size, size)
    source = np.stack(
        [
            ((pixel * (channel * 2 + 3) + channel * 37) % 251) / 250
            for channel in range(3)
        ]
    ).astype(np.float32)
    reference = np.stack(
        [
            ((pixel * (channel * 2 + 5) + channel * 53 + 19) % 251) / 250
            for channel in range(3)
        ]
    ).astype(np.float32)
    return {"source": source[None], "reference": reference[None]}


def create_browser_probe(model_path: Path, size: int, sample_count: int = 64) -> dict:
    """Record sparse expected LUT values for an ONNX Runtime Web parity test."""
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    lut = session.run(None, browser_probe_inputs(size))[0].reshape(-1)
    indices = np.linspace(0, len(lut) - 1, sample_count, dtype=np.int64)
    return {
        "inputGeneration": "colorcheck-modulo-v1",
        "inputSize": size,
        "artifact": model_path.name,
        "sampleIndices": indices.tolist(),
        "expectedLutValues": lut[indices].astype(float).tolist(),
        "maximumAllowedAbsoluteError": 1e-4,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dataset-zip", type=Path, help="Local FiveK ZIP archive")
    source.add_argument(
        "--dataset-root",
        type=Path,
        help="Extracted FiveK directory or Kaggle mount containing raw/a/b/c/d/e",
    )
    parser.add_argument("--splits", type=Path, required=True)
    parser.add_argument(
        "--evaluation-summary",
        type=Path,
        required=True,
        help="summary.json produced by the training run that selected this checkpoint",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path(".local/reference-matcher/export")
    )
    parser.add_argument("--calibration-samples", type=int, default=128)
    parser.add_argument("--comparison-samples", type=int, default=64)
    args = parser.parse_args()
    dataset_path = args.dataset_zip or args.dataset_root
    args.output_dir.mkdir(parents=True, exist_ok=True)

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    config = checkpoint["config"]
    model = ReferenceLutModel(config["basis_count"], config["lut_size"])
    model.load_state_dict(checkpoint["model"])
    model.eval()
    size = config["image_size"]
    example = torch.zeros(1, 3, size, size)
    fp32_path = args.output_dir / "reference-matcher-fp32.onnx"
    lut_only = LutOnly(model).eval()
    torch.onnx.export(
        lut_only,
        (example, example),
        fp32_path,
        input_names=["source", "reference"],
        output_names=["lut"],
        opset_version=18,
        external_data=False,
    )
    onnx.checker.check_model(str(fp32_path))
    quantized_basis_path = args.output_dir / "reference-matcher-uint8-basis.onnx"
    quantized_lut_only = QuantizedBasisLutOnly(model).eval()
    torch.onnx.export(
        quantized_lut_only,
        (example, example),
        quantized_basis_path,
        input_names=["source", "reference"],
        output_names=["lut"],
        opset_version=18,
        external_data=False,
        do_constant_folding=False,
    )
    onnx.checker.check_model(str(quantized_basis_path))
    preprocessed_path = args.output_dir / "reference-matcher-fp32-preprocessed.onnx"
    quant_pre_process(
        str(quantized_basis_path),
        str(preprocessed_path),
        skip_symbolic_shape=True,
        skip_optimization=True,
    )

    splits = load_splits(args.splits)
    calibration = FiveKReferenceDataset(
        dataset_path, splits.validation, size, training=False, seed=config["seed"]
    )
    int8_path = args.output_dir / "reference-matcher-int8.onnx"
    quantize_static(
        model_input=str(preprocessed_path),
        model_output=str(int8_path),
        calibration_data_reader=FiveKCalibrationReader(
            calibration, args.calibration_samples
        ),
        quant_format=QuantFormat.QDQ,
        activation_type=QuantType.QUInt8,
        weight_type=QuantType.QInt8,
        per_channel=True,
        op_types_to_quantize=["Conv", "MatMul", "Gemm"],
    )
    onnx.checker.check_model(str(int8_path))
    comparison = compare_sessions(
        fp32_path, int8_path, calibration, args.comparison_samples
    )
    fp32_bytes = fp32_path.stat().st_size
    int8_bytes = int8_path.stat().st_size
    accepted = (
        int8_bytes < fp32_bytes
        and comparison["lutMeanAbsoluteError"] <= 1 / 255
        and comparison["lutMaximumAbsoluteError"] <= 2 / 255
        and comparison["renderMeanAbsoluteError"] <= 0.5 / 255
        and comparison["renderMaximumAbsoluteError"] <= 2 / 255
    )
    evaluation_summary = json.loads(args.evaluation_summary.read_text())
    decision = deployment_decision(checkpoint, evaluation_summary, accepted)
    browser_artifact = int8_path if accepted else fp32_path
    manifest = {
        "id": "colorcheck-reference-matcher-v1",
        "training": "ColorCheck-trained reference-conditioned 3D LUT predictor",
        "checkpointEpoch": checkpoint["epoch"],
        "validation": checkpoint["validation"],
        "inputs": {"source": [1, 3, size, size], "reference": [1, 3, size, size]},
        "outputs": {
            "lut": [1, 3, config["lut_size"], config["lut_size"], config["lut_size"]],
            "order": "batch,channel,blue,green,red",
        },
        "fp32": {
            "artifact": fp32_path.name,
            "bytes": fp32_bytes,
            "sha256": digest(fp32_path),
        },
        "int8": {
            "artifact": int8_path.name,
            "bytes": int8_bytes,
            "sha256": digest(int8_path),
            "format": "INT8 QDQ encoder with UINT8 LUT bases",
            "calibrationSamples": min(args.calibration_samples, len(calibration)),
        },
        "quantizationComparison": comparison,
        "quantizedAccepted": accepted,
        "evaluationSummarySha256": digest(args.evaluation_summary),
        "promotionGates": decision,
        "recommendedArtifact": int8_path.name if decision["deploymentReady"] else None,
        "browserProbe": create_browser_probe(browser_artifact, size),
        "versions": {
            "torch": torch.__version__,
            "onnx": onnx.__version__,
            "onnxruntime": ort.__version__,
        },
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
