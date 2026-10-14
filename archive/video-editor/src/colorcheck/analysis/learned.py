"""Opt-in bounded correction inference; deliberately independent of PyTorch."""

from __future__ import annotations

import json
import logging
import os
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from colorcheck.analysis.correction import LIMITS, clamp
from colorcheck.models import CorrectionPlan, LightingProfile

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 1
PROFILE_FIELDS = (
    "luma_mean", "luma_std", "saturation_mean", "temperature_proxy",
    "red_mean", "green_mean", "blue_mean", "red_std", "green_std", "blue_std",
)
FEATURE_NAMES = tuple(
    f"{prefix}_{field}"
    for prefix in ("reference", "target", "delta")
    for field in PROFILE_FIELDS
) + tuple(f"log_ratio_{field}" for field in (*PROFILE_FIELDS[:3], *PROFILE_FIELDS[4:7]))
PARAMETER_NAMES = ("exposure", "contrast", "saturation", "red_balance", "blue_balance")
PARAMETER_SCALES = np.array([0.35, 0.15, 0.15, 0.08, 0.08], dtype=np.float32)
HIDDEN_SIZE = 64
MAX_ARTIFACT_BYTES = 1_000_000


def profile_values(profile: LightingProfile) -> np.ndarray:
    return np.array([
        profile.luma_mean, profile.luma_std, profile.saturation_mean,
        profile.temperature_proxy, *profile.rgb_mean, *profile.rgb_std,
    ], dtype=np.float32)


def feature_vector(reference: LightingProfile, target: LightingProfile) -> np.ndarray:
    ref, tgt = profile_values(reference), profile_values(target)
    indices = [0, 1, 2, 4, 5, 6]
    ratios = np.log(np.maximum(ref[indices], 0.01) / np.maximum(tgt[indices], 0.01))
    return np.concatenate([ref, tgt, ref - tgt, ratios]).astype(np.float32)


def parameters_to_plan(parameters: np.ndarray, baseline: CorrectionPlan) -> CorrectionPlan:
    values = np.asarray(parameters, dtype=np.float32)
    if values.shape != (5,) or not np.isfinite(values).all():
        raise ValueError("Invalid learned correction parameters.")
    values = np.clip(values, -1.0, 1.0)
    exposure, contrast, saturation, red, blue = values * PARAMETER_SCALES
    return CorrectionPlan(
        exposure_stops=clamp(float(exposure), -0.35, 0.35),
        contrast_multiplier=clamp(1.0 + float(contrast), 0.85, 1.15),
        saturation_multiplier=clamp(1.0 + float(saturation), 0.85, 1.15),
        channel_gains=(clamp(1.0 + float(red), 0.92, 1.08), 1.0,
                       clamp(1.0 + float(blue), 0.92, 1.08)),
        lift_offset=(0.0, 0.0, 0.0),
        confidence=baseline.confidence,
        rationale=[
            "Experimental learned global correction, trained on synthetic photographic pairs.",
            "Confidence is the existing heuristic, not a calibrated model probability.",
            "Existing correction bounds and clipping checks remain in effect.",
        ],
    )


@dataclass(frozen=True)
class CorrectionRegressor:
    arrays: dict[str, np.ndarray]
    metadata: dict

    def predict(self, features: np.ndarray, *, check_domain: bool = True) -> np.ndarray | None:
        features = np.asarray(features, dtype=np.float32)
        if features.shape != (len(FEATURE_NAMES),) or not np.isfinite(features).all():
            return None
        arrays = self.arrays
        if check_domain:
            margin = np.maximum(arrays["feature_max"] - arrays["feature_min"], 0.02) * 0.25
            if np.any(features < arrays["feature_min"] - margin) or np.any(
                features > arrays["feature_max"] + margin
            ):
                return None
        data = (features - arrays["feature_mean"]) / arrays["feature_scale"]
        data = np.maximum(arrays["weight_0"] @ data + arrays["bias_0"], 0.0)
        data = np.maximum(arrays["weight_1"] @ data + arrays["bias_1"], 0.0)
        output = np.tanh(arrays["weight_2"] @ data + arrays["bias_2"])
        return output if np.isfinite(output).all() else None


def load_regressor(path: str | Path) -> CorrectionRegressor:
    path = Path(path)
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError("Correction artifact exceeds the size limit.")
    with zipfile.ZipFile(path) as archive:
        if sum(item.file_size for item in archive.infolist()) > MAX_ARTIFACT_BYTES:
            raise ValueError("Expanded correction artifact exceeds the size limit.")
    size = len(FEATURE_NAMES)
    shapes = {
        "feature_mean": (size,), "feature_scale": (size,),
        "feature_min": (size,), "feature_max": (size,),
        "weight_0": (HIDDEN_SIZE, size), "bias_0": (HIDDEN_SIZE,),
        "weight_1": (HIDDEN_SIZE, HIDDEN_SIZE), "bias_1": (HIDDEN_SIZE,),
        "weight_2": (5, HIDDEN_SIZE), "bias_2": (5,),
    }
    with np.load(path, allow_pickle=False) as artifact:
        if set(artifact.files) != {*shapes, "metadata"}:
            raise ValueError("Unexpected correction artifact contents.")
        encoded = artifact["metadata"]
        if encoded.ndim != 1 or encoded.dtype != np.uint8 or encoded.size > 64_000:
            raise ValueError("Invalid correction metadata.")
        metadata = json.loads(encoded.tobytes().decode("utf-8"))
        if not isinstance(metadata, dict) or metadata.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported correction schema.")
        if metadata.get("features") != list(FEATURE_NAMES):
            raise ValueError("Correction feature schema does not match.")
        if metadata.get("parameters") != list(PARAMETER_NAMES) or metadata.get("limits") != LIMITS:
            raise ValueError("Correction bounds do not match.")
        arrays = {}
        for name, shape in shapes.items():
            value = artifact[name]
            if value.shape != shape or value.dtype != np.float32 or not np.isfinite(value).all():
                raise ValueError(f"Invalid correction tensor: {name}.")
            arrays[name] = value.copy()
    if np.any(arrays["feature_scale"] < 1e-5) or np.any(
        arrays["feature_min"] > arrays["feature_max"]
    ):
        raise ValueError("Invalid correction normalization.")
    return CorrectionRegressor(arrays, metadata)


@lru_cache(maxsize=2)
def _cached_regressor(path: str, modified_ns: int, size: int) -> CorrectionRegressor | None:
    try:
        return load_regressor(path)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        LOGGER.warning("Experimental correction model is unavailable; using rule-based correction.")
        return None


def experimental_correction(
    reference: LightingProfile,
    target: LightingProfile,
    baseline: CorrectionPlan,
) -> CorrectionPlan | None:
    path_string = os.environ.get("VCC_CORRECTION_MODEL", "")
    if not path_string or os.environ.get("VCC_ENABLE_EXPERIMENTAL_MODEL") != "1":
        return None
    try:
        path = Path(path_string).resolve()
        stat = path.stat()
    except OSError:
        return None
    model = _cached_regressor(str(path), stat.st_mtime_ns, stat.st_size)
    if model is None or model.metadata.get("synthetic_gate_passed") is not True:
        return None
    if min(reference.luma_std, target.luma_std) < 0.01:
        return None
    parameters = model.predict(feature_vector(reference, target))
    if parameters is None:
        return None
    if np.max(np.abs(profile_values(reference) - profile_values(target))) < 1e-5:
        parameters = np.zeros(5, dtype=np.float32)
    return parameters_to_plan(parameters, baseline)
