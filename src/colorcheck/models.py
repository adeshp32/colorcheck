from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class LightingProfile:
    luma_mean: float
    luma_std: float
    saturation_mean: float
    temperature_proxy: float
    rgb_mean: tuple[float, float, float]
    rgb_std: tuple[float, float, float]
    lighting_label: str
    lighting_distance: float


@dataclass(frozen=True)
class FrameAnalysis:
    frame_index: int
    timestamp_sec: float
    match_score: float
    ssim: float
    delta_e_mean: float
    histogram_similarity: float
    luma_delta: float
    contrast_delta: float
    saturation_delta: float
    temperature_delta: float
    target_profile: LightingProfile
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CorrectionPlan:
    exposure_stops: float
    contrast_multiplier: float
    saturation_multiplier: float
    channel_gains: tuple[float, float, float]
    lift_offset: tuple[float, float, float]
    confidence: float
    rationale: list[str]


@dataclass(frozen=True)
class GuardrailResult:
    safe_to_apply: bool
    clipping_risk_percent: float
    warnings: list[str]
    limits: dict[str, float]


@dataclass(frozen=True)
class ExportSettings:
    correction_strength_percent: int
    lighting_shift_threshold_percent: int
    audio_status: str


@dataclass(frozen=True)
class LightingShiftResult:
    shift_percent: float
    threshold_percent: int
    preserves_lighting_setup: bool
    warnings: list[str]


@dataclass(frozen=True)
class AnalysisSummary:
    overall_score: float
    drift_level: str
    risky_frame_count: int
    sampled_frame_count: int
    reference_lighting: str
    target_lighting: str
    recommendation: str


@dataclass(frozen=True)
class AnalysisReport:
    reference_path: str
    video_path: str
    reference_profile: LightingProfile
    aggregate_target_profile: LightingProfile
    frames: list[FrameAnalysis]
    correction: CorrectionPlan
    guardrails: GuardrailResult
    export_settings: ExportSettings
    lighting_shift: LightingShiftResult
    summary: AnalysisSummary
    corrected_video_filename: str | None = None
    corrected_master_filename: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
