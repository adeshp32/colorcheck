from __future__ import annotations

import shutil
import subprocess

import cv2
import pytest

import colorcheck.exports.video as video_exports
from colorcheck.exports.video import (
    MasterExportResult,
    SourceVideoSettings,
    VideoExportResult,
    has_audio_stream,
    probe_source_video_settings,
    write_corrected_exports,
    write_corrected_master,
    write_corrected_video,
)
from colorcheck.models import CorrectionPlan


def identity_correction() -> CorrectionPlan:
    return CorrectionPlan(
        exposure_stops=0.0,
        contrast_multiplier=1.0,
        saturation_multiplier=1.0,
        channel_gains=(1.0, 1.0, 1.0),
        lift_offset=(0.0, 0.0, 0.0),
        confidence=1.0,
        rationale=[],
    )


def video_codec(video_path) -> str:
    result = subprocess.run(
        [
            shutil.which("ffprobe") or "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def media_stream_hash(video_path, stream: str) -> str:
    result = subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-v",
            "error",
            "-i",
            str(video_path),
            "-map",
            stream,
            "-c",
            "copy",
            "-f",
            "hash",
            "-hash",
            "sha256",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required for audio export",
)
def test_corrected_video_preserves_source_audio(tmp_path) -> None:
    source = tmp_path / "source-with-audio.mp4"
    output = tmp_path / "corrected.mp4"
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x48:r=8:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
            "-shortest",
            str(source),
        ],
        check=True,
    )

    result = write_corrected_video(source, output, identity_correction())
    capture = cv2.VideoCapture(str(output))

    assert result.path == output
    assert result.audio_status == "preserved"
    assert output.exists()
    assert capture.isOpened()
    assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) > 0
    assert (int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))) == (
        64,
        48,
    )
    assert video_codec(output) == "h264"
    assert has_audio_stream(output) is True
    assert not list(tmp_path.glob("*.video-only.*"))
    capture.release()


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required for master export",
)
def test_corrected_master_preserves_hevc_main10_hdr_characteristics(tmp_path) -> None:
    source = tmp_path / "source-main10-hlg.mov"
    output = tmp_path / "corrected-master.mov"
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=64x48:r=8:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-vf",
            (
                "setparams=range=limited:color_primaries=bt2020:"
                "color_trc=arib-std-b67:colorspace=bt2020nc"
            ),
            "-c:v",
            "libx265",
            "-preset",
            "ultrafast",
            "-x265-params",
            "log-level=error",
            "-pix_fmt",
            "yuv420p10le",
            "-tag:v",
            "hvc1",
            "-color_range",
            "tv",
            "-colorspace",
            "bt2020nc",
            "-color_trc",
            "arib-std-b67",
            "-color_primaries",
            "bt2020",
            "-c:a",
            "aac",
            "-shortest",
            str(source),
        ],
        check=True,
    )

    result = write_corrected_master(source, output, identity_correction())
    settings = probe_source_video_settings(output)

    assert result.path == output
    assert result.codec_preserved
    assert settings.codec_name == "hevc"
    assert settings.profile == "Main 10"
    assert settings.pixel_format == "yuv420p10le"
    assert (settings.width, settings.height) == (64, 48)
    assert settings.color_space == "bt2020nc"
    assert settings.color_transfer == "arib-std-b67"
    assert settings.color_primaries == "bt2020"
    assert has_audio_stream(output) is True
    assert media_stream_hash(source, "0:a:0") == media_stream_hash(output, "0:a:0")
    assert result.encoder_name in {"hevc_videotoolbox", "libx265"}
    assert not list(tmp_path.glob(".*.cube"))


def test_videotoolbox_plan_preserves_hevc_main10(monkeypatch) -> None:
    settings = SourceVideoSettings(
        codec_name="hevc",
        profile="Main 10",
        pixel_format="yuv420p10le",
        width=3840,
        height=2160,
        color_range="tv",
        color_space="bt2020nc",
        color_transfer="arib-std-b67",
        color_primaries="bt2020",
    )
    monkeypatch.setattr(video_exports.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        video_exports,
        "_available_video_encoders",
        lambda: frozenset({"hevc_videotoolbox"}),
    )

    plan = video_exports._videotoolbox_master_plan(settings)

    assert plan is not None
    assert plan.name == "hevc_videotoolbox"
    assert plan.pixel_format == "p010le"
    assert plan.hardware_accelerated
    assert "main10" in plan.arguments


def test_corrected_exports_builds_preview_from_completed_master(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.mov"
    master_path = tmp_path / "master.mov"
    preview_path = tmp_path / "preview.mp4"
    calls = []

    def fake_master(video_path, output_path, correction):
        calls.append(("master", video_path, output_path, correction))
        return MasterExportResult(
            path=master_path,
            codec_name="hevc",
            profile="Main 10",
            pixel_format="yuv420p10le",
            codec_preserved=True,
            encoder_name="hevc_videotoolbox",
            hardware_accelerated=True,
        )

    def fake_preview(video_path, output_path, correction=None):
        calls.append(("preview", video_path, output_path, correction))
        return VideoExportResult(path=preview_path, audio_status="preserved")

    monkeypatch.setattr(video_exports, "write_corrected_master", fake_master)
    monkeypatch.setattr(video_exports, "write_corrected_preview", fake_preview)

    result = write_corrected_exports(
        source,
        preview_path,
        master_path,
        identity_correction(),
    )

    assert result.master.path == master_path
    assert result.preview.path == preview_path
    assert calls[0][0] == "master"
    assert calls[1] == ("preview", master_path, preview_path, None)
