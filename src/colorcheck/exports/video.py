from __future__ import annotations

import json
import logging
import platform
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from colorcheck.edits import EditPlan, retained_segments
from colorcheck.exports.lut import write_cube_lut
from colorcheck.models import CorrectionPlan

LOGGER = logging.getLogger(__name__)


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
class StreamingExport:
    filename: str
    media_type: str
    chunks: Iterator[bytes]


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


@lru_cache(maxsize=1)
def _available_filters() -> frozenset[str]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return frozenset()
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-filters"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return frozenset()
    return frozenset(
        fields[1]
        for line in result.stdout.splitlines()
        if len(fields := line.split()) >= 2 and fields[0][0] in {"T", "."}
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


def probe_source_duration(video_path: str | Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise ValueError("ffprobe is required to inspect the source duration.")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise ValueError("Could not inspect the source duration.") from exc
    if result.returncode != 0 or duration <= 0:
        raise ValueError("Could not inspect the source duration.")
    return duration


def _lighting_balance(plan: EditPlan) -> tuple[float, float, float]:
    presets = {
        "neutral": (0.0, 0.0, 0.0),
        "warm": (0.04, 0.01, -0.04),
        "cool": (-0.04, 0.0, 0.05),
        "golden_hour": (0.07, 0.025, -0.055),
        "moonlight": (-0.045, 0.0, 0.08),
        "fluorescent": (-0.03, 0.045, 0.01),
        "candlelight": (0.09, 0.025, -0.075),
    }
    intensity = plan.color.intensity / 100.0
    red = int(plan.color.tint[1:3], 16) / 255.0
    green = int(plan.color.tint[3:5], 16) / 255.0
    blue = int(plan.color.tint[5:7], 16) / 255.0
    mean = (red + green + blue) / 3.0
    tint = ((red - mean) * 0.16, (green - mean) * 0.16, (blue - mean) * 0.16)
    preset = presets[plan.color.mode]
    return tuple((preset[index] + tint[index]) * intensity for index in range(3))


def _write_overlay_text(work_dir: Path, index: int, text: str) -> Path:
    path = work_dir / f"overlay-{index}.txt"
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return path


def _edit_filters(
    settings: SourceVideoSettings,
    plan: EditPlan,
    correction: CorrectionPlan | None,
    work_dir: Path,
    *,
    segment_start: float,
    segment_end: float,
    preview: bool,
) -> list[str]:
    filters: list[str] = []
    crop = plan.crop
    if (crop.x, crop.y, crop.width, crop.height) != (0.0, 0.0, 1.0, 1.0):
        filters.append(
            "crop="
            f"w='max(2,trunc(iw*{crop.width:.8f}/2)*2)':"
            f"h='max(2,trunc(ih*{crop.height:.8f}/2)*2)':"
            f"x='trunc(iw*{crop.x:.8f}/2)*2':"
            f"y='trunc(ih*{crop.y:.8f}/2)*2'"
        )
    if correction is not None:
        lut_path = work_dir / "correction.cube"
        if not lut_path.exists():
            write_cube_lut(lut_path, correction, size=33)
        filters.append(f"lut3d=file='{_escaped_filter_path(lut_path)}':interp=tetrahedral")

    red, green, blue = _lighting_balance(plan)
    if max(abs(red), abs(green), abs(blue)) > 0.0001:
        values = f"rs={red:.6f}:gs={green:.6f}:bs={blue:.6f}"
        values += f":rm={red:.6f}:gm={green:.6f}:bm={blue:.6f}"
        values += f":rh={red:.6f}:gh={green:.6f}:bh={blue:.6f}"
        filters.append(f"colorbalance={values}:pl=1")
    if plan.color.black_and_white:
        filters.append("hue=s=0")

    for index, overlay in enumerate(plan.text_overlays):
        visible_start = max(segment_start, overlay.start)
        visible_end = min(segment_end, overlay.end)
        if visible_end <= visible_start:
            continue
        text_path = _write_overlay_text(work_dir, index, overlay.text)
        local_start = visible_start - segment_start
        local_end = visible_end - segment_start
        box = ":box=1:boxcolor=black@0.48:boxborderw=10" if overlay.background else ""
        filters.append(
            "drawtext="
            f"textfile='{_escaped_filter_path(text_path)}':reload=0:"
            f"fontcolor=0x{overlay.color[1:]}:fontsize=h*{overlay.size / 100.0:.6f}:"
            f"x=(w-text_w)*{overlay.x:.6f}:y=(h-text_h)*{overlay.y:.6f}:"
            f"enable='between(t,{local_start:.6f},{local_end:.6f})'{box}"
        )

    if preview:
        filters.append(
            "scale=w='min(1920,iw)':h='min(1080,ih)':"
            "force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos"
        )
        pixel_format = "yuv420p"
    else:
        pixel_format = _software_master_plan(settings).pixel_format
    filters.append(f"format={pixel_format}{_color_setparams(settings)}")
    return filters


def _stream_filter_arguments(
    settings: SourceVideoSettings,
    plan: EditPlan,
    correction: CorrectionPlan | None,
    work_dir: Path,
    duration: float,
    *,
    preview: bool,
    source_has_audio: bool,
) -> tuple[list[str], list[str], bool]:
    segments = retained_segments(plan, duration)
    full_timeline = len(segments) == 1 and segments[0][0] <= 0.001 and segments[0][1] >= duration - 0.001
    if full_timeline:
        filters = _edit_filters(
            settings,
            plan,
            correction,
            work_dir,
            segment_start=0.0,
            segment_end=duration,
            preview=preview,
        )
        return ["-vf", ",".join(filters)], ["-map", "0:v:0", "-map", "0:a:0?"], True

    video_sources = [f"vsrc{index}" for index in range(len(segments))]
    audio_sources = [f"asrc{index}" for index in range(len(segments))]
    graph: list[str] = []
    if len(segments) > 1:
        graph.append(
            f"[0:v:0]split={len(segments)}" + "".join(f"[{name}]" for name in video_sources)
        )
        if source_has_audio:
            graph.append(
                f"[0:a:0]asplit={len(segments)}" + "".join(f"[{name}]" for name in audio_sources)
            )
    else:
        video_sources = ["0:v:0"]
        audio_sources = ["0:a:0"]

    for index, (start, end) in enumerate(segments):
        filters = _edit_filters(
            settings,
            plan,
            correction,
            work_dir,
            segment_start=start,
            segment_end=end,
            preview=preview,
        )
        graph.append(
            f"[{video_sources[index]}]trim=start={start:.6f}:end={end:.6f},"
            f"setpts=PTS-STARTPTS,{','.join(filters)}[v{index}]"
        )
        if source_has_audio:
            graph.append(
                f"[{audio_sources[index]}]atrim=start={start:.6f}:end={end:.6f},"
                f"asetpts=PTS-STARTPTS[a{index}]"
            )

    if source_has_audio:
        concat_inputs = "".join(f"[v{index}][a{index}]" for index in range(len(segments)))
        graph.append(f"{concat_inputs}concat=n={len(segments)}:v=1:a=1[vout][aout]")
        mapping = ["-map", "[vout]", "-map", "[aout]"]
    else:
        concat_inputs = "".join(f"[v{index}]" for index in range(len(segments)))
        graph.append(f"{concat_inputs}concat=n={len(segments)}:v=1:a=0[vout]")
        mapping = ["-map", "[vout]"]
    return ["-filter_complex", ";".join(graph)], mapping, False


def stream_edited_video(
    video_path: str | Path,
    work_dir: str | Path,
    edit_plan: EditPlan,
    correction: CorrectionPlan | None,
    *,
    preview: bool = False,
) -> StreamingExport:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ValueError("ffmpeg is required to stream an edited export.")
    if edit_plan.text_overlays and "drawtext" not in _available_filters():
        raise ValueError("This FFmpeg build does not include the text-overlay filter.")
    source = Path(video_path)
    temporary_dir = Path(work_dir)
    temporary_dir.mkdir(parents=True, exist_ok=True)
    settings = probe_source_video_settings(source)
    duration = probe_source_duration(source)
    source_has_audio = has_audio_stream(source) is True
    filter_arguments, mapping, full_timeline = _stream_filter_arguments(
        settings,
        edit_plan,
        correction,
        temporary_dir,
        duration,
        preview=preview,
        source_has_audio=source_has_audio,
    )

    if preview:
        encoder = _preview_encoder_plans()[-1]
        filename = "colorcheck-preview.mp4"
        media_type = "video/mp4"
        muxer = "mp4"
        audio_arguments = ["-c:a", "aac", "-b:a", "192k"]
    else:
        encoder = _software_master_plan(settings)
        filename = "colorcheck-master.mov"
        media_type = "video/quicktime"
        muxer = "mov"
        audio_arguments = (
            ["-c:a", "copy"]
            if full_timeline
            else ["-c:a", "aac", "-b:a", "256k"]
        )

    command = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        *filter_arguments,
        *mapping,
        "-map_metadata",
        "0",
        *encoder.arguments,
        *_color_metadata_args(settings),
        "-fps_mode",
        "passthrough",
        *audio_arguments,
        "-movflags",
        "frag_keyframe+empty_moov+default_base_moof",
        "-f",
        muxer,
        "pipe:1",
    ]

    def chunks() -> Iterator[bytes]:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert process.stdout is not None
        try:
            while chunk := process.stdout.read(1024 * 1024):
                yield chunk
            return_code = process.wait()
            if return_code != 0:
                stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
                LOGGER.error("Streaming FFmpeg export failed: %s", stderr.strip())
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()

    return StreamingExport(filename=filename, media_type=media_type, chunks=chunks())
