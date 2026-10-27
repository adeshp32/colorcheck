"""NumPy-only mirror of ColorCheck's browser matcher and pilot label search."""

from __future__ import annotations

import numpy as np

BASELINE = np.array([0.65, 0.45], dtype=np.float64)
STRENGTHS = (0.0, 0.15, 0.3, 0.45, 0.6, 0.65, 0.75, 0.9, 1.0)
FEATURE_NAMES = tuple(
    [f"source_mean_{channel}" for channel in "rgb"]
    + [f"reference_mean_{channel}" for channel in "rgb"]
    + [f"source_std_{channel}" for channel in "rgb"]
    + [f"reference_std_{channel}" for channel in "rgb"]
    + [f"mean_shift_{channel}" for channel in "rgb"]
    + [f"std_shift_{channel}" for channel in "rgb"]
)


def features(source: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Match web/src/adaptive-reference-match.js exactly in feature order."""
    source_mean = source.mean(axis=(1, 2))
    reference_mean = reference.mean(axis=(1, 2))
    source_std = source.std(axis=(1, 2))
    reference_std = reference.std(axis=(1, 2))
    return np.concatenate((
        source_mean, reference_mean, source_std, reference_std,
        reference_mean - source_mean, reference_std - source_std,
    )).astype(np.float64)


def match(source: np.ndarray, reference: np.ndarray, strengths: np.ndarray) -> np.ndarray:
    """Reproduce the site's bounded mean/spread transfer before manual edits."""
    source_mean = source.mean(axis=(1, 2))[:, None, None]
    reference_mean = reference.mean(axis=(1, 2))[:, None, None]
    source_std = source.std(axis=(1, 2))
    reference_std = reference.std(axis=(1, 2))
    gain = np.clip(reference_std / np.maximum(source_std, 0.015), 0.65, 1.5)[:, None, None]
    proposed = (source + (reference_mean - source_mean) * strengths[0]
                + (source - source_mean) * (gain - 1) * strengths[1])
    return np.clip(proposed, 0, 1)


def clipping(image: np.ndarray) -> float:
    return float(np.mean(np.any((image <= 1 / 255) | (image >= 254 / 255), axis=0)))


def training_label(source: np.ndarray, reference: np.ndarray, expert: np.ndarray) -> np.ndarray:
    """Find the best existing-control settings, with a mild clipping penalty."""
    best_score = float("inf")
    best = BASELINE
    original_clipping = clipping(source)
    for palette in STRENGTHS:
        for tone in STRENGTHS:
            strengths = np.array([palette, tone])
            result = match(source, reference, strengths)
            score = (float(np.mean(np.abs(result - expert)))
                     + 0.03 * max(0, clipping(result) - original_clipping)
                     + 0.003 * float(np.sum(np.abs(strengths - BASELINE))))
            if score < best_score:
                best_score, best = score, strengths
    return best


def gain_interval(values: np.ndarray, seed: int = 917) -> list[float]:
    generator = np.random.default_rng(seed)
    samples = values[generator.integers(0, len(values), size=(2000, len(values)))].mean(axis=1)
    return [float(value) for value in np.percentile(samples, (2.5, 97.5))]
