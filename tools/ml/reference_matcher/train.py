"""Train, validate, and test ColorCheck's reference-conditioned 3D LUT model.

This module contains the complete learning loop. The command line interface is
shared by local development and Kaggle so the same model is evaluated under the
same rules in both environments.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from contextlib import nullcontext
from pathlib import Path

import numpy as np
import torch
from torch.optim import AdamW
from torch.utils.data import DataLoader, Subset
from tqdm import tqdm

from .dataset import FiveKReferenceDataset, create_splits, inspect_dataset
from .evaluation import (
    MetricStore,
    coefficient_diagnostics,
    metric_samples,
    mismatch_references,
    paired_improvement,
    statistics_match,
)
from .losses import (
    ReferenceMatchLoss,
    exact_lut_supervision_loss,
    reference_ranking_loss,
    rgb_to_lab,
)
from .model import ReferenceLutModel, apply_lut


def choose_device(requested: str) -> torch.device:
    """Select CUDA on Kaggle, Apple Metal locally, or CPU as a final fallback."""
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def choose_mixed_precision(requested: str, device: torch.device) -> torch.dtype | None:
    """Choose a lower-precision CUDA format without changing stored checkpoints.

    Mixed precision accelerates temporary matrix operations during training.
    Model parameters and saved checkpoints remain full precision. Automatic mode
    deliberately stays off for CPU and Apple Metal, where this pipeline has not
    demonstrated a reliable speed advantage.
    """
    if requested == "off":
        return None
    if requested == "fp16":
        if device.type != "cuda":
            raise ValueError("FP16 training is only enabled for CUDA in this pipeline")
        return torch.float16
    if requested == "bf16":
        if device.type != "cuda" or not torch.cuda.is_bf16_supported():
            raise ValueError("BF16 was requested, but this CUDA device does not support it")
        return torch.bfloat16
    if device.type == "cuda":
        return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    return None


def autocast_context(device: torch.device, dtype: torch.dtype | None):
    """Return a PyTorch precision context or a no-op context when AMP is disabled."""
    if dtype is None:
        return nullcontext()
    return torch.autocast(device_type=device.type, dtype=dtype)


def move_images(batch, device: torch.device) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Transfer only image tensors to the accelerator.

    Metadata such as scene filenames remains on the CPU. ``non_blocking`` lets
    CUDA overlap a transfer with computation when DataLoader uses pinned memory.
    """
    non_blocking = device.type == "cuda"
    return (
        batch["source"].to(device, non_blocking=non_blocking),
        batch["reference"].to(device, non_blocking=non_blocking),
        batch["expected"].to(device, non_blocking=non_blocking),
    )


def batch_metrics(output: torch.Tensor, expected: torch.Tensor) -> dict[str, float]:
    """Calculate interpretable image-quality measurements for one batch."""
    # Metrics are intentionally computed in float32 so mixed precision cannot
    # make the reported validation result appear better or worse by rounding.
    output = output.float()
    expected = expected.float()
    mse = (output - expected).square().mean()
    psnr = -10 * torch.log10(mse.clamp_min(1e-10))
    delta_e = (rgb_to_lab(output) - rgb_to_lab(expected)).square().sum(1).sqrt().mean()
    clipping = (
        ((output <= 1 / 255) | (output >= 254 / 255)).any(dim=1).float().mean() * 100
    )
    return {
        "psnr": psnr.item(),
        "delta_e76": delta_e.item(),
        "clipping_percent": clipping.item(),
    }


@torch.no_grad()
def validate(
    model,
    loader,
    device,
    loss_function,
    mixed_precision: torch.dtype | None = None,
    shuffled_reference: bool = False,
):
    """Evaluate without updating weights and average metrics per photograph."""
    model.eval()
    totals: dict[str, float] = {}
    count = 0
    for batch in tqdm(loader, desc="validate", leave=False):
        source, reference, expected = move_images(batch, device)

        # Rolling references by one position intentionally gives every source
        # the wrong reference. A useful reference-conditioned model should score
        # worse here than it does with the correct references.
        if shuffled_reference and reference.shape[0] > 1:
            reference = reference.roll(1, 0)

        with autocast_context(device, mixed_precision):
            lut, _ = model(source, reference)
            output = apply_lut(source, lut)

        # Keep the loss calculation numerically stable and comparable across
        # GPUs by converting model outputs back to float32.
        loss, components = loss_function(
            output.float(), expected.float(), source.float(), lut.float()
        )
        values = {"loss": loss.item(), **batch_metrics(output, expected)}
        values.update({name: value.item() for name, value in components.items()})
        batch_size = source.shape[0]
        for name, value in values.items():
            totals[name] = totals.get(name, 0.0) + value * batch_size
        count += batch_size
    return {name: value / count for name, value in totals.items()}


@torch.no_grad()
def identity_baseline(loader, device):
    """Measure the result of doing nothing to establish a minimum useful score."""
    totals: dict[str, float] = {}
    count = 0
    for batch in tqdm(loader, desc="identity baseline", leave=False):
        source = batch["source"].to(device, non_blocking=device.type == "cuda")
        expected = batch["expected"].to(device, non_blocking=device.type == "cuda")
        values = batch_metrics(source, expected)
        for name, value in values.items():
            totals[name] = totals.get(name, 0.0) + value * source.shape[0]
        count += source.shape[0]
    return {name: value / count for name, value in totals.items()}


def checkpoint_selection_score(
    real_validation: dict[str, float],
    synthetic_validation: dict[str, float],
) -> float:
    """Balance photographic edits and exact reference transfer during selection.

    Both validation sets use the same held-out scene identities, but ask different
    questions. Real FiveK pairs reward plausible expert enhancement; synthetic
    pairs verify that one style applied to two unrelated photographs can be
    recovered from the reference. Their equally weighted DeltaE76 mean is easy to
    audit and prevents either objective from selecting the checkpoint alone.
    """
    return (real_validation["delta_e76"] + synthetic_validation["delta_e76"]) / 2


@torch.no_grad()
def comprehensive_evaluation(model, loader, device, mixed_precision, seed: int = 42):
    """Run final product-oriented controls after checkpoint selection.

    This deliberately runs only on the untouched test split. It compares the
    learned model with doing nothing and with the editor's current statistics
    matcher, then repeats inference with incorrect references. Results retain
    per-photo uncertainty and expert-specific behavior.
    """
    model.eval()
    stores = {
        "model": MetricStore(),
        "identity": MetricStore(),
        "statisticsMatch": MetricStore(),
        "shuffledReference": MetricStore(),
    }
    sensitivities: list[float] = []
    all_coefficients = []
    elapsed_seconds = 0.0
    peak_memory = 0

    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)

    for batch in tqdm(loader, desc="comprehensive evaluation", leave=False):
        source, reference, expected = move_images(batch, device)
        experts = batch["expert"]
        scenes = batch["scene"]
        wrong_reference, _ = mismatch_references(reference, experts)

        if device.type == "cuda":
            torch.cuda.synchronize(device)
        started = time.perf_counter()
        with autocast_context(device, mixed_precision):
            lut, coefficients = model(source, reference)
            output = apply_lut(source, lut)
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        elapsed_seconds += time.perf_counter() - started

        # Wrong-reference inference is an evaluation control, not product
        # latency, so it is deliberately outside the timed region.
        with autocast_context(device, mixed_precision):
            wrong_lut, _ = model(source, wrong_reference)
            wrong_output = apply_lut(source, wrong_lut)

        output = output.float()
        wrong_output = wrong_output.float()
        stores["model"].add(metric_samples(output, expected), experts, scenes)
        stores["identity"].add(metric_samples(source, expected), experts, scenes)
        stores["statisticsMatch"].add(
            metric_samples(statistics_match(source, reference), expected), experts, scenes
        )
        stores["shuffledReference"].add(
            metric_samples(wrong_output, expected), experts, scenes
        )
        sensitivities.extend(
            (output - wrong_output).abs().flatten(1).mean(1).cpu().tolist()
        )
        all_coefficients.append(coefficients.detach().float().cpu())

    if device.type == "cuda":
        peak_memory = torch.cuda.max_memory_allocated(device)

    summaries = {name: store.summary(seed) for name, store in stores.items()}
    identity_gain = paired_improvement(stores["model"], stores["identity"], seed)
    statistics_gain = paired_improvement(
        stores["model"], stores["statisticsMatch"], seed
    )
    wrong_reference_gain = paired_improvement(
        stores["model"], stores["shuffledReference"], seed
    )
    sensitivity = np.asarray(sensitivities)
    sample_count = len(sensitivity)
    coefficient_report = coefficient_diagnostics(torch.cat(all_coefficients))
    gates = {
        # Require the complete confidence interval to favor the model. These are
        # conservative evidence gates, not claims of subjective superiority.
        "beatsIdentityDeltaE2000": identity_gain["deltaE2000"]["ci95Lower"] > 0,
        "beatsIdentitySsim": identity_gain["ssim"]["ci95Lower"] > 0,
        "beatsStatisticsDeltaE2000": statistics_gain["deltaE2000"]["ci95Lower"] > 0,
        "correctReferenceBeatsShuffledDeltaE2000": (
            wrong_reference_gain["deltaE2000"]["ci95Lower"] > 0
        ),
        "respondsToReference": float(sensitivity.mean()) > 1 / 1024,
        "avoidsSingleBasisCollapse": (
            max(coefficient_report["meanBasisWeights"]) < 0.9
            and coefficient_report["dominantBasisFraction"] < 0.9
        ),
        "doesNotIncreaseClippingVsIdentity": (
            identity_gain["clippingPercent"]["ci95Lower"] >= 0
        ),
    }
    return {
        "metrics": summaries,
        "pairedImprovementOverIdentity": identity_gain,
        "pairedImprovementOverStatisticsMatch": statistics_gain,
        "pairedImprovementFromCorrectReference": wrong_reference_gain,
        "referenceSensitivityMae": {
            "mean": float(sensitivity.mean()),
            "minimum": float(sensitivity.min()),
            "maximum": float(sensitivity.max()),
            "sampleCount": sample_count,
        },
        "mixtureDiagnostics": coefficient_report,
        "runtime": {
            "singleModelAndLutMillisecondsPerImage": elapsed_seconds * 1000 / sample_count,
            "cudaPeakMemoryBytes": peak_memory,
            "parameterCount": sum(parameter.numel() for parameter in model.parameters()),
        },
        "deploymentEvidenceGates": gates,
        "allEvidenceGatesPass": all(gates.values()),
    }


def build_loader(dataset, batch_size: int, shuffle: bool, workers: int, use_cuda: bool):
    """Create a DataLoader tuned for either a local ZIP or Kaggle directories."""
    options = {
        "dataset": dataset,
        "batch_size": batch_size,
        "shuffle": shuffle,
        "num_workers": workers,
        "pin_memory": use_cuda,
        "persistent_workers": workers > 0,
    }
    if workers > 0:
        # Each worker prepares upcoming batches while the GPU handles the current
        # one. This helps extracted Kaggle files but can hurt random ZIP access.
        options["prefetch_factor"] = 2
    return DataLoader(**options)


def parse_arguments() -> argparse.Namespace:
    """Describe every reproducible choice accepted by the training command."""
    parser = argparse.ArgumentParser(
        description="Train ColorCheck's reference-conditioned 3D LUT predictor"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dataset-zip", type=Path, help="Local FiveK ZIP archive")
    source.add_argument(
        "--dataset-root",
        type=Path,
        help="Extracted FiveK directory or Kaggle mount containing raw/a/b/c/d/e",
    )
    parser.add_argument("--output-dir", type=Path, default=Path(".local/reference-matcher"))
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument(
        "--evaluation-image-size",
        type=int,
        default=256,
        help="Higher-resolution validation/test size; does not change ONNX input size",
    )
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Use 0 for removable ZIP media and 2-4 for extracted Kaggle files",
    )
    parser.add_argument("--device", default="auto")
    parser.add_argument(
        "--mixed-precision",
        choices=("auto", "off", "fp16", "bf16"),
        default="auto",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-train-pairs", type=int, default=0)
    parser.add_argument("--max-validation-pairs", type=int, default=0)
    parser.add_argument("--max-test-pairs", type=int, default=0)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument(
        "--synthetic-probability",
        type=float,
        default=0.5,
        help="Fraction of training pairs using exact synthetic style supervision",
    )
    parser.add_argument(
        "--ranking-weight",
        type=float,
        default=0.25,
        help="Weight for correct-reference versus wrong-style ranking",
    )
    parser.add_argument(
        "--exact-lut-weight",
        type=float,
        default=1.0,
        help="Weight for exact full-cube supervision on synthetic styles",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    dataset_path = args.dataset_zip or args.dataset_root

    # Seeding all three random-number libraries makes split creation, network
    # initialization, and augmentation choices repeatable where hardware allows.
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    scenes = inspect_dataset(dataset_path)
    splits = create_splits(scenes, seed=args.seed)
    splits.save(args.output_dir / "splits.json")

    train_data = FiveKReferenceDataset(
        dataset_path,
        splits.train,
        args.image_size,
        training=True,
        seed=args.seed,
        synthetic_probability=args.synthetic_probability,
        include_lut_supervision=True,
    )
    validation_data = FiveKReferenceDataset(
        dataset_path,
        splits.validation,
        args.evaluation_image_size,
        training=False,
        seed=args.seed,
    )
    synthetic_validation_data = FiveKReferenceDataset(
        dataset_path,
        splits.validation,
        args.evaluation_image_size,
        training=False,
        seed=args.seed,
        synthetic_probability=1.0,
    )
    test_data = FiveKReferenceDataset(
        dataset_path,
        splits.test,
        args.evaluation_image_size,
        training=False,
        seed=args.seed,
    )
    synthetic_test_data = FiveKReferenceDataset(
        dataset_path,
        splits.test,
        args.evaluation_image_size,
        training=False,
        seed=args.seed,
        synthetic_probability=1.0,
    )

    # Pair limits make a real but deliberately small smoke test possible before
    # spending GPU quota on the complete 20,000-pair training split.
    if args.max_train_pairs:
        train_data = Subset(train_data, range(min(args.max_train_pairs, len(train_data))))
    if args.max_validation_pairs:
        validation_data = Subset(
            validation_data, range(min(args.max_validation_pairs, len(validation_data)))
        )
        synthetic_validation_data = Subset(
            synthetic_validation_data,
            range(min(args.max_validation_pairs, len(synthetic_validation_data))),
        )
    if args.max_test_pairs:
        test_data = Subset(test_data, range(min(args.max_test_pairs, len(test_data))))
        synthetic_test_data = Subset(
            synthetic_test_data,
            range(min(args.max_test_pairs, len(synthetic_test_data))),
        )

    device = choose_device(args.device)
    mixed_precision = choose_mixed_precision(args.mixed_precision, device)
    use_cuda = device.type == "cuda"
    train_loader = build_loader(
        train_data, args.batch_size, shuffle=True, workers=args.workers, use_cuda=use_cuda
    )
    validation_loader = build_loader(
        validation_data,
        args.batch_size,
        shuffle=False,
        workers=args.workers,
        use_cuda=use_cuda,
    )
    synthetic_validation_loader = build_loader(
        synthetic_validation_data,
        args.batch_size,
        shuffle=False,
        workers=args.workers,
        use_cuda=use_cuda,
    )
    test_loader = build_loader(
        test_data, args.batch_size, shuffle=False, workers=args.workers, use_cuda=use_cuda
    )
    synthetic_test_loader = build_loader(
        synthetic_test_data,
        args.batch_size,
        shuffle=False,
        workers=args.workers,
        use_cuda=use_cuda,
    )

    model = ReferenceLutModel().to(device)
    loss_function = ReferenceMatchLoss().to(device)
    optimizer = AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    # FP16 has a smaller numeric range, so GradScaler prevents small gradients
    # from becoming zero. BF16 and full precision do not require scaling.
    scaler = torch.amp.GradScaler(
        "cuda", enabled=(device.type == "cuda" and mixed_precision == torch.float16)
    )

    best_selection_score = float("inf")
    history = []
    starting_epoch = 1
    epochs_without_improvement = 0

    if args.resume:
        resume = torch.load(args.resume, map_location=device, weights_only=True)
        model.load_state_dict(resume["model"])
        optimizer.load_state_dict(resume["optimizer"])
        scheduler.load_state_dict(resume["scheduler"])
        if "scaler" in resume:
            scaler.load_state_dict(resume["scaler"])
        starting_epoch = resume["epoch"] + 1
        # Older checkpoints selected on real validation alone. Supporting their
        # field keeps interrupted smoke runs resumable without weakening new runs.
        best_selection_score = resume.get(
            "best_selection_score", resume.get("best_delta_e", float("inf"))
        )
        history_path = args.output_dir / "history.json"
        if history_path.exists():
            history = json.loads(history_path.read_text())

    setup = {
        "device": str(device),
        "gpu": torch.cuda.get_device_name(0) if use_cuda else None,
        "mixedPrecision": str(mixed_precision).removeprefix("torch.") if mixed_precision else "off",
        "scenes": len(scenes),
        "trainPairs": len(train_data),
        "validationPairs": len(validation_data),
        "syntheticValidationPairs": len(synthetic_validation_data),
        "testPairs": len(test_data),
        "syntheticTrainingProbability": args.synthetic_probability,
        "referenceRankingWeight": args.ranking_weight,
        "exactLutWeight": args.exact_lut_weight,
        "workers": args.workers,
        "batchSize": args.batch_size,
        "trainingImageSize": args.image_size,
        "evaluationImageSize": args.evaluation_image_size,
    }
    print(json.dumps(setup))

    for epoch in range(starting_epoch, args.epochs + 1):
        model.train()
        running_loss = 0.0
        running_ranking_loss = 0.0
        running_exact_lut_loss = 0.0
        started = time.perf_counter()
        progress = tqdm(train_loader, desc=f"epoch {epoch}/{args.epochs}")

        for batch in progress:
            source, reference, expected = move_images(batch, device)
            wrong_reference, _ = mismatch_references(reference, batch["style_id"])
            # PyTorch accumulates gradients by default. Clearing them before
            # every batch ensures each update represents only the current batch.
            optimizer.zero_grad(set_to_none=True)

            with autocast_context(device, mixed_precision):
                # Correct and wrong references share one accelerator call. The
                # second half is a training control and is absent from ONNX.
                paired_source = torch.cat((source, source), dim=0)
                paired_reference = torch.cat((reference, wrong_reference), dim=0)
                paired_lut, _ = model(paired_source, paired_reference)
                lut, wrong_lut = paired_lut.chunk(2, dim=0)
                output = apply_lut(source, lut)
                wrong_output = apply_lut(source, wrong_lut)

            loss, _ = loss_function(
                output.float(), expected.float(), source.float(), lut.float()
            )
            ranking = reference_ranking_loss(
                output.float(), wrong_output.float(), expected.float()
            )
            exact_lut = exact_lut_supervision_loss(
                lut,
                batch["expected_lut"].to(device, non_blocking=use_cuda),
                batch["has_exact_lut"].to(device, non_blocking=use_cuda),
            )
            loss = (
                loss
                + args.ranking_weight * ranking
                + args.exact_lut_weight * exact_lut
            )
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            # Gradient clipping limits rare unstable updates without changing
            # ordinary gradients below this norm.
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(optimizer)
            scaler.update()

            running_loss += loss.item() * source.shape[0]
            running_ranking_loss += ranking.item() * source.shape[0]
            running_exact_lut_loss += exact_lut.item() * source.shape[0]
            progress.set_postfix(loss=f"{loss.item():.4f}")

        scheduler.step()
        real_validation = validate(
            model,
            validation_loader,
            device,
            loss_function,
            mixed_precision=mixed_precision,
        )
        synthetic_validation = validate(
            model,
            synthetic_validation_loader,
            device,
            loss_function,
            mixed_precision=mixed_precision,
        )
        selection_score = checkpoint_selection_score(
            real_validation, synthetic_validation
        )
        record = {
            "epoch": epoch,
            "trainLoss": running_loss / len(train_data),
            "referenceRankingLoss": running_ranking_loss / len(train_data),
            "exactLutLoss": running_exact_lut_loss / len(train_data),
            "seconds": time.perf_counter() - started,
            "learningRate": scheduler.get_last_lr()[0],
            "realValidation": real_validation,
            "syntheticValidation": synthetic_validation,
            "selectionScore": selection_score,
        }
        history.append(record)
        (args.output_dir / "history.json").write_text(json.dumps(history, indent=2) + "\n")

        checkpoint = {
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "scaler": scaler.state_dict(),
            "epoch": epoch,
            "best_selection_score": min(best_selection_score, selection_score),
            "config": {
                "basis_count": model.basis_count,
                "lut_size": model.lut_size,
                "image_size": args.image_size,
                "seed": args.seed,
                "synthetic_probability": args.synthetic_probability,
                "ranking_weight": args.ranking_weight,
                "exact_lut_weight": args.exact_lut_weight,
            },
            # validation remains an alias for compatibility with the ONNX
            # manifest and earlier experiment readers.
            "validation": real_validation,
            "synthetic_validation": synthetic_validation,
            "selection_score": selection_score,
        }
        # ``last.pt`` supports recovery from interruption. ``best.pt`` remains
        # fixed at the strongest validation result even if later epochs regress.
        torch.save(checkpoint, args.output_dir / "last.pt")
        if selection_score < best_selection_score:
            best_selection_score = selection_score
            epochs_without_improvement = 0
            torch.save(checkpoint, args.output_dir / "best.pt")
        else:
            epochs_without_improvement += 1

        print(json.dumps(record))
        if epochs_without_improvement >= args.patience:
            print(f"Early stopping after {args.patience} validation epochs without improvement")
            break

    # Final testing happens exactly once with the strongest validation checkpoint.
    # Test scores therefore cannot influence which checkpoint is selected.
    best_checkpoint = torch.load(args.output_dir / "best.pt", map_location=device, weights_only=True)
    model.load_state_dict(best_checkpoint["model"])
    test_metrics = validate(
        model, test_loader, device, loss_function, mixed_precision=mixed_precision
    )
    shuffle_metrics = validate(
        model,
        test_loader,
        device,
        loss_function,
        mixed_precision=mixed_precision,
        shuffled_reference=True,
    )
    baseline_metrics = identity_baseline(test_loader, device)
    real_evaluation = comprehensive_evaluation(
        model, test_loader, device, mixed_precision, seed=args.seed
    )
    synthetic_evaluation = comprehensive_evaluation(
        model, synthetic_test_loader, device, mixed_precision, seed=args.seed + 1
    )
    summary = {
        "bestEpoch": best_checkpoint["epoch"],
        "bestValidation": best_checkpoint["validation"],
        "bestSyntheticValidation": best_checkpoint["synthetic_validation"],
        "bestSelectionScore": best_checkpoint["selection_score"],
        "test": test_metrics,
        "testWithShuffledReferences": shuffle_metrics,
        "identityTestBaseline": baseline_metrics,
        "realExpertEvaluation": real_evaluation,
        "syntheticReferenceEvaluation": synthetic_evaluation,
        "allDeploymentEvidenceGatesPass": (
            real_evaluation["allEvidenceGatesPass"]
            and synthetic_evaluation["allEvidenceGatesPass"]
        ),
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
