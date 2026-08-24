from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from time import perf_counter

from colorcheck.exports.video import probe_source_video_settings, write_corrected_exports
from colorcheck.models import CorrectionPlan


def _segment_source(source: Path, destination: Path, seconds: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required for the export benchmark.")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-t",
            str(seconds),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c",
            "copy",
            str(destination),
        ],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark ColorCheck's corrected exports.")
    parser.add_argument("video", type=Path)
    parser.add_argument("--seconds", type=int, default=6)
    parser.add_argument("--out", type=Path, default=Path("reports/export-benchmark"))
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    segment = args.out / "source-segment.mov"
    preview = args.out / "corrected-preview.mp4"
    master = args.out / "corrected-master.mov"
    _segment_source(args.video, segment, max(1, args.seconds))

    correction = CorrectionPlan(
        exposure_stops=0.18,
        contrast_multiplier=1.04,
        saturation_multiplier=1.06,
        channel_gains=(1.03, 1.0, 0.97),
        lift_offset=(0.0, 0.0, 0.0),
        confidence=0.9,
        rationale=["Stable benchmark correction."],
    )
    started_at = perf_counter()
    result = write_corrected_exports(segment, preview, master, correction)
    elapsed_seconds = perf_counter() - started_at
    source_settings = probe_source_video_settings(segment)
    master_settings = probe_source_video_settings(master)
    print(
        json.dumps(
            {
                "elapsed_seconds": round(elapsed_seconds, 2),
                "source": source_settings.__dict__,
                "master": master_settings.__dict__,
                "encoder": result.master.encoder_name,
                "hardware_accelerated": result.master.hardware_accelerated,
                "audio_status": result.preview.audio_status,
                "preview_bytes": preview.stat().st_size,
                "master_bytes": master.stat().st_size,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
