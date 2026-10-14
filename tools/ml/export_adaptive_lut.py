"""Export upstream pretrained PyTorch weights; no training or photo upload occurs.

Classifier architecture adapted from HuiZeng/Image-Adaptive-3DLUT (Apache-2.0).
Changes: package the three basis LUTs into the model output, omit native
interpolation extensions, and validate a browser-compatible ONNX artifact.
"""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import onnx
import onnxruntime as ort
import torch
from torch import nn

REVISION = "b491f6df64a588864739a157db271e5c848e1805"
SOURCE = f"https://raw.githubusercontent.com/HuiZeng/Image-Adaptive-3DLUT/{REVISION}"
HASHES = {
    "classifier.pth": "bae9865395625ecae58cfe86147e521093bb1e29e7b2544e02adb238b8035021",
    "LUTs.pth": "c1bb2bc4b7239c1a7e96159f5923123ba796b1fceb0b8c3132b423ea825b821a",
}


class AdaptiveLut(nn.Module):
    """The original classifier predicts coefficients for three learned 33-cube LUTs."""

    def __init__(self, weights: Path):
        super().__init__()
        layers = [
            nn.Upsample(size=(256, 256), mode="bilinear"),
            nn.Conv2d(3, 16, 3, 2, 1),
            nn.LeakyReLU(0.2),
            nn.InstanceNorm2d(16, affine=True),
        ]
        for incoming, outgoing, normalize in [
            (16, 32, True),
            (32, 64, True),
            (64, 128, True),
            (128, 128, False),
        ]:
            layers.extend([nn.Conv2d(incoming, outgoing, 3, 2, 1), nn.LeakyReLU(0.2)])
            if normalize:
                layers.append(nn.InstanceNorm2d(outgoing, affine=True))
        layers.extend([nn.Dropout(0.5), nn.Conv2d(128, 3, 8)])
        self.model = nn.Sequential(*layers)
        self.load_state_dict(
            torch.load(
                weights / "classifier.pth", map_location="cpu", weights_only=True
            )
        )
        basis = torch.load(weights / "LUTs.pth", map_location="cpu", weights_only=True)
        self.register_buffer(
            "basis", torch.stack([basis[str(i)]["LUT"] for i in range(3)])
        )

    def forward(self, image):
        coefficients = self.model(image).reshape(3)
        lut = (coefficients.reshape(3, 1, 1, 1, 1) * self.basis).sum(dim=0)
        return lut, coefficients


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--weights", type=Path, default=Path(".local/adaptive-lut-weights")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("web/assets/models/adaptive-lut")
    )
    args = parser.parse_args()
    args.weights.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, expected in HASHES.items():
        path = args.weights / name
        if not path.exists():
            with urlopen(
                f"{SOURCE}/pretrained_models/sRGB/{name}", timeout=60
            ) as response:
                path.write_bytes(response.read())
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Checkpoint checksum mismatch: {name}")
    torch.set_num_threads(2)
    model = AdaptiveLut(args.weights).eval()
    example = torch.zeros(1, 3, 256, 256)
    output = args.output / "enhancement.onnx"
    torch.onnx.export(
        model,
        (example,),
        output,
        input_names=["image"],
        output_names=["lut", "coefficients"],
        opset_version=18,
        dynamo=True,
        external_data=False,
    )
    onnx.checker.check_model(str(output))
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    session = ort.InferenceSession(
        str(output), sess_options=options, providers=["CPUExecutionProvider"]
    )
    rng = np.random.default_rng(42)
    grid = np.linspace(0, 1, 256, dtype=np.float32)
    gradient = np.stack(
        [
            np.broadcast_to(grid, (256, 256)),
            np.broadcast_to(grid[:, None], (256, 256)),
            np.full((256, 256), 0.5, dtype=np.float32),
        ]
    )[None].copy()
    fixtures = [
        np.zeros((1, 3, 256, 256), dtype=np.float32),
        np.ones((1, 3, 256, 256), dtype=np.float32),
        gradient,
        rng.random((1, 3, 256, 256), dtype=np.float32),
    ]
    max_error = 0.0
    fixture_errors = []
    for index, image in enumerate(fixtures):
        with torch.no_grad():
            expected = model(torch.from_numpy(image))[0].numpy()
        actual = session.run(None, {"image": image})[0]
        error = float(np.max(np.abs(expected - actual)))
        # Near-zero InstanceNorm variance amplifies floating-point differences on black input.
        tolerance = 1 / 255 if index == 0 else 1e-4
        fixture_errors.append(
            {
                "name": ["black", "white", "gradient", "noise"][index],
                "maximumAbsoluteError": error,
                "tolerance": tolerance,
            }
        )
        max_error = max(max_error, error)
        if error > tolerance:
            raise ValueError(f"PyTorch/ONNX parity failed on fixture {index}: {error}")
    with torch.no_grad():
        probe_lut, probe_coefficients = model(torch.from_numpy(gradient))
    manifest = {
        "id": "adaptive-lut-srgb-v1",
        "artifact": "enhancement.onnx",
        "bytes": output.stat().st_size,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "license": "Apache-2.0",
        "source": "https://github.com/HuiZeng/Image-Adaptive-3DLUT",
        "revision": REVISION,
        "sourceWeights": HASHES,
        "input": {"shape": [1, 3, 256, 256], "colorSpace": "sRGB", "range": [0, 1]},
        "output": {"shape": [3, 33, 33, 33], "order": "channel,blue,green,red"},
        "training": "Upstream pretrained paired sRGB enhancement weights; not trained by ColorCheck.",
        "parity": {"fixtures": fixture_errors, "maximumAbsoluteError": max_error},
        "browserProbe": {
            "coefficients": probe_coefficients.tolist(),
            "lutSamples": probe_lut.flatten()[::2000].tolist(),
        },
        "versions": {
            "pytorch": torch.__version__,
            "onnx": onnx.__version__,
            "onnxruntime": ort.__version__,
        },
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {"modelBytes": manifest["bytes"], "parity": manifest["parity"]}, indent=2
        )
    )


if __name__ == "__main__":
    main()
