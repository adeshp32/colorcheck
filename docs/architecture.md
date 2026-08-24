# Architecture

ColorCheck uses a small layered architecture organized around responsibilities rather than frameworks.

## Module Boundaries

| Module | Owns | May depend on |
| --- | --- | --- |
| `colorcheck.models` | Shared typed analysis and export contracts | Standard library |
| `colorcheck.analysis` | Frame sampling, perceptual metrics, correction bounds, pipeline orchestration | Models, exporters |
| `colorcheck.exports` | Video encoding, LUT/CDL generation, reports, editor guidance | Models, correction primitives |
| `colorcheck.web` | HTTP routes, upload validation, rate limits, temporary job access, HTML pages | Config, analysis pipeline |
| `colorcheck.config` | Environment-backed runtime settings | Standard library |
| `colorcheck.cli` | Local command-line workflow | Analysis pipeline |

The analysis and export layers do not import the web application. This keeps the core workflow reusable from FastAPI, the CLI, tests, and future background workers.

## Request Lifecycle

1. The web boundary validates request origin, size, rate, and processing capacity.
2. Uploaded media is renamed, written with byte limits, and validated with Pillow or FFprobe.
3. The analysis pipeline samples frames and computes reference-aware perceptual metrics.
4. Correction logic creates a bounded plan and evaluates clipping and lighting-shift risk.
5. The exporter applies the correction once while producing the quality-preserved master, using supported hardware encoding when available.
6. A browser-friendly preview is derived from the completed master without repeating the color correction.
7. Exporters write the LUT/CDL files, reports, and editor guides.
8. Source uploads are deleted in a `finally` block; only allowlisted generated artifacts remain.
9. Expired job directories are removed according to the configured retention period.

## Deployment Model

Version 1 uses one process and one in-memory concurrency slot. This is deliberate for a portfolio deployment with CPU-heavy synchronous video work. The next scaling boundary is an object store plus a durable queue and isolated workers, not additional complexity inside the analysis modules.
