from __future__ import annotations

from pathlib import Path

import numpy as np

from video_color_checker.correction import (
    aggregate_profile,
    clamp_percent,
    estimate_lighting_shift,
    evaluate_guardrails,
    recommend_correction,
    scale_correction,
)
from video_color_checker.image_metrics import (
    compare_frame,
    load_image_rgb,
    nearest_lighting_archetype,
    profile_image,
    sample_video_frames,
)
from video_color_checker.models import (
    AnalysisReport,
    AnalysisSummary,
    ExportSettings,
    LightingProfile,
)
from video_color_checker.reporting import write_report_package
from video_color_checker.video_export import write_corrected_master, write_corrected_video

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}


def _is_video(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def _aggregate_lighting_profiles(profiles: list[LightingProfile]) -> LightingProfile:
    if not profiles:
        raise ValueError("Cannot aggregate an empty profile list.")

    def median_attr(attr: str) -> float:
        return float(np.median([getattr(profile, attr) for profile in profiles]))

    rgb_mean = tuple(
        float(np.median([profile.rgb_mean[channel] for profile in profiles]))
        for channel in range(3)
    )
    rgb_std = tuple(
        float(np.median([profile.rgb_std[channel] for profile in profiles]))
        for channel in range(3)
    )
    luma_mean = median_attr("luma_mean")
    luma_std = median_attr("luma_std")
    saturation_mean = median_attr("saturation_mean")
    temperature_proxy = median_attr("temperature_proxy")
    label, distance = nearest_lighting_archetype(
        luma_mean,
        luma_std,
        saturation_mean,
        temperature_proxy,
    )
    return LightingProfile(
        luma_mean=luma_mean,
        luma_std=luma_std,
        saturation_mean=saturation_mean,
        temperature_proxy=temperature_proxy,
        rgb_mean=rgb_mean,
        rgb_std=rgb_std,
        lighting_label=label,
        lighting_distance=distance,
    )


def _profile_distance(reference: LightingProfile, target: LightingProfile) -> float:
    values = np.array(
        [
            reference.luma_mean - target.luma_mean,
            reference.luma_std - target.luma_std,
            reference.saturation_mean - target.saturation_mean,
            reference.temperature_proxy - target.temperature_proxy,
        ],
        dtype=np.float32,
    )
    weights = np.array([1.6, 1.1, 1.0, 1.2], dtype=np.float32)
    return float(np.linalg.norm(values * weights))


def _reference_candidates(
    reference_path: str | Path,
    sample_count: int,
) -> tuple[list[tuple[np.ndarray, LightingProfile, str]], LightingProfile]:
    if _is_video(reference_path):
        reference_frames = sample_video_frames(reference_path, sample_count=sample_count)
        candidates = [
            (
                frame.rgb,
                profile_image(frame.rgb),
                f"reference video at {frame.timestamp_sec:.2f}s",
            )
            for frame in reference_frames
        ]
    else:
        reference_rgb = load_image_rgb(reference_path)
        candidates = [(reference_rgb, profile_image(reference_rgb), "reference image")]

    aggregate_reference = _aggregate_lighting_profiles([candidate[1] for candidate in candidates])
    return candidates, aggregate_reference


def _best_reference_for_target(
    candidates: list[tuple[np.ndarray, LightingProfile, str]],
    target_profile: LightingProfile,
) -> tuple[np.ndarray, str]:
    best_rgb, _best_profile, best_label = min(
        candidates,
        key=lambda candidate: _profile_distance(candidate[1], target_profile),
    )
    return best_rgb, best_label


def _drift_level(overall_score: float) -> str:
    if overall_score >= 90:
        return "minimal"
    if overall_score >= 80:
        return "mild"
    if overall_score >= 65:
        return "moderate"
    return "strong"


def _recommendation(
    overall_score: float,
    safe_to_apply: bool,
    preserves_lighting_setup: bool,
) -> str:
    if overall_score >= 90:
        return "The video already tracks closely to the reference. Use any generated correction lightly."
    if not preserves_lighting_setup:
        return "The selected correction strength may change the original lighting setup. Lower strength before final use."
    if safe_to_apply:
        return "A conservative correction is recommended. Review scopes before applying to final footage."
    return "Correction guidance is available, but guardrails flagged risk. Apply manually and reduce strength."


def analyze_video(
    reference_path: str | Path,
    video_path: str | Path,
    out_dir: str | Path,
    sample_count: int = 24,
    correction_strength_percent: int = 50,
    lighting_shift_threshold_percent: int = 60,
) -> tuple[AnalysisReport, dict[str, Path]]:
    output_dir = Path(out_dir)
    reference_candidates, reference_profile = _reference_candidates(reference_path, sample_count)
    sampled_frames = sample_video_frames(video_path, sample_count=sample_count)
    frame_results = []
    for frame in sampled_frames:
        target_profile = profile_image(frame.rgb)
        reference_rgb, matched_reference = _best_reference_for_target(
            reference_candidates,
            target_profile,
        )
        frame_result = compare_frame(reference_rgb, frame)
        if len(reference_candidates) > 1:
            frame_result = frame_result.__class__(
                **{
                    **frame_result.__dict__,
                    "notes": [f"matched {matched_reference}", *frame_result.notes],
                }
        )
        frame_results.append(frame_result)
    aggregate_target = aggregate_profile(frame_results)
    full_correction = recommend_correction(reference_profile, aggregate_target, frame_results)
    strength = clamp_percent(correction_strength_percent)
    threshold = clamp_percent(lighting_shift_threshold_percent, low=5, high=100)
    correction = scale_correction(full_correction, strength)
    guardrails = evaluate_guardrails(
        [frame.rgb for frame in sampled_frames],
        correction,
    )
    lighting_shift = estimate_lighting_shift(correction, guardrails, threshold)
    overall_score = float(np.median([frame.match_score for frame in frame_results]))
    risky_count = sum(1 for frame in frame_results if frame.match_score < 75.0)
    summary = AnalysisSummary(
        overall_score=round(overall_score, 2),
        drift_level=_drift_level(overall_score),
        risky_frame_count=risky_count,
        sampled_frame_count=len(frame_results),
        reference_lighting=reference_profile.lighting_label,
        target_lighting=aggregate_target.lighting_label,
        recommendation=_recommendation(
            overall_score,
            guardrails.safe_to_apply,
            lighting_shift.preserves_lighting_setup,
        ),
    )
    corrected_video_filename = "corrected_preview.mp4" if strength > 0 else None
    corrected_master_filename = "corrected_master.mov" if strength > 0 else None
    corrected_video = None
    corrected_master = None
    audio_status = "not_exported"
    if corrected_video_filename:
        corrected_video = write_corrected_video(
            video_path,
            output_dir / corrected_video_filename,
            correction,
        )
        audio_status = corrected_video.audio_status
    if corrected_master_filename:
        corrected_master = write_corrected_master(
            video_path,
            output_dir / corrected_master_filename,
            correction,
        )
    report = AnalysisReport(
        reference_path=Path(reference_path).name,
        video_path=Path(video_path).name,
        reference_profile=reference_profile,
        aggregate_target_profile=aggregate_target,
        frames=frame_results,
        correction=correction,
        guardrails=guardrails,
        export_settings=ExportSettings(
            correction_strength_percent=strength,
            lighting_shift_threshold_percent=threshold,
            audio_status=audio_status,
        ),
        lighting_shift=lighting_shift,
        summary=summary,
        corrected_video_filename=corrected_video_filename,
        corrected_master_filename=corrected_master_filename,
    )
    written = write_report_package(report, output_dir)
    if corrected_video:
        written["corrected_video"] = corrected_video.path
    if corrected_master:
        written["corrected_master"] = corrected_master.path
    return report, written
