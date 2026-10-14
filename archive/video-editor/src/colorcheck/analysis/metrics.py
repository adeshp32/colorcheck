from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from colorcheck.models import FrameAnalysis, LightingProfile

RGB_TO_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


@dataclass(frozen=True)
class VideoFrame:
    frame_index: int
    timestamp_sec: float
    rgb: np.ndarray


@dataclass(frozen=True)
class PreparedImage:
    rgb: np.ndarray
    normalized: np.ndarray
    luma: np.ndarray
    lab: np.ndarray
    histograms: tuple[np.ndarray, np.ndarray, np.ndarray]
    profile: LightingProfile


LIGHTING_ARCHETYPES = {
    "neutral daylight": (0.52, 0.22, 0.34, 0.00),
    "warm indoor": (0.45, 0.18, 0.38, 0.08),
    "cool shade": (0.42, 0.17, 0.30, -0.08),
    "low-key dramatic": (0.24, 0.20, 0.28, 0.01),
    "high-key bright": (0.74, 0.15, 0.25, 0.00),
    "muted low saturation": (0.46, 0.14, 0.14, 0.00),
}


def load_image_rgb(path: str | Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not read image: {path}")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def resize_for_analysis(rgb: np.ndarray, max_side: int = 512) -> np.ndarray:
    height, width = rgb.shape[:2]
    largest = max(height, width)
    if largest <= max_side:
        return rgb
    scale = max_side / largest
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return cv2.resize(rgb, new_size, interpolation=cv2.INTER_AREA)


def _saturation_mean(resized_rgb: np.ndarray) -> float:
    hsv = cv2.cvtColor(resized_rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    return float((hsv[:, :, 1] / 255.0).mean())


def _lab_delta_e(reference_lab: np.ndarray, target_lab: np.ndarray) -> float:
    delta = reference_lab - target_lab
    return float(np.sqrt(np.sum(delta * delta, axis=2)).mean())


def _global_ssim(reference_y: np.ndarray, target_y: np.ndarray) -> float:
    c1 = 0.01**2
    c2 = 0.03**2
    ref = reference_y.flatten()
    tgt = target_y.flatten()
    mu_ref = float(ref.mean())
    mu_tgt = float(tgt.mean())
    var_ref = float(ref.var())
    var_tgt = float(tgt.var())
    cov = ((ref - mu_ref) * (tgt - mu_tgt)).mean()
    score = ((2 * mu_ref * mu_tgt + c1) * (2 * cov + c2)) / (
        (mu_ref**2 + mu_tgt**2 + c1) * (var_ref + var_tgt + c2)
    )
    return float(np.clip(score, 0.0, 1.0))


def _channel_histograms(normalized: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    histograms = []
    for channel in range(3):
        histogram = np.histogram(normalized[:, :, channel], bins=48, range=(0.0, 1.0))[0]
        histogram = histogram.astype(np.float32)
        histogram /= max(float(histogram.sum()), 1.0)
        histograms.append(histogram)
    return tuple(histograms)  # type: ignore[return-value]


def _histogram_similarity(
    reference: tuple[np.ndarray, np.ndarray, np.ndarray],
    target: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> float:
    similarities = [
        float(np.minimum(ref_hist, target_hist).sum())
        for ref_hist, target_hist in zip(reference, target, strict=True)
    ]
    return float(sum(similarities) / len(similarities))


def nearest_lighting_archetype(
    luma_mean: float,
    luma_std: float,
    saturation_mean: float,
    temperature_proxy: float,
) -> tuple[str, float]:
    current = np.array([luma_mean, luma_std, saturation_mean, temperature_proxy], dtype=np.float32)
    best_label = ""
    best_distance = float("inf")
    for label, values in LIGHTING_ARCHETYPES.items():
        archetype = np.array(values, dtype=np.float32)
        weights = np.array([1.6, 1.1, 1.0, 1.2], dtype=np.float32)
        distance = float(np.linalg.norm((current - archetype) * weights))
        if distance < best_distance:
            best_label = label
            best_distance = distance
    return best_label, best_distance


def _profile_resized(resized_rgb: np.ndarray, normalized: np.ndarray, luma: np.ndarray) -> LightingProfile:
    rgb_mean = normalized.mean(axis=(0, 1))
    rgb_std = normalized.std(axis=(0, 1))
    saturation = _saturation_mean(resized_rgb)
    temperature_proxy = float(rgb_mean[0] - rgb_mean[2])
    label, distance = nearest_lighting_archetype(
        float(luma.mean()),
        float(luma.std()),
        saturation,
        temperature_proxy,
    )
    return LightingProfile(
        luma_mean=float(luma.mean()),
        luma_std=float(luma.std()),
        saturation_mean=saturation,
        temperature_proxy=temperature_proxy,
        rgb_mean=tuple(float(v) for v in rgb_mean.tolist()),
        rgb_std=tuple(float(v) for v in rgb_std.tolist()),
        lighting_label=label,
        lighting_distance=distance,
    )


def prepare_image(rgb: np.ndarray, size: tuple[int, int] | None = None) -> PreparedImage:
    resized = resize_for_analysis(rgb)
    if size is not None and (resized.shape[1], resized.shape[0]) != size:
        resized = cv2.resize(resized, size, interpolation=cv2.INTER_AREA)
    normalized = resized.astype(np.float32) / 255.0
    luma = (normalized * RGB_TO_LUMA).sum(axis=2)
    return PreparedImage(
        rgb=resized,
        normalized=normalized,
        luma=luma,
        lab=cv2.cvtColor(resized, cv2.COLOR_RGB2LAB).astype(np.float32),
        histograms=_channel_histograms(normalized),
        profile=_profile_resized(resized, normalized, luma),
    )


def profile_image(rgb: np.ndarray) -> LightingProfile:
    return prepare_image(rgb).profile


def compare_prepared_frame(
    reference: PreparedImage,
    frame: VideoFrame,
    target: PreparedImage | None = None,
) -> FrameAnalysis:
    target = target or prepare_image(
        frame.rgb,
        size=(reference.rgb.shape[1], reference.rgb.shape[0]),
    )
    if target.rgb.shape != reference.rgb.shape:
        target = prepare_image(
            target.rgb,
            size=(reference.rgb.shape[1], reference.rgb.shape[0]),
        )
    ref_profile = reference.profile
    target_profile = target.profile
    ssim = _global_ssim(reference.luma, target.luma)
    histogram = _histogram_similarity(reference.histograms, target.histograms)
    delta_e = _lab_delta_e(reference.lab, target.lab)

    luma_delta = target_profile.luma_mean - ref_profile.luma_mean
    contrast_delta = target_profile.luma_std - ref_profile.luma_std
    saturation_delta = target_profile.saturation_mean - ref_profile.saturation_mean
    temperature_delta = target_profile.temperature_proxy - ref_profile.temperature_proxy

    luma_score = 1.0 - min(abs(luma_delta) / 0.35, 1.0)
    contrast_score = 1.0 - min(abs(contrast_delta) / 0.25, 1.0)
    saturation_score = 1.0 - min(abs(saturation_delta) / 0.30, 1.0)
    temperature_score = 1.0 - min(abs(temperature_delta) / 0.22, 1.0)
    delta_e_score = 1.0 - min(delta_e / 65.0, 1.0)
    score = (
        0.22 * ssim
        + 0.18 * histogram
        + 0.18 * luma_score
        + 0.12 * contrast_score
        + 0.12 * saturation_score
        + 0.10 * temperature_score
        + 0.08 * delta_e_score
    )

    notes: list[str] = []
    if luma_delta < -0.08:
        notes.append("target frame is noticeably darker than the reference")
    elif luma_delta > 0.08:
        notes.append("target frame is noticeably brighter than the reference")
    if saturation_delta < -0.08:
        notes.append("target frame is less saturated than the reference")
    elif saturation_delta > 0.08:
        notes.append("target frame is more saturated than the reference")
    if temperature_delta < -0.05:
        notes.append("target frame is cooler than the reference")
    elif temperature_delta > 0.05:
        notes.append("target frame is warmer than the reference")

    return FrameAnalysis(
        frame_index=frame.frame_index,
        timestamp_sec=frame.timestamp_sec,
        match_score=round(float(score * 100.0), 2),
        ssim=round(ssim, 4),
        delta_e_mean=round(delta_e, 2),
        histogram_similarity=round(histogram, 4),
        luma_delta=round(luma_delta, 4),
        contrast_delta=round(contrast_delta, 4),
        saturation_delta=round(saturation_delta, 4),
        temperature_delta=round(temperature_delta, 4),
        target_profile=target_profile,
        notes=notes,
    )


def compare_frame(reference_rgb: np.ndarray, frame: VideoFrame) -> FrameAnalysis:
    return compare_prepared_frame(prepare_image(reference_rgb), frame)


def sample_video_frames(video_path: str | Path, sample_count: int = 24) -> list[VideoFrame]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    if frame_count <= 0:
        raise ValueError("Video does not expose a frame count; try transcoding it with ffmpeg first.")

    sample_total = max(1, min(sample_count, frame_count))
    indices = np.linspace(0, frame_count - 1, num=sample_total, dtype=int)
    frames: list[VideoFrame] = []
    for frame_index in indices:
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
        ok, bgr = capture.read()
        if not ok or bgr is None:
            continue
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        frames.append(
            VideoFrame(
                frame_index=int(frame_index),
                timestamp_sec=float(frame_index / fps),
                rgb=rgb,
            )
        )

    capture.release()
    if not frames:
        raise ValueError("No frames could be sampled from the video.")
    return frames
