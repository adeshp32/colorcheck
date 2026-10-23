"""Held-out evaluation for reference-conditioned photographic matching.

Training loss answers whether gradient descent can improve the model. This
module answers the harder product question: does the trained model improve an
unseen photograph, use the supplied reference, preserve structure, and remain
small and fast enough for an interactive browser editor?

Every metric is retained per photograph before aggregation. Confidence intervals
resample source scenes, not individual expert variants or pixels, because the five
edits of one FiveK photograph are related observations rather than five independent
photographs.
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import torch
import torch.nn.functional as F

from .dataset import EXPERTS
from .losses import image_gradients, rgb_to_lab

# These thresholds are declared in source before full training. They prevent a
# large evaluation set from promoting a statistically positive but visually tiny
# result. Confidence intervals must still exclude zero independently.
MINIMUM_PRACTICAL_EFFECTS = {
    "identityDeltaE2000": 0.25,
    "identitySsim": 0.002,
    "statisticsDeltaE2000": 0.10,
    "correctReferenceDeltaE2000": 0.05,
    "referenceSensitivityMae": 1 / 1024,
}


def _per_image_mean(values: torch.Tensor) -> torch.Tensor:
    """Average every dimension except the leading batch dimension."""
    return values.flatten(1).mean(1)


def _luminance(image: torch.Tensor) -> torch.Tensor:
    """Convert sRGB channels to a one-channel Rec. 709 luminance estimate."""
    weights = image.new_tensor([0.2126, 0.7152, 0.0722])[None, :, None, None]
    return (image * weights).sum(1, keepdim=True)


def ciede2000(lab_a: torch.Tensor, lab_b: torch.Tensor) -> torch.Tensor:
    """Return the CIEDE2000 color difference for corresponding Lab pixels.

    CIEDE2000 accounts for nonuniform sensitivity to lightness, chroma, and hue.
    It is used only as an evaluation metric: the smoother Delta E 76 objective
    remains preferable for backpropagation.
    """
    l1, a1, b1 = lab_a.unbind(1)
    l2, a2, b2 = lab_b.unbind(1)
    c1 = torch.sqrt(a1.square() + b1.square() + 1e-12)
    c2 = torch.sqrt(a2.square() + b2.square() + 1e-12)
    mean_c = (c1 + c2) / 2
    mean_c7 = mean_c.pow(7)
    g = 0.5 * (1 - torch.sqrt(mean_c7 / (mean_c7 + 25**7)))
    a1_prime = (1 + g) * a1
    a2_prime = (1 + g) * a2
    c1_prime = torch.sqrt(a1_prime.square() + b1.square() + 1e-12)
    c2_prime = torch.sqrt(a2_prime.square() + b2.square() + 1e-12)
    h1_prime = torch.rad2deg(torch.atan2(b1, a1_prime)).remainder(360)
    h2_prime = torch.rad2deg(torch.atan2(b2, a2_prime)).remainder(360)

    delta_l = l2 - l1
    delta_c = c2_prime - c1_prime
    delta_h_degrees = h2_prime - h1_prime
    delta_h_degrees = torch.where(
        delta_h_degrees > 180, delta_h_degrees - 360, delta_h_degrees
    )
    delta_h_degrees = torch.where(
        delta_h_degrees < -180, delta_h_degrees + 360, delta_h_degrees
    )
    delta_h_degrees = torch.where(
        (c1_prime * c2_prime) == 0, torch.zeros_like(delta_h_degrees), delta_h_degrees
    )
    delta_h = (
        2
        * torch.sqrt(c1_prime * c2_prime)
        * torch.sin(torch.deg2rad(delta_h_degrees) / 2)
    )

    mean_l = (l1 + l2) / 2
    mean_c_prime = (c1_prime + c2_prime) / 2
    hue_distance = (h1_prime - h2_prime).abs()
    mean_h = (h1_prime + h2_prime) / 2
    mean_h = torch.where(hue_distance > 180, mean_h + 180, mean_h).remainder(360)
    mean_h = torch.where((c1_prime * c2_prime) == 0, h1_prime + h2_prime, mean_h)
    t = (
        1
        - 0.17 * torch.cos(torch.deg2rad(mean_h - 30))
        + 0.24 * torch.cos(torch.deg2rad(2 * mean_h))
        + 0.32 * torch.cos(torch.deg2rad(3 * mean_h + 6))
        - 0.20 * torch.cos(torch.deg2rad(4 * mean_h - 63))
    )
    delta_theta = 30 * torch.exp(-((mean_h - 275) / 25).square())
    r_c = 2 * torch.sqrt(mean_c_prime.pow(7) / (mean_c_prime.pow(7) + 25**7))
    s_l = 1 + (0.015 * (mean_l - 50).square()) / torch.sqrt(20 + (mean_l - 50).square())
    s_c = 1 + 0.045 * mean_c_prime
    s_h = 1 + 0.015 * mean_c_prime * t
    r_t = -torch.sin(torch.deg2rad(2 * delta_theta)) * r_c
    lightness = delta_l / s_l
    chroma = delta_c / s_c
    hue = delta_h / s_h
    return torch.sqrt(
        (
            lightness.square() + chroma.square() + hue.square() + r_t * chroma * hue
        ).clamp_min(0)
        + 1e-12
    )


def _ssim_per_image(output: torch.Tensor, expected: torch.Tensor) -> torch.Tensor:
    """Measure local luminance, contrast, and structure similarity."""
    x, y = _luminance(output), _luminance(expected)
    kernel = min(11, x.shape[-2], x.shape[-1])
    if kernel % 2 == 0:
        kernel -= 1
    padding = kernel // 2
    mean_x = F.avg_pool2d(x, kernel, stride=1, padding=padding)
    mean_y = F.avg_pool2d(y, kernel, stride=1, padding=padding)
    variance_x = F.avg_pool2d(x.square(), kernel, 1, padding) - mean_x.square()
    variance_y = F.avg_pool2d(y.square(), kernel, 1, padding) - mean_y.square()
    covariance = F.avg_pool2d(x * y, kernel, 1, padding) - mean_x * mean_y
    c1, c2 = 0.01**2, 0.03**2
    score = ((2 * mean_x * mean_y + c1) * (2 * covariance + c2)) / (
        (mean_x.square() + mean_y.square() + c1) * (variance_x + variance_y + c2)
    )
    return _per_image_mean(score)


def metric_samples(
    output: torch.Tensor, expected: torch.Tensor
) -> dict[str, torch.Tensor]:
    """Calculate one value per photograph for each complementary quality axis."""
    output, expected = output.float(), expected.float()
    error = output - expected
    mse = _per_image_mean(error.square())
    lab_output, lab_expected = rgb_to_lab(output), rgb_to_lab(expected)
    output_x, output_y = image_gradients(output)
    expected_x, expected_y = image_gradients(expected)
    edge_error = (
        _per_image_mean((output_x - expected_x).abs())
        + _per_image_mean((output_y - expected_y).abs())
    ) / 2
    chroma_output = torch.sqrt(lab_output[:, 1].square() + lab_output[:, 2].square())
    chroma_expected = torch.sqrt(
        lab_expected[:, 1].square() + lab_expected[:, 2].square()
    )
    return {
        "mae": _per_image_mean(error.abs()),
        "psnrDb": -10 * torch.log10(mse.clamp_min(1e-10)),
        "ssim": _ssim_per_image(output, expected),
        "deltaE2000": _per_image_mean(ciede2000(lab_output, lab_expected)),
        "luminanceMae": _per_image_mean(
            (_luminance(output) - _luminance(expected)).abs()
        ),
        "chromaMae": _per_image_mean((chroma_output - chroma_expected).abs()),
        "edgeMae": edge_error,
        "clippingPercent": _per_image_mean(
            ((output <= 1 / 255) | (output >= 254 / 255))
            .any(dim=1, keepdim=True)
            .float()
        )
        * 100,
    }


def statistics_match(source: torch.Tensor, reference: torch.Tensor) -> torch.Tensor:
    """Apply the editor's bounded per-channel mean/spread reference baseline."""
    source_mean = source.mean((2, 3), keepdim=True)
    source_std = source.std((2, 3), correction=0, keepdim=True)
    reference_mean = reference.mean((2, 3), keepdim=True)
    reference_std = reference.std((2, 3), correction=0, keepdim=True)
    gain = (reference_std / source_std.clamp_min(0.015)).clamp(0.65, 1.5)
    return ((source - source_mean) * gain + reference_mean).clamp(0, 1)


def mismatch_references(
    reference: torch.Tensor, style_labels
) -> tuple[torch.Tensor, torch.Tensor]:
    """Pair each item with a reference carrying a different style label.

    Rolling a batch can accidentally compare two references from the same FiveK
    expert. That is not a meaningful wrong-style control. This deterministic
    mapping searches forward for a different expert and returns the selected
    indices so the evaluation remains auditable.
    """
    count = reference.shape[0]
    indices = torch.arange(count, device=reference.device)
    if count < 2:
        return reference, indices
    if isinstance(style_labels, torch.Tensor):
        label_values = style_labels.detach().cpu().tolist()
    else:
        label_values = list(style_labels)
    if len(label_values) != count:
        raise ValueError("One style label is required for every reference")
    selected = []
    for index in range(count):
        candidate = next(
            (
                (index + offset) % count
                for offset in range(1, count)
                if label_values[(index + offset) % count] != label_values[index]
            ),
            index,
        )
        selected.append(candidate)
    indices = torch.tensor(selected, device=reference.device)
    return reference.index_select(0, indices), indices


def _bootstrap(values: np.ndarray, seed: int, samples: int = 1000) -> dict[str, float]:
    """Estimate a photograph-level 95% confidence interval for a mean."""
    values = np.asarray(values, dtype=np.float64)
    if not len(values):
        raise ValueError("Cannot summarize an empty metric")
    if len(values) == 1:
        lower = upper = float(values[0])
    else:
        generator = np.random.default_rng(seed)
        indices = generator.integers(0, len(values), size=(samples, len(values)))
        means = values[indices].mean(1)
        lower, upper = np.percentile(means, [2.5, 97.5])
    return {
        "mean": float(values.mean()),
        "ci95Lower": float(lower),
        "ci95Upper": float(upper),
        "sampleCount": int(len(values)),
    }


def _cluster_bootstrap(
    values: np.ndarray, scene_ids, seed: int, samples: int = 1000
) -> dict[str, float]:
    """Bootstrap scene means so repeated expert edits do not inflate certainty.

    FiveK contains five expert variants of each source scene. Averaging those
    variants within a scene and then resampling scenes gives each photograph one
    independent vote while retaining every expert measurement in its scene mean.
    """
    values = np.asarray(values, dtype=np.float64)
    scenes = np.asarray(scene_ids, dtype=object)
    if len(values) != len(scenes):
        raise ValueError("One source scene identifier is required per metric value")
    unique_scenes = tuple(dict.fromkeys(scenes.tolist()))
    scene_means = np.asarray(
        [values[scenes == scene].mean() for scene in unique_scenes], dtype=np.float64
    )
    result = _bootstrap(scene_means, seed, samples)
    result["sceneCount"] = result.pop("sampleCount")
    result["observationCount"] = int(len(values))
    return result


class MetricStore:
    """Collect per-image measurements while retaining expert identities."""

    def __init__(self) -> None:
        self.values: dict[str, list[float]] = defaultdict(list)
        self.experts: list[int] = []
        self.scenes: list[str] = []

    def add(
        self, metrics: dict[str, torch.Tensor], experts: torch.Tensor, scenes
    ) -> None:
        scene_values = list(scenes)
        batch_size = len(experts)
        if len(scene_values) != batch_size:
            raise ValueError("One source scene identifier is required per photograph")
        for name, values in metrics.items():
            if len(values) != batch_size:
                raise ValueError("Every metric must contain one value per photograph")
            self.values[name].extend(values.detach().cpu().tolist())
        self.experts.extend(experts.detach().cpu().tolist())
        self.scenes.extend(scene_values)

    def summary(self, seed: int = 42) -> dict:
        overall = {
            name: _cluster_bootstrap(np.asarray(values), self.scenes, seed + index)
            for index, (name, values) in enumerate(sorted(self.values.items()))
        }
        expert_array = np.asarray(self.experts)
        scene_array = np.asarray(self.scenes, dtype=object)
        by_expert = {}
        for expert_index, expert_name in enumerate(EXPERTS):
            selected = expert_array == expert_index
            if selected.any():
                by_expert[expert_name.upper()] = {
                    name: _cluster_bootstrap(
                        np.asarray(values)[selected],
                        scene_array[selected],
                        seed + expert_index,
                    )
                    for name, values in sorted(self.values.items())
                }
        return {"overall": overall, "byExpert": by_expert}


def paired_improvement(
    model: MetricStore, baseline: MetricStore, seed: int = 42
) -> dict[str, dict[str, float]]:
    """Report positive values when the model improves over a paired baseline."""
    higher_is_better = {"psnrDb", "ssim"}
    if model.scenes != baseline.scenes:
        raise ValueError("Paired comparisons require metrics in the same scene order")
    comparisons = {}
    for index, name in enumerate(sorted(model.values)):
        model_values = np.asarray(model.values[name])
        baseline_values = np.asarray(baseline.values[name])
        difference = (
            model_values - baseline_values
            if name in higher_is_better
            else baseline_values - model_values
        )
        comparisons[name] = _cluster_bootstrap(difference, model.scenes, seed + index)
    return comparisons


def coefficient_diagnostics(coefficients: torch.Tensor) -> dict[str, object]:
    """Detect a collapsed mixture that ignores most learned LUT bases."""
    coefficients = coefficients.float()
    entropy = -(coefficients * coefficients.clamp_min(1e-8).log()).sum(1)
    entropy /= math.log(coefficients.shape[1])
    dominant_counts = torch.bincount(
        coefficients.argmax(1), minlength=coefficients.shape[1]
    )
    return {
        "normalizedEntropyMean": float(entropy.mean()),
        "normalizedEntropyMinimum": float(entropy.min()),
        "meanBasisWeights": coefficients.mean(0).tolist(),
        "basisWeightStandardDeviations": coefficients.std(0, correction=0).tolist(),
        "dominantBasisCounts": dominant_counts.tolist(),
        "dominantBasisFraction": float(dominant_counts.max() / coefficients.shape[0]),
    }


def deployment_evidence_gates(
    identity_gain: dict,
    statistics_gain: dict,
    wrong_reference_gain: dict,
    reference_sensitivity_mean: float,
    coefficient_report: dict,
) -> dict[str, bool]:
    """Require statistical confidence, practical effect, and model diversity."""
    minimum = MINIMUM_PRACTICAL_EFFECTS
    return {
        "beatsIdentityDeltaE2000": (
            identity_gain["deltaE2000"]["ci95Lower"] > 0
            and identity_gain["deltaE2000"]["mean"] >= minimum["identityDeltaE2000"]
        ),
        "beatsIdentitySsim": (
            identity_gain["ssim"]["ci95Lower"] > 0
            and identity_gain["ssim"]["mean"] >= minimum["identitySsim"]
        ),
        "beatsStatisticsDeltaE2000": (
            statistics_gain["deltaE2000"]["ci95Lower"] > 0
            and statistics_gain["deltaE2000"]["mean"] >= minimum["statisticsDeltaE2000"]
        ),
        "correctReferenceBeatsShuffledDeltaE2000": (
            wrong_reference_gain["deltaE2000"]["ci95Lower"] > 0
            and wrong_reference_gain["deltaE2000"]["mean"]
            >= minimum["correctReferenceDeltaE2000"]
        ),
        "respondsToReference": (
            reference_sensitivity_mean >= minimum["referenceSensitivityMae"]
        ),
        "avoidsSingleBasisCollapse": (
            max(coefficient_report["meanBasisWeights"]) < 0.9
            and coefficient_report["dominantBasisFraction"] < 0.9
        ),
        "doesNotIncreaseClippingVsIdentity": (
            identity_gain["clippingPercent"]["ci95Lower"] >= 0
        ),
    }
