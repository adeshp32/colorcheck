from __future__ import annotations

import json
import platform
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from colorcheck.exports.lut import write_cube_lut
from colorcheck.models import CorrectionPlan


@dataclass(frozen=True)
class VideoExportResult:
    path: Path
    audio_status: str


@dataclass(frozen=True)
class SourceVideoSettings:
    codec_name: str
    profile: str
    pixel_format: str
    width: int
    height: int
    color_range: str
    color_space: str
    color_transfer: str
    color_primaries: str


@dataclass(frozen=True)
class MasterExportResult:
    path: Path
    codec_name: str
    profile: str
    pixel_format: str
    codec_preserved: bool
    encoder_name: str
    hardware_accelerated: bool


@dataclass(frozen=True)
class CorrectedExportsResult:
    preview: VideoExportResult
    master: MasterExportResult


@dataclass(frozen=True)
class _EncoderPlan:
    name: str
    codec_name: str
    pixel_format: str
    arguments: tuple[str, ...]
    hardware_accelerated: bool


@lru_cache(maxsize=1)
def _available_video_encoders() -> frozenset[str]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return frozenset()
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return frozenset()
    return frozenset(
        fields[1]
        for line in result.stdout.splitlines()
        if len(fields := line.split()) >= 2 and fields[0].startswith("V")
    )


def probe_source_video_settings(video_path: str | Path) -> SourceVideoSettings:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise ValueError("ffprobe is required to preserve source video settings.")

    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            (
                "stream=codec_name,profile,pix_fmt,width,height,color_range,color_space,"
                "color_transfer,color_primaries"
            ),
            "-of",
            "json",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("Could not inspect source video settings.")

    streams = json.loads(result.stdout).get("streams", [])
    if not streams:
        raise ValueError("The source does not contain a video stream.")
    stream = streams[0]
    return SourceVideoSettings(
        codec_name=str(stream.get("codec_name", "unknown")),
        profile=str(stream.get("profile", "unknown")),
        pixel_format=str(stream.get("pix_fmt", "yuv420p")),
        width=int(stream.get("width", 0)),
        height=int(stream.get("height", 0)),
        color_range=str(stream.get("color_range", "unknown")),
        color_space=str(stream.get("color_space", "unknown")),
        color_transfer=str(stream.get("color_transfer", "unknown")),
        color_primaries=str(stream.get("color_primaries", "unknown")),
    )


def _h264_profile_arguments(settings: SourceVideoSettings) -> tuple[str, ...]:
    profile = settings.profile.strip().lower().replace(" ", "_")
    normalized = {
        "baseline": "baseline",
        "constrained_baseline": "baseline",
        "main": "main",
        "high": "high",
        "constrained_high": "high",
    }.get(profile)
    if normalized is not None:
        return "-profile:v", normalized
    return ()


def _software_master_plan(settings: SourceVideoSettings) -> _EncoderPlan:
    if settings.codec_name in {"hevc", "h265"}:
        pixel_format = settings.pixel_format if settings.pixel_format.startswith("yuv") else "yuv420p"
        return _EncoderPlan(
            name="libx265",
            codec_name="hevc",
            pixel_format=pixel_format,
            arguments=("-c:v", "libx265", "-preset", "fast", "-crf", "16", "-tag:v", "hvc1"),
            hardware_accelerated=False,
        )
    if settings.codec_name == "h264":
        pixel_format = settings.pixel_format if settings.pixel_format.startswith("yuv") else "yuv420p"
        return _EncoderPlan(
            name="libx264",
            codec_name="h264",
            pixel_format=pixel_format,
            arguments=(
                "-c:v",
                "libx264",
                *_h264_profile_arguments(settings),
                "-preset",
                "fast",
                "-crf",
                "15",
                "-tag:v",
                "avc1",
            ),
            hardware_accelerated=False,
        )
    return _EncoderPlan(
        name="libx264",
        codec_name="h264",
        pixel_format="yuv420p",
        arguments=("-c:v", "libx264", "-preset", "fast", "-crf", "15", "-tag:v", "avc1"),
        hardware_accelerated=False,
    )


def _videotoolbox_master_plan(settings: SourceVideoSettings) -> _EncoderPlan | None:
    if platform.system() != "Darwin":
        return None
    available = _available_video_encoders()
    if settings.codec_name in {"hevc", "h265"} and "hevc_videotoolbox" in available:
        format_profile = {
            "yuv420p": ("yuv420p", "main"),
            "nv12": ("yuv420p", "main"),
            "yuv420p10le": ("p010le", "main10"),
            "p010le": ("p010le", "main10"),
            "yuv422p10le": ("p210le", "main42210"),
            "p210le": ("p210le", "main42210"),
        }.get(settings.pixel_format)
        if format_profile is not None:
            pixel_format, profile = format_profile
            return _EncoderPlan(
                name="hevc_videotoolbox",
                codec_name="hevc",
                pixel_format=pixel_format,
                arguments=(
                    "-c:v",
                    "hevc_videotoolbox",
                    "-profile:v",
                    profile,
                    "-q:v",
                    "65",
                    "-tag:v",
                    "hvc1",
                ),
                hardware_accelerated=True,
            )
    if (
        settings.codec_name == "h264"
        and settings.pixel_format in {"yuv420p", "nv12"}
        and "h264_videotoolbox" in available
    ):
        return _EncoderPlan(
            name="h264_videotoolbox",
            codec_name="h264",
            pixel_format="yuv420p",
            arguments=(
                "-c:v",
                "h264_videotoolbox",
                *_h264_profile_arguments(settings),
                "-q:v",
                "65",
                "-tag:v",
                "avc1",
            ),
            hardware_accelerated=True,
        )
    return None


def _master_encoder_plans(settings: SourceVideoSettings) -> tuple[_EncoderPlan, ...]:
    hardware = _videotoolbox_master_plan(settings)
    software = _software_master_plan(settings)
    return (hardware, software) if hardware is not None else (software,)


def _color_metadata_args(settings: SourceVideoSettings) -> list[str]:
    options = (
        ("-color_range", settings.color_range),
        ("-colorspace", settings.color_space),
        ("-color_trc", settings.color_transfer),
        ("-color_primaries", settings.color_primaries),
    )
    return [item for option, value in options if value != "unknown" for item in (option, value)]


def _color_setparams(settings: SourceVideoSettings) -> str:
    color_range = {"tv": "limited", "pc": "full"}.get(settings.color_range, settings.color_range)
    options = (
        ("range", color_range),
        ("color_primaries", settings.color_primaries),
        ("color_trc", settings.color_transfer),
        ("colorspace", settings.color_space),
    )
    values = [f"{name}={value}" for name, value in options if value != "unknown"]
    return f",setparams={':'.join(values)}" if values else ""


def _escaped_filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _run_master_encode(
    ffmpeg: str,
    source: Path,
    destination: Path,
    settings: SourceVideoSettings,
    video_filter: str,
    plan: _EncoderPlan,
    audio_arguments: tuple[str, ...],
) -> subprocess.CompletedProcess[str]:
    destination.unlink(missing_ok=True)
    return subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-map_metadata",
            "0",
            "-vf",
            video_filter,
            *plan.arguments,
            *_color_metadata_args(settings),
            "-fps_mode",
            "passthrough",
            *audio_arguments,
            "-movflags",
            "+faststart",
            str(destination),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def write_corrected_master(
    video_path: str | Path,
    output_path: str | Path,
    correction: CorrectionPlan,
) -> MasterExportResult:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ValueError("ffmpeg is required to create a quality-preserving master export.")

    source = Path(video_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    settings = probe_source_video_settings(source)
    lut_path = destination.with_name(f".{destination.stem}.cube")
    write_cube_lut(lut_path, correction, size=33)
    result: subprocess.CompletedProcess[str] | None = None
    successful_plan: _EncoderPlan | None = None
    try:
        for plan in _master_encoder_plans(settings):
            video_filter = (
                f"lut3d=file='{_escaped_filter_path(lut_path)}':interp=tetrahedral,"
                f"format={plan.pixel_format}{_color_setparams(settings)}"
            )
            for audio_arguments in (("-c:a", "copy"), ("-c:a", "aac", "-b:a", "192k")):
                result = _run_master_encode(
                    ffmpeg,
                    source,
                    destination,
                    settings,
                    video_filter,
                    plan,
                    audio_arguments,
                )
                if result.returncode == 0:
                    successful_plan = plan
                    break
            if successful_plan is not None:
                break
    finally:
        lut_path.unlink(missing_ok=True)
    if result is None or successful_plan is None:
        destination.unlink(missing_ok=True)
        stderr = result.stderr.strip() if result is not None else ""
        detail = stderr.splitlines()[-1] if stderr else "unknown error"
        raise ValueError(f"Could not create corrected master: {detail}")

    output_settings = probe_source_video_settings(destination)
    normalized_source_codec = "hevc" if settings.codec_name in {"hevc", "h265"} else settings.codec_name
    return MasterExportResult(
        path=destination,
        codec_name=output_settings.codec_name,
        profile=output_settings.profile,
        pixel_format=output_settings.pixel_format,
        codec_preserved=output_settings.codec_name == normalized_source_codec,
        encoder_name=successful_plan.name,
        hardware_accelerated=successful_plan.hardware_accelerated,
    )


def has_audio_stream(video_path: str | Path) -> bool | None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None

    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def _preview_encoder_plans() -> tuple[_EncoderPlan, ...]:
    plans = []
    if platform.system() == "Darwin" and "h264_videotoolbox" in _available_video_encoders():
        plans.append(
            _EncoderPlan(
                name="h264_videotoolbox",
                codec_name="h264",
                pixel_format="yuv420p",
                arguments=("-c:v", "h264_videotoolbox", "-q:v", "65", "-tag:v", "avc1"),
                hardware_accelerated=True,
            )
        )
    plans.append(
        _EncoderPlan(
            name="libx264",
            codec_name="h264",
            pixel_format="yuv420p",
            arguments=("-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-tag:v", "avc1"),
            hardware_accelerated=False,
        )
    )
    return tuple(plans)


def _preview_filter(
    settings: SourceVideoSettings,
    pixel_format: str,
    lut_path: Path | None,
) -> str:
    filters = []
    if lut_path is not None:
        filters.append(
            f"lut3d=file='{_escaped_filter_path(lut_path)}':interp=tetrahedral"
        )
    filters.extend(
        (
            (
                "scale=w='min(1920,iw)':h='min(1920,ih)':"
                "force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos"
            ),
            f"format={pixel_format}{_color_setparams(settings)}",
        )
    )
    return ",".join(filters)


def write_corrected_preview(
    video_path: str | Path,
    output_path: str | Path,
    correction: CorrectionPlan | None = None,
) -> VideoExportResult:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ValueError("ffmpeg is required to create a corrected preview export.")

    source = Path(video_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    settings = probe_source_video_settings(source)
    source_has_audio = has_audio_stream(source)
    lut_path = destination.with_name(f".{destination.stem}.cube") if correction else None
    if lut_path is not None:
        write_cube_lut(lut_path, correction, size=33)
    result: subprocess.CompletedProcess[str] | None = None
    try:
        for plan in _preview_encoder_plans():
            destination.unlink(missing_ok=True)
            result = subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(source),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0?",
                    "-map_metadata",
                    "0",
                    "-vf",
                    _preview_filter(settings, plan.pixel_format, lut_path),
                    *plan.arguments,
                    *_color_metadata_args(settings),
                    "-fps_mode",
                    "passthrough",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-movflags",
                    "+faststart",
                    str(destination),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                break
    finally:
        if lut_path is not None:
            lut_path.unlink(missing_ok=True)

    if result is None or result.returncode != 0:
        destination.unlink(missing_ok=True)
        stderr = result.stderr.strip() if result is not None else ""
        detail = stderr.splitlines()[-1] if stderr else "unknown error"
        raise ValueError(f"Could not create corrected preview: {detail}")

    output_has_audio = has_audio_stream(destination)
    if source_has_audio is False:
        audio_status = "source_has_no_audio"
    elif source_has_audio is True and output_has_audio is True:
        audio_status = "preserved"
    else:
        audio_status = "unavailable"
    return VideoExportResult(path=destination, audio_status=audio_status)


def write_corrected_exports(
    video_path: str | Path,
    preview_path: str | Path,
    master_path: str | Path,
    correction: CorrectionPlan,
) -> CorrectedExportsResult:
    master = write_corrected_master(video_path, master_path, correction)
    preview = write_corrected_preview(master.path, preview_path)
    return CorrectedExportsResult(preview=preview, master=master)


def write_corrected_video(
    video_path: str | Path,
    output_path: str | Path,
    correction: CorrectionPlan,
) -> VideoExportResult:
    return write_corrected_preview(video_path, output_path, correction)
