# ColorCheck

[![CI](https://github.com/adeshp32/colorcheck/actions/workflows/ci.yml/badge.svg)](https://github.com/adeshp32/colorcheck/actions/workflows/ci.yml)

Reference-aware, guardrail-first video color intelligence for editors.

ColorCheck compares target footage with an image or video reference, measures perceptual color and lighting drift with PyTorch, and produces conservative corrections without modifying the source. It generates browser previews, quality-preserved editing masters, LUT/CDL files, structured reports, and workflow guidance for DaVinci Resolve, Premiere Pro, Avid Media Composer, and iMovie.

## Capabilities

- Match target frames against a still or lighting-similar moments from a reference clip.
- Measure structural similarity, perceptual color distance, luminance, contrast, saturation, and temperature drift.
- Recommend bounded exposure, contrast, saturation, and channel-balance adjustments.
- Let editors control correction strength and define a lighting-preservation threshold.
- Preserve source audio in the H.264 preview when an audio stream is present.
- Preserve supported codec, resolution, timing, bit depth, color metadata, and audio characteristics in the editing master.
- Use Apple VideoToolbox automatically on native macOS for high-fidelity hardware encoding, with portable software fallbacks.
- Export individual CUBE, CDL, JSON, HTML, MP4, MOV, and editor-guide files.

## Architecture

```text
src/colorcheck/
|-- analysis/   # Perceptual metrics, correction logic, and orchestration
|-- exports/    # Video, LUT, report, and editor-guide generation
|-- web/        # FastAPI routes, browser pages, and upload security
|-- config.py   # Environment-backed runtime limits
|-- models.py   # Shared typed domain models
`-- cli.py      # Command-line entry point
```

The dependency direction is intentionally simple: interfaces call the analysis pipeline, the pipeline coordinates domain logic and exporters, and lower-level modules never depend on the web layer. See [Architecture](docs/architecture.md) for the complete request and data lifecycle.

## Quick Start

Requirements: Python 3.11 or newer and FFmpeg.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Start the web application:

```bash
uvicorn colorcheck.web.app:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

Run the CLI:

```bash
colorcheck \
  --reference path/to/reference.jpg \
  --video path/to/video.mp4 \
  --out reports/demo \
  --strength 50 \
  --lighting-threshold 60
```

Run with Docker:

```bash
docker compose up --build
```

## Output Contract

| File | Purpose |
| --- | --- |
| `corrected_preview.mp4` | Browser-compatible H.264 preview, capped at 1080p, with source audio when available |
| `corrected_master.mov` | High-quality editing master with supported source characteristics preserved |
| `recommended_correction.cube` | Portable 3D LUT |
| `recommended_correction.cdl` | ASC CDL correction values |
| `report.html` | Human-readable analysis |
| `report.json` | Structured analysis data |
| `*_steps.md` | Editor-specific application guidance |

Video pixels must be re-encoded after correction, so a corrected file cannot be bit-for-bit identical to the source. ColorCheck never modifies the original upload.

The optimized exporter corrects and encodes the quality-preserved master once, then derives the browser preview from that completed master. See the reproducible [performance notes](docs/performance.md) for benchmark and fidelity results.

## Safety Model

- Exposure is capped at approximately 0.35 stops.
- Contrast and saturation multipliers remain between 0.85 and 1.15.
- Per-channel balance remains between 0.92 and 1.08.
- Lighting-shift and clipping-risk checks warn before a correction becomes destructive.
- Source uploads receive generic internal names and are deleted immediately after processing.
- Generated jobs expire automatically and are reachable only through unguessable job identifiers.
- Upload size, duration, resolution, request rate, and processing concurrency are bounded.
- The release container runs as a non-root user with a read-only filesystem and no Linux capabilities.

Read the [security policy](.github/SECURITY.md) and [privacy notes](docs/privacy.md) before operating a public instance.

## Verification

```bash
ruff check src tests
pytest -q
docker build -t colorcheck:local .
```

GitHub Actions runs the lint and test suite on every push and pull request. Dependabot checks Python, Docker, and GitHub Actions dependencies weekly.

## Deployment

The first public deployment target is Railway using the included `Dockerfile` and `railway.toml`. The current synchronous pipeline is intentionally limited to one analysis at a time. See the [deployment guide](docs/deployment.md) for resource limits, cost controls, and the asynchronous growth path.

Kubernetes manifests are available in [`deploy/kubernetes`](deploy/kubernetes):

```bash
docker build -t colorcheck:local .
kubectl apply -f deploy/kubernetes/
kubectl port-forward service/colorcheck 8000:80
```
