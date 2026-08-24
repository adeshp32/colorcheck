from __future__ import annotations

import math

import numpy as np

from video_color_checker.models import (
    CorrectionPlan,
    FrameAnalysis,
    GuardrailResult,
    LightingProfile,
    LightingShiftResult,
)

LIMITS = {
    "max_abs_exposure_stops": 0.35,
    "min_contrast_multiplier": 0.85,
    "max_contrast_multiplier": 1.15,
    "min_saturation_multiplier": 0.85,
    "max_saturation_multiplier": 1.15,
    "min_channel_gain": 0.92,
    "max_channel_gain": 1.08,
    "max_clipping_risk_percent": 1.5,
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def clamp_percent(value: float, low: int = 0, high: int = 100) -> int:
    return round(clamp(float(value), float(low), float(high)))


def aggregate_profile(frames: list[FrameAnalysis]) -> LightingProfile:
    if not frames:
        raise ValueError("Cannot aggregate an empty frame list.")

    def median_attr(attr: str) -> float:
        return float(np.median([getattr(frame.target_profile, attr) for frame in frames]))

    rgb_mean = tuple(
        float(np.median([frame.target_profile.rgb_mean[channel] for frame in frames]))
        for channel in range(3)
    )
    rgb_std = tuple(
        float(np.median([frame.target_profile.rgb_std[channel] for frame in frames]))
        for channel in range(3)
    )
    from video_color_checker.image_metrics import nearest_lighting_archetype

    label, distance = nearest_lighting_archetype(
        median_attr("luma_mean"),
        median_attr("luma_std"),
        median_attr("saturation_mean"),
        median_attr("temperature_proxy"),
    )
    return LightingProfile(
        luma_mean=median_attr("luma_mean"),
        luma_std=median_attr("luma_std"),
        saturation_mean=median_attr("saturation_mean"),
        temperature_proxy=median_attr("temperature_proxy"),
        rgb_mean=rgb_mean,
        rgb_std=rgb_std,
        lighting_label=label,
        lighting_distance=distance,
    )


def recommend_correction(
    reference: LightingProfile,
    target: LightingProfile,
    frames: list[FrameAnalysis],
) -> CorrectionPlan:
    exposure_raw = math.log2(max(reference.luma_mean, 0.03) / max(target.luma_mean, 0.03))
    exposure_stops = clamp(
        exposure_raw,
        -LIMITS["max_abs_exposure_stops"],
        LIMITS["max_abs_exposure_stops"],
    )

    contrast_raw = reference.luma_std / max(target.luma_std, 0.03)
    contrast = clamp(
        contrast_raw,
        LIMITS["min_contrast_multiplier"],
        LIMITS["max_contrast_multiplier"],
    )

    saturation_raw = reference.saturation_mean / max(target.saturation_mean, 0.03)
    saturation = clamp(
        saturation_raw,
        LIMITS["min_saturation_multiplier"],
        LIMITS["max_saturation_multiplier"],
    )

    gains: list[float] = []
    for ref_channel, target_channel in zip(reference.rgb_mean, target.rgb_mean, strict=True):
        gains.append(
            clamp(
                ref_channel / max(target_channel, 0.03),
                LIMITS["min_channel_gain"],
                LIMITS["max_channel_gain"],
            )
        )

    median_score = float(np.median([frame.match_score for frame in frames])) if frames else 0.0
    confidence = clamp((100.0 - median_score) / 45.0, 0.15, 0.95)
    if median_score >= 90.0:
        confidence = 0.2

    rationale = [
        f"Reference lighting classified as {reference.lighting_label}.",
        f"Target video median lighting classified as {target.lighting_label}.",
        "Values were clamped to conservative guardrails before export.",
    ]
    if abs(exposure_raw) > LIMITS["max_abs_exposure_stops"]:
        rationale.append("Exposure drift exceeded the limit, so the recommendation was capped.")
    if saturation_raw != saturation:
        rationale.append("Saturation correction was capped to avoid an artificial-looking grade.")
    if contrast_raw != contrast:
        rationale.append("Contrast correction was capped to preserve shadow/highlight detail.")

    return CorrectionPlan(
        exposure_stops=round(exposure_stops, 4),
        contrast_multiplier=round(contrast, 4),
        saturation_multiplier=round(saturation, 4),
        channel_gains=tuple(round(v, 4) for v in gains),
        lift_offset=(0.0, 0.0, 0.0),
        confidence=round(confidence, 3),
        rationale=rationale,
    )


def scale_correction(correction: CorrectionPlan, strength_percent: float) -> CorrectionPlan:
    strength = clamp(float(strength_percent), 0.0, 100.0) / 100.0
    rationale = [
        *correction.rationale,
        f"Preview/export correction strength set to {round(strength * 100)}%.",
    ]
    return CorrectionPlan(
        exposure_stops=round(correction.exposure_stops * strength, 4),
        contrast_multiplier=round(1.0 + (correction.contrast_multiplier - 1.0) * strength, 4),
        saturation_multiplier=round(
            1.0 + (correction.saturation_multiplier - 1.0) * strength,
            4,
        ),
        channel_gains=tuple(
            round(1.0 + (gain - 1.0) * strength, 4) for gain in correction.channel_gains
        ),
        lift_offset=tuple(round(offset * strength, 4) for offset in correction.lift_offset),
        confidence=correction.confidence,
        rationale=rationale,
    )


def apply_correction_array(rgb_float: np.ndarray, correction: CorrectionPlan) -> np.ndarray:
    data = np.clip(rgb_float.astype(np.float32), 0.0, 1.0)
    exposure_gain = 2.0 ** correction.exposure_stops
    gains = np.array(correction.channel_gains, dtype=np.float32)
    lift = np.array(correction.lift_offset, dtype=np.float32)

    corrected = data * exposure_gain
    corrected = corrected * gains + lift
    corrected = (corrected - 0.5) * correction.contrast_multiplier + 0.5

    luma = (
        corrected[:, :, 0] * 0.2126
        + corrected[:, :, 1] * 0.7152
        + corrected[:, :, 2] * 0.0722
    )
    corrected = luma[:, :, None] + (corrected - luma[:, :, None]) * correction.saturation_multiplier
    return np.clip(corrected, 0.0, 1.0)


def evaluate_guardrails(sample_frames: list[np.ndarray], correction: CorrectionPlan) -> GuardrailResult:
    warnings: list[str] = []
    clipping_values: list[float] = []
    for frame in sample_frames:
        small = frame.astype(np.float32) / 255.0
        corrected = apply_correction_array(small, correction)
        clipped = np.logical_or(corrected <= 0.002, corrected >= 0.998)
        clipping_values.append(float(clipped.mean() * 100.0))

    clipping_risk = float(np.median(clipping_values)) if clipping_values else 0.0
    if clipping_risk > LIMITS["max_clipping_risk_percent"]:
        warnings.append("Estimated clipping risk is above the safe threshold.")
    if abs(correction.exposure_stops) >= LIMITS["max_abs_exposure_stops"]:
        warnings.append("Exposure recommendation reached the maximum allowed adjustment.")
    if correction.saturation_multiplier in (
        LIMITS["min_saturation_multiplier"],
        LIMITS["max_saturation_multiplier"],
    ):
        warnings.append("Saturation recommendation reached the guardrail limit.")

    return GuardrailResult(
        safe_to_apply=len(warnings) == 0,
        clipping_risk_percent=round(clipping_risk, 3),
        warnings=warnings,
        limits=LIMITS.copy(),
    )


def estimate_lighting_shift(
    correction: CorrectionPlan,
    guardrails: GuardrailResult,
    threshold_percent: float,
) -> LightingShiftResult:
    threshold = clamp_percent(threshold_percent, low=5, high=100)
    contrast_limit = max(
        LIMITS["max_contrast_multiplier"] - 1.0,
        1.0 - LIMITS["min_contrast_multiplier"],
    )
    saturation_limit = max(
        LIMITS["max_saturation_multiplier"] - 1.0,
        1.0 - LIMITS["min_saturation_multiplier"],
    )
    channel_limit = max(
        LIMITS["max_channel_gain"] - 1.0,
        1.0 - LIMITS["min_channel_gain"],
    )
    components = {
        "exposure": abs(correction.exposure_stops) / LIMITS["max_abs_exposure_stops"],
        "contrast": abs(correction.contrast_multiplier - 1.0) / contrast_limit,
        "saturation": abs(correction.saturation_multiplier - 1.0) / saturation_limit,
        "channel_balance": max(abs(gain - 1.0) / channel_limit for gain in correction.channel_gains),
        "clipping": guardrails.clipping_risk_percent / LIMITS["max_clipping_risk_percent"],
    }
    weighted_shift = (
        0.32 * components["exposure"]
        + 0.18 * components["contrast"]
        + 0.18 * components["saturation"]
        + 0.17 * components["channel_balance"]
        + 0.15 * components["clipping"]
    )
    shift_percent = round(clamp(weighted_shift * 100.0, 0.0, 100.0), 2)

    warnings: list[str] = []
    if shift_percent > threshold:
        warnings.append(
            "Selected strength is likely to change the original lighting setup; lower the strength."
        )
    if not guardrails.safe_to_apply:
        warnings.append("Color guardrails flagged clipping or capped-adjustment risk at this strength.")

    return LightingShiftResult(
        shift_percent=shift_percent,
        threshold_percent=threshold,
        preserves_lighting_setup=not warnings,
        warnings=warnings,
    )
