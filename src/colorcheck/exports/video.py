from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from colorcheck.analysis.correction import apply_correction_array
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


def _master_encoder(settings: SourceVideoSettings) -> tuple[str, str, str, bool]:
    if settings.codec_name in {"hevc", "h265"}:
        pixel_format = settings.pixel_format if "10" in settings.pixel_format else "yuv420p"
        return "libx265", "hevc", pixel_format, True
    if settings.codec_name == "h264":
        pixel_format = settings.pixel_format if settings.pixel_format.startswith("yuv") else "yuv420p"
        return "libx264", "h264", pixel_format, True
    return "libx264", "h264", "yuv420p", False


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


def _run_master_encode(command: list[str], destination: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        return result

    destination.unlink(missing_ok=True)
    audio_index = command.index("-c:a")
    fallback = [*command[:audio_index], "-c:a", "aac", "-b:a", "192k", *command[audio_index + 2 :]]
    return subprocess.run(fallback, capture_output=True, text=True, check=False)


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
    encoder, output_codec, pixel_format, codec_preserved = _master_encoder(settings)
    lut_path = destination.with_name(f".{destination.stem}.cube")
    write_cube_lut(lut_path, correction, size=33)

    escaped_lut = str(lut_path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    video_filter = (
        f"lut3d=file='{escaped_lut}':interp=tetrahedral,format={pixel_format}"
        f"{_color_setparams(settings)}"
    )
    codec_args = (
        ["-c:v", encoder, "-preset", "medium", "-crf", "16", "-tag:v", "hvc1"]
        if output_codec == "hevc"
        else ["-c:v", encoder, "-preset", "medium", "-crf", "15", "-tag:v", "avc1"]
    )
    command = [
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
        *codec_args,
        *_color_metadata_args(settings),
        "-fps_mode",
        "passthrough",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(destination),
    ]
    try:
        result = _run_master_encode(command, destination)
    finally:
        lut_path.unlink(missing_ok=True)
    if result.returncode != 0:
        destination.unlink(missing_ok=True)
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"
        raise ValueError(f"Could not create corrected master: {detail}")

    output_settings = probe_source_video_settings(destination)
    return MasterExportResult(
        path=destination,
        codec_name=output_settings.codec_name,
        profile=output_settings.profile,
        pixel_format=output_settings.pixel_format,
        codec_preserved=codec_preserved,
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


def _mux_source_audio(video_only: Path, source: Path, destination: Path) -> str:
    ffmpeg = shutil.which("ffmpeg")
    source_has_audio = has_audio_stream(source)
    if ffmpeg is None:
        video_only.replace(destination)
        return "unavailable" if source_has_audio is not False else "source_has_no_audio"

    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(video_only),
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0?",
            "-map_metadata",
            "1",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-tag:v",
            "avc1",
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
    if result.returncode != 0:
        video_only.replace(destination)
        return "unavailable" if source_has_audio is not False else "source_has_no_audio"

    output_has_audio = has_audio_stream(destination)
    if source_has_audio is False:
        return "source_has_no_audio"
    if source_has_audio is True and output_has_audio is True:
        return "preserved"
    return "unavailable"


def write_corrected_video(
    video_path: str | Path,
    output_path: str | Path,
    correction: CorrectionPlan,
) -> VideoExportResult:
    source = Path(video_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    video_only = destination.with_name(f"{destination.stem}.video-only{destination.suffix}")
    video_only.unlink(missing_ok=True)

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise ValueError(f"Could not open video for export: {source}")

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if width <= 0 or height <= 0:
        capture.release()
        raise ValueError("Video does not expose a usable frame size.")

    writer = cv2.VideoWriter(
        str(video_only),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        capture.release()
        raise ValueError("Could not create corrected video writer.")

    try:
        while True:
            ok, bgr = capture.read()
            if not ok or bgr is None:
                break
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            corrected = apply_correction_array(rgb.astype(np.float32) / 255.0, correction)
            corrected_bgr = cv2.cvtColor(
                np.rint(corrected * 255.0).astype(np.uint8),
                cv2.COLOR_RGB2BGR,
            )
            writer.write(corrected_bgr)
    finally:
        capture.release()
        writer.release()

    try:
        audio_status = _mux_source_audio(video_only, source, destination)
    finally:
        video_only.unlink(missing_ok=True)

    return VideoExportResult(path=destination, audio_status=audio_status)
