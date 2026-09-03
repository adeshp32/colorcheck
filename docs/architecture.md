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

1. The browser decodes candidate frames locally and selects a compact, visually diverse sample set.
2. The web boundary validates request origin, size, rate, disk capacity, and queue capacity.
3. A persistent job record is written before a single background worker starts analysis.
4. Cached reference features are compared with each selected target frame.
5. Correction logic creates a bounded plan and evaluates clipping and lighting-shift risk.
6. Reports, LUT/CDL files, and editor guides are retained temporarily; analysis media is deleted.
7. Trim regions, crop, text, lighting, tint, B&W, and correction remain a browser-owned edit recipe.
8. A requested preview or master is rendered once by FFmpeg and streamed directly to the browser.
9. The uploaded source is deleted in the stream cleanup path; no corrected video is stored.

## Deployment Model

The Oracle release uses one application process, a persistent disk-backed job queue, one analysis worker, and one rendering slot. This keeps memory and CPU bounded on the free VM. A higher-traffic deployment can retain the same contracts while moving temporary upload chunks and queue state to dedicated services.
