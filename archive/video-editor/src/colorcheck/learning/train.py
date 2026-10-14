"""Run with python -m colorcheck.learning.train; all outputs stay local."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from colorcheck.analysis.correction import LIMITS, apply_correction_array
from colorcheck.analysis.learned import (
    FEATURE_NAMES,
    HIDDEN_SIZE,
    PARAMETER_NAMES,
    SCHEMA_VERSION,
    CorrectionRegressor,
    load_regressor,
    parameters_to_plan,
)
from colorcheck.learning.data import (
    IDENTITY,
    Examples,
    build_examples,
    lab_error,
    read_manifest,
    split_sources,
)


def make_network(torch):
    return torch.nn.Sequential(
        torch.nn.Linear(len(FEATURE_NAMES), HIDDEN_SIZE), torch.nn.ReLU(),
        torch.nn.Linear(HIDDEN_SIZE, HIDDEN_SIZE), torch.nn.ReLU(),
        torch.nn.Linear(HIDDEN_SIZE, 5), torch.nn.Tanh(),
    )


def render_tensor(torch, pixels, parameters):
    exposure = torch.exp2(parameters[:, 0] * 0.35)[:, None, None]
    gains = torch.stack([
        1.0 + parameters[:, 3] * 0.08,
        torch.ones_like(parameters[:, 0]),
        1.0 + parameters[:, 4] * 0.08,
    ], dim=1)[:, None, :]
    data = pixels * exposure * gains
    data = (data - 0.5) * (1.0 + parameters[:, 1] * 0.15)[:, None, None] + 0.5
    luma = (data * data.new_tensor([0.2126, 0.7152, 0.0722])).sum(dim=2, keepdim=True)
    data = luma + (data - luma) * (1.0 + parameters[:, 2] * 0.15)[:, None, None]
    return torch.clamp(data, 0.0, 1.0)


def normalization(features: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "feature_mean": features.mean(axis=0).astype(np.float32),
        "feature_scale": np.maximum(features.std(axis=0), 1e-4).astype(np.float32),
        "feature_min": features.min(axis=0).astype(np.float32),
        "feature_max": features.max(axis=0).astype(np.float32),
    }


def train_regressor(
    train: Examples,
    validation: Examples,
    *,
    epochs: int,
    seed: int,
    device: str = "cpu",
    batch_size: int = 128,
):
    import torch

    torch.set_num_threads(2)
    torch.manual_seed(seed)
    if device == "mps" and not torch.backends.mps.is_available():
        raise ValueError("MPS is unavailable; use --device cpu.")
    if device == "cpu":
        torch.use_deterministic_algorithms(True)
    stats = normalization(train.features)
    network = make_network(torch).to(device)
    optimizer = torch.optim.AdamW(network.parameters(), lr=0.002, weight_decay=0.0001)

    def tensors(examples):
        inputs = (examples.features - stats["feature_mean"]) / stats["feature_scale"]
        return [torch.as_tensor(array, device=device) for array in (
            inputs, examples.parameters, examples.target_pixels, examples.reference_pixels,
        )]

    train_x, train_y, train_pixels, train_reference = tensors(train)
    val_x, val_y, val_pixels, val_reference = tensors(validation)
    rng = np.random.default_rng(seed)
    best_loss, best_epoch, best_weights = float("inf"), 0, None
    history = []

    def objective(parameters, labels, pixels, reference):
        reconstruction = render_tensor(torch, pixels, parameters)
        return 10.0 * (reconstruction - reference).square().mean() + (
            0.02 * (parameters - labels).square().mean()
        )

    for epoch in range(1, epochs + 1):
        network.train()
        losses = []
        order = rng.permutation(len(train_x))
        for offset in range(0, len(order), batch_size):
            index = torch.as_tensor(order[offset:offset + batch_size], device=device)
            optimizer.zero_grad(set_to_none=True)
            prediction = network(train_x[index])
            loss = objective(prediction, train_y[index], train_pixels[index], train_reference[index])
            if not torch.isfinite(loss):
                raise ValueError("Training produced a non-finite loss.")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(network.parameters(), 1.0)
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        network.eval()
        with torch.inference_mode():
            prediction = network(val_x)
            val_loss = float(objective(prediction, val_y, val_pixels, val_reference).cpu())
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses)),
                        "validation_loss": val_loss})
        if val_loss < best_loss:
            best_loss, best_epoch = val_loss, epoch
            best_weights = {key: value.detach().cpu().clone()
                            for key, value in network.state_dict().items()}
        if epoch == 1 or epoch % 25 == 0:
            print(f"epoch={epoch} train={np.mean(losses):.6f} validation={val_loss:.6f}", flush=True)
        if epoch - best_epoch >= 50:
            break
    if best_weights is None:
        raise ValueError("No usable training checkpoint.")
    network.load_state_dict(best_weights)
    arrays = {**stats}
    for index, layer in enumerate((0, 2, 4)):
        arrays[f"weight_{index}"] = best_weights[f"{layer}.weight"].numpy().copy()
        arrays[f"bias_{index}"] = best_weights[f"{layer}.bias"].numpy().copy()
    with torch.inference_mode():
        torch_predictions = network(val_x).cpu().numpy()
    numpy_predictions = np.stack([
        CorrectionRegressor(arrays, {}).predict(features, check_domain=False)
        for features in validation.features
    ])
    parity_error = float(np.max(np.abs(torch_predictions - numpy_predictions)))
    if parity_error > 1e-5:
        raise ValueError("Exported NumPy weights do not match training inference.")
    return arrays, history, best_epoch, parity_error, torch.__version__


def predict_pixels(model: CorrectionRegressor, examples: Examples, *, check_domain: bool):
    pixels, accepted = [], []
    for index, features in enumerate(examples.features):
        parameters = model.predict(features, check_domain=check_domain)
        accepted.append(parameters is not None)
        if parameters is None:
            pixels.append(examples.baseline_pixels[index])
            continue
        if np.max(np.abs(features[20:30])) < 1e-5:
            parameters = np.zeros(5, dtype=np.float32)
        plan = parameters_to_plan(parameters, IDENTITY)
        corrected = apply_correction_array(examples.target_pixels[index][None, :, :], plan)[0]
        pixels.append(corrected)
    return np.asarray(pixels), np.asarray(accepted)


def _group_bootstrap(delta: np.ndarray, groups: tuple[str, ...]) -> list[float]:
    independent = np.array([delta[np.asarray(groups) == group].mean() for group in sorted(set(groups))])
    rng = np.random.default_rng(2026)
    means = rng.choice(independent, size=(2000, len(independent)), replace=True).mean(axis=1)
    return np.quantile(means, [0.025, 0.975]).tolist()


def evaluate(model: CorrectionRegressor, examples: Examples) -> dict:
    learned, accepted = predict_pixels(model, examples, check_domain=True)
    methods = {"identity": examples.target_pixels, "rules": examples.baseline_pixels,
               "learned_with_fallback": learned}
    errors = {name: np.abs(pixels - examples.reference_pixels).mean(axis=(1, 2))
              for name, pixels in methods.items()}
    metrics = {
        name: {"mean_rgb_mae": float(errors[name].mean()),
               "mean_lab_delta_e76": float(lab_error(pixels, examples.reference_pixels).mean())}
        for name, pixels in methods.items()
    }
    identity = np.max(np.abs(examples.parameters), axis=1) == 0
    clipping = ((learned <= 0.002) | (learned >= 0.998)).mean(axis=(1, 2))
    metrics["comparison"] = {
        "improvement_over_rules_percent": float(
            (1.0 - errors["learned_with_fallback"].mean() / max(errors["rules"].mean(), 1e-8)) * 100
        ),
        "improvement_over_identity_percent": float(
            (1.0 - errors["learned_with_fallback"].mean() / max(errors["identity"].mean(), 1e-8)) * 100
        ),
        "wins_over_rules_percent": float(np.mean(
            errors["learned_with_fallback"] < errors["rules"] - 1e-6
        ) * 100),
        "regressions_over_rules_percent": float(np.mean(
            errors["learned_with_fallback"] > errors["rules"] + 1e-6
        ) * 100),
        "rule_minus_learned_mae_group_bootstrap_95_ci": _group_bootstrap(
            errors["rules"] - errors["learned_with_fallback"], examples.groups,
        ),
        "model_coverage_percent": float(accepted.mean() * 100),
        "identity_rgb_mae": float(errors["learned_with_fallback"][identity].mean()),
        "mean_clipped_channel_percent": float(clipping.mean() * 100),
    }
    return metrics


def save_artifact(path: Path, arrays: dict[str, np.ndarray], metadata: dict) -> None:
    encoded = np.frombuffer(json.dumps(metadata, sort_keys=True).encode(), dtype=np.uint8)
    np.savez_compressed(path, **arrays, metadata=encoded)
    load_regressor(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train an experimental bounded color regressor.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--variants", type=int, default=32)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    args = parser.parse_args()
    if not 1 <= args.epochs <= 1000 or not 8 <= args.variants <= 64:
        parser.error("Use 1-1000 epochs and 8-64 variants.")
    if args.out.exists():
        parser.error("Output directory already exists; choose a new run name.")
    sources = read_manifest(args.manifest)
    if not 20 <= len(sources) <= 500:
        parser.error("This local workflow supports 20-500 source images.")
    splits = split_sources(sources, args.seed)
    args.out.mkdir(parents=True)
    start = time.perf_counter()
    examples = {name: build_examples(rows, args.variants, args.seed + offset * 1000)
                for offset, (name, rows) in enumerate(splits.items())}
    print("examples=" + json.dumps({name: len(data.features) for name, data in examples.items()}),
          flush=True)
    arrays, history, best_epoch, parity, torch_version = train_regressor(
        examples["train"], examples["validation"], epochs=args.epochs,
        seed=args.seed, device=args.device,
    )
    model = CorrectionRegressor(arrays, {})
    validation = evaluate(model, examples["validation"])
    # Test data is evaluated only after validation has selected the checkpoint.
    test = evaluate(model, examples["test"])
    comparison = test["comparison"]
    gate = (
        comparison["improvement_over_rules_percent"] >= 10.0
        and comparison["improvement_over_identity_percent"] >= 10.0
        and comparison["identity_rgb_mae"] < 0.001
        and comparison["rule_minus_learned_mae_group_bootstrap_95_ci"][0] > 0.0
    )
    for _ in range(20):
        model.predict(examples["test"].features[0], check_domain=False)
    inference_start = time.perf_counter()
    for _ in range(1000):
        model.predict(examples["test"].features[0], check_domain=False)
    latency_ms = (time.perf_counter() - inference_start) / 1000 * 1000
    code_files = [Path(__file__), Path(__file__).with_name("data.py"),
                  Path(__file__).parents[1] / "analysis" / "learned.py"]
    code_hash = hashlib.sha256(b"".join(path.read_bytes() for path in code_files)).hexdigest()
    manifest_hash = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    metadata = {
        "schema_version": SCHEMA_VERSION, "features": list(FEATURE_NAMES),
        "parameters": list(PARAMETER_NAMES), "limits": LIMITS,
        "status": "experimental", "synthetic_gate_passed": gate,
        "dataset_sha256": manifest_hash, "training_code_sha256": code_hash,
        "seed": args.seed, "best_epoch": best_epoch,
        "label_source": "known inverse color transforms on natural photographs; not expert grades",
    }
    save_artifact(args.out / "correction.npz", arrays, metadata)
    report = {
        **metadata, "created_at": datetime.now(UTC).isoformat(),
        "config": {"epochs": args.epochs, "variants": args.variants, "device": args.device},
        "environment": {"python": platform.python_version(), "torch": torch_version,
                        "numpy": np.__version__, "machine": platform.machine()},
        "splits": {name: {"images": len(rows), "groups": len({row.group for row in rows}),
                          "examples": len(examples[name].features),
                          "image_ids": [row.image_id for row in rows]}
                   for name, rows in splits.items()},
        "validation": validation, "test": test, "history": history,
        "parameter_count": sum(array.size for name, array in arrays.items()
                               if name.startswith(("weight_", "bias_"))),
        "numpy_parity_max_abs_error": parity,
        "inference_ms_excluding_feature_extraction": latency_ms,
        "total_seconds": time.perf_counter() - start,
        "limitations": [
            "Same-scene synthetic pairs, not human retouch labels or cinematic preferences.",
            "Global sRGB statistics only; no semantic masks, HDR/log calibration or local relighting.",
            "Single clip-wide grade; real motion, shot boundaries and temporal consistency unvalidated.",
            "Group bootstrap is descriptive on this small corpus, not a generalization guarantee.",
            "A synthetic gate is not approval for a production model release.",
        ],
    }
    (args.out / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"synthetic_gate_passed": gate, "test": test,
                      "total_seconds": report["total_seconds"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
