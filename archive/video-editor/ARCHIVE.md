# Archived Video Application

This folder preserves ColorCheck's former Python/FastAPI/FFmpeg application,
video editing work, tests, deployment manifests, historical screenshots, and
unfinished experimental training code. Existing local changes were retained.

The active product is now the browser-only photo editor at the repository root.
Nothing in this archive is imported by that editor or run by its CI.

## Historical layout

- `src/colorcheck/`: analysis, media exports, edit plans, web application, and CLI.
- `tests/`: former Python regression tests.
- `scripts/`: former benchmarking, fixtures, and training-data preparation.
- `deploy/`, `k8s/`, `compose.yaml`, `Dockerfile`: former backend deployment.
- `docs/`, `README.md`: historical documentation, not current product claims.

To investigate the previous application, work from this directory and follow
its own `pyproject.toml`. Paths in historical documentation may assume the old
repository layout. The archive is not an actively maintained deployment target.
Training scaffolding is experimental and does not establish that a model was trained.

Uploaded media, private credentials, local virtual environments, and runtime
storage are not included. The running old website is an independent deployment
and has not been shut down by this repository reorganization.
