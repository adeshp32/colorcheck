from __future__ import annotations

import shutil
import subprocess

import cv2
import pytest

from colorcheck.exports.video import (
    has_audio_stream,
    probe_source_video_settings,
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
    assert video_codec(output) == "h264"
    assert has_audio_stream(output) is True
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
