from __future__ import annotations

import argparse
import json
from pathlib import Path

from colorcheck.analysis.pipeline import analyze_video


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze target footage against an image or video color reference."
    )
    parser.add_argument("--reference", required=True, help="Path to the reference image or video.")
    parser.add_argument("--video", required=True, help="Path to the target video.")
    parser.add_argument("--out", required=True, help="Directory for generated outputs.")
    parser.add_argument(
        "--samples",
        type=int,
        default=24,
        help="Number of frames to sample from the target video.",
    )
    parser.add_argument(
        "--strength",
        type=int,
        default=50,
        help="Correction strength percentage for preview/LUT/CDL output.",
    )
    parser.add_argument(
        "--lighting-threshold",
        type=int,
        default=60,
        help="Warn when the selected correction shifts lighting beyond this percentage.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report, written = analyze_video(
        reference_path=Path(args.reference),
        video_path=Path(args.video),
        out_dir=Path(args.out),
        sample_count=args.samples,
        correction_strength_percent=args.strength,
        lighting_shift_threshold_percent=args.lighting_threshold,
    )
    result = {
        "summary": report.summary.__dict__,
        "correction": report.correction.__dict__,
        "guardrails": report.guardrails.__dict__,
        "export_settings": report.export_settings.__dict__,
        "lighting_shift": report.lighting_shift.__dict__,
        "outputs": {key: str(path) for key, path in written.items()},
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
