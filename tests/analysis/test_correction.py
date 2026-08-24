from colorcheck.analysis.correction import (
    LIMITS,
    estimate_lighting_shift,
    evaluate_guardrails,
    recommend_correction,
    scale_correction,
)
from colorcheck.models import CorrectionPlan, FrameAnalysis, LightingProfile


def profile(luma: float, saturation: float, temperature: float) -> LightingProfile:
    return LightingProfile(
        luma_mean=luma,
        luma_std=0.2,
        saturation_mean=saturation,
        temperature_proxy=temperature,
        rgb_mean=(luma + temperature, luma, luma - temperature),
        rgb_std=(0.1, 0.1, 0.1),
        lighting_label="neutral daylight",
        lighting_distance=0.1,
    )


def frame(score: float) -> FrameAnalysis:
    target = profile(0.2, 0.2, -0.1)
    return FrameAnalysis(
        frame_index=1,
        timestamp_sec=0.0,
        match_score=score,
        ssim=0.8,
        delta_e_mean=10.0,
        histogram_similarity=0.8,
        luma_delta=-0.2,
        contrast_delta=0.0,
        saturation_delta=-0.2,
        temperature_delta=-0.1,
        target_profile=target,
    )


def test_recommendation_is_clamped_to_guardrails() -> None:
    correction = recommend_correction(
        reference=profile(0.8, 0.8, 0.1),
        target=profile(0.1, 0.1, -0.2),
        frames=[frame(60.0), frame(65.0)],
    )

    assert abs(correction.exposure_stops) <= LIMITS["max_abs_exposure_stops"]
    assert LIMITS["min_saturation_multiplier"] <= correction.saturation_multiplier
    assert correction.saturation_multiplier <= LIMITS["max_saturation_multiplier"]
    assert all(LIMITS["min_channel_gain"] <= gain <= LIMITS["max_channel_gain"] for gain in correction.channel_gains)


def test_scale_correction_interpolates_from_identity() -> None:
    correction = CorrectionPlan(
        exposure_stops=0.3,
        contrast_multiplier=1.1,
        saturation_multiplier=0.9,
        channel_gains=(1.08, 0.96, 1.0),
        lift_offset=(0.02, 0.0, -0.02),
        confidence=0.7,
        rationale=[],
    )

    scaled = scale_correction(correction, 50)

    assert scaled.exposure_stops == 0.15
    assert scaled.contrast_multiplier == 1.05
    assert scaled.saturation_multiplier == 0.95
    assert scaled.channel_gains == (1.04, 0.98, 1.0)
    assert scaled.lift_offset == (0.01, 0.0, -0.01)


def test_lighting_shift_warns_when_threshold_is_crossed() -> None:
    correction = CorrectionPlan(
        exposure_stops=LIMITS["max_abs_exposure_stops"],
        contrast_multiplier=LIMITS["max_contrast_multiplier"],
        saturation_multiplier=LIMITS["max_saturation_multiplier"],
        channel_gains=(LIMITS["max_channel_gain"], 1.0, LIMITS["min_channel_gain"]),
        lift_offset=(0.0, 0.0, 0.0),
        confidence=0.8,
        rationale=[],
    )
    guardrails = evaluate_guardrails([], correction)

    shift = estimate_lighting_shift(correction, guardrails, threshold_percent=20)

    assert shift.shift_percent > 20
    assert not shift.preserves_lighting_setup
