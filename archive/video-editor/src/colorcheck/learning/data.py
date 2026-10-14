from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from colorcheck.analysis.correction import apply_correction_array, recommend_correction
from colorcheck.analysis.learned import feature_vector, parameters_to_plan
from colorcheck.analysis.metrics import load_image_rgb, profile_image, resize_for_analysis
from colorcheck.models import CorrectionPlan

IDENTITY = CorrectionPlan(0.0, 1.0, 1.0, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0), 0.0, [])


@dataclass(frozen=True)
class SourceImage:
    image_id: str
    path: Path
    group: str
    sha256: str


def read_manifest(path: str | Path) -> list[SourceImage]:
    path = Path(path).resolve()
    document = json.loads(path.read_text())
    if document.get("schema_version") != 1:
        raise ValueError("Unsupported image manifest.")
    sources = []
    hashes: set[str] = set()
    ids: set[str] = set()
    for row in document["images"]:
        image_path = (path.parent / row["path"]).resolve()
        if not image_path.is_relative_to(path.parent) or not image_path.is_file():
            raise ValueError("Training image must be inside the dataset directory.")
        digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
        if digest != row["sha256"]:
            raise ValueError("Training image checksum mismatch.")
        if digest in hashes or row["image_id"] in ids:
            raise ValueError("Duplicate training image.")
        if not row.get("group") or not row.get("license_url") or not row.get("source_url"):
            raise ValueError("Source, license and scene/author group are required.")
        hashes.add(digest)
        ids.add(row["image_id"])
        sources.append(SourceImage(row["image_id"], image_path, row["group"], digest))
    return sources


def split_sources(sources: list[SourceImage], seed: int) -> dict[str, list[SourceImage]]:
    groups = sorted({source.group for source in sources})
    if len(groups) < 10:
        raise ValueError("At least 10 independent scene/author groups are required.")
    rng = np.random.default_rng(seed)
    rng.shuffle(groups)
    validation_count = max(2, round(len(groups) * 0.15))
    test_count = max(2, round(len(groups) * 0.15))
    assignment = {
        group: "validation" if index < validation_count else (
            "test" if index < validation_count + test_count else "train"
        ) for index, group in enumerate(groups)
    }
    result = {name: [] for name in ("train", "validation", "test")}
    for source in sorted(sources, key=lambda item: item.image_id):
        result[assignment[source.group]].append(source)
    return result


def inverse_target(reference: np.ndarray, parameters: np.ndarray) -> np.ndarray:
    plan = parameters_to_plan(parameters, IDENTITY)
    luma = (reference * np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)).sum(axis=2)
    data = luma[:, :, None] + (reference - luma[:, :, None]) / plan.saturation_multiplier
    data = (data - 0.5) / plan.contrast_multiplier + 0.5
    data /= (2.0 ** plan.exposure_stops) * np.array(plan.channel_gains, dtype=np.float32)
    return np.clip(data, 0.0, 1.0)


@dataclass(frozen=True)
class Examples:
    features: np.ndarray
    parameters: np.ndarray
    target_pixels: np.ndarray
    reference_pixels: np.ndarray
    baseline_pixels: np.ndarray
    image_ids: tuple[str, ...]
    groups: tuple[str, ...]


def build_examples(sources: list[SourceImage], variants: int, seed: int) -> Examples:
    features, labels, targets, references, baselines, ids, groups = [], [], [], [], [], [], []
    for source in sources:
        image_seed = int(hashlib.sha256(f"{seed}:{source.image_id}".encode()).hexdigest()[:16], 16)
        rng = np.random.default_rng(image_seed)
        rgb = resize_for_analysis(load_image_rgb(source.path), max_side=192)
        reference = rgb.astype(np.float32) / 255.0
        reference_profile = profile_image(rgb)
        indices = rng.choice(reference.shape[0] * reference.shape[1], size=256, replace=True)
        for variant in range(variants):
            parameters = rng.uniform(-0.85, 0.85, 5).astype(np.float32)
            if variant % 8 == 0:
                parameters[:] = 0.0
            target = inverse_target(reference, parameters)
            target_rgb = np.round(target * 255).astype(np.uint8)
            target = target_rgb.astype(np.float32) / 255.0
            target_profile = profile_image(target_rgb)
            baseline = recommend_correction(reference_profile, target_profile, [])
            features.append(feature_vector(reference_profile, target_profile))
            labels.append(parameters)
            targets.append(target.reshape(-1, 3)[indices])
            references.append(reference.reshape(-1, 3)[indices])
            baselines.append(apply_correction_array(target, baseline).reshape(-1, 3)[indices])
            ids.append(source.image_id)
            groups.append(source.group)
    return Examples(
        *(np.asarray(values, dtype=np.float32) for values in (
            features, labels, targets, references, baselines,
        )), tuple(ids), tuple(groups),
    )


def lab_error(predicted: np.ndarray, expected: np.ndarray) -> np.ndarray:
    pred_lab = cv2.cvtColor(predicted.astype(np.float32), cv2.COLOR_RGB2LAB)
    ref_lab = cv2.cvtColor(expected.astype(np.float32), cv2.COLOR_RGB2LAB)
    return np.linalg.norm(pred_lab - ref_lab, axis=-1).mean(axis=1)
