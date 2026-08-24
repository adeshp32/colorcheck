# Video Color Consistency Checker

Version 1 of an AI-assisted color review tool for editors.

The app compares a target video against a reference image or reference video, builds a lighting/color drift report, exports a guarded corrected preview, and provides bounded correction guidance for common editors:

- DaVinci Resolve
- Adobe Premiere Pro
- Avid Media Composer
- iMovie

It also generates portable correction files:

- `recommended_correction.cube`
- `recommended_correction.cdl`
- `report.json`
- `report.html`
- `corrected_preview.mp4`
- `corrected_master.mov`
- editor-specific Markdown instructions

## What Version 1 Does

- Samples frames from a target video.
- Accepts either a still image or a sampled video as the reference look.
- Uses PyTorch tensors for image similarity and lighting drift metrics.
- Matches target frames against similar reference-video lighting moments when a reference clip is used.
- Estimates exposure, contrast, saturation, and color balance differences.
- Lets the user choose correction strength from 0% to 100%.
- Warns when the selected strength risks changing the original lighting setup.
- Applies guardrails so recommendations and preview exports stay conservative.
- Generates a browser-compatible H.264 corrected preview without modifying the original video and preserves source audio when present.
- Generates a high-quality editing master that preserves supported source codec, resolution, timing, bit depth, color metadata, and audio characteristics.
- Provides Docker and Kubernetes files for local deployment practice.

The original upload is never modified. Browser previews prioritize compatibility, while the separate editing master preserves supported source codec, resolution, timing, bit depth, HDR/color metadata, and audio characteristics. Video pixels must be re-encoded after a correction, so compressed output cannot be bit-for-bit identical to the source.

## Quick Start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Analyze a video:

```bash
vcc-analyze --reference path/to/reference.jpg --video path/to/video.mp4 --out reports/demo --strength 50 --lighting-threshold 60
vcc-analyze --reference path/to/reference_clip.mp4 --video path/to/video.mp4 --out reports/demo-video-ref --strength 45
```

Run the local API:

```bash
uvicorn video_color_checker.api:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://localhost:8000
```

The JSON endpoint requires the same ownership confirmation as the web form:

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -F reference=@path/to/reference.jpg \
  -F video=@path/to/video.mp4 \
  -F rights_confirmed=true
```

## Safety Model

Version 1 is intentionally guardrail-first. It does not rewrite your original footage. The generated preview video, LUT, and CDL are conservative recommendations designed to stay inside these limits:

- Exposure shift capped at about 0.35 stops.
- Saturation multiplier capped between 0.85 and 1.15.
- Contrast multiplier capped between 0.85 and 1.15.
- Per-channel color balance capped between 0.92 and 1.08.
- Recommendations are marked risky if estimated clipping exceeds guardrail limits.
- A lighting-shift score warns when the chosen strength is likely to alter the original lighting setup.

## Public Demo Safety

- Source uploads are renamed internally and deleted immediately after processing.
- Failed jobs are removed instead of retaining partial uploads.
- Generated results expire after six hours by default.
- Upload size, video duration, resolution, per-IP rate, and concurrent processing are limited.
- Download paths use strict job-ID and filename allowlists.
- Browser security headers and same-origin form checks are enabled.
- Internal stack traces and local filesystem paths are not returned to visitors.
- The Docker and Kubernetes configurations run without root privileges or Linux capabilities.

See [SECURITY.md](SECURITY.md) and [PRIVACY.md](PRIVACY.md) before operating a public instance.

## Public Hosting

The recommended first deployment is Railway using the included Dockerfile and `railway.toml`. It is the lowest-friction fit for the current synchronous video workflow. See [DEPLOYMENT.md](DEPLOYMENT.md) for exact limits, cost controls, and the longer-term Cloud Run/object-storage architecture.

## Kubernetes

Build and run locally:

```bash
docker build -t video-color-checker:local .
kubectl apply -f k8s/
kubectl port-forward service/video-color-checker 8000:80
```

Then open:

```text
http://localhost:8000
```
