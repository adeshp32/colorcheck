# Containerized Model Export

Docker packages the offline PyTorch-to-ONNX export and numerical validation job.
It is not a web server or a production dependency. Visitors do not need Docker,
and their photographs are not processed by this container.

## Run

From the repository root:

```sh
mkdir -p .local/adaptive-lut-weights .local/ml-container-output
docker compose -f compose.ml.yaml build model-export
LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) \
  docker compose -f compose.ml.yaml run --rm model-export
```

For an SSD, create the two directories on that drive and set `ML_WEIGHTS_DIR`
and `ML_OUTPUT_DIR` to their absolute paths. Docker Desktop may need permission
to share that drive. The job does not need your image dataset.

The initial run downloads the two upstream checkpoints if the weights directory
is empty. Later runs verify their SHA-256 hashes before deserializing them.
Outputs are `enhancement.onnx` and `manifest.json`. They are placed in a separate
output directory, not automatically copied into the deployed app. Review the
manifest and browser checks before deliberately promoting an artifact.

Validate a generated artifact through the editor without replacing its shipped files:

```sh
ML_TEST_ARTIFACT_DIR="$PWD/.local/ml-container-output" npm run test:browser
```

This test uses only the specified model/manifest for its main browser page. It
checks browser/PyTorch agreement, enhancement, export, and the normal fallback.

With cached checkpoints, the run can be isolated from the network:

```sh
LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) \
  docker compose -f compose.ml.yaml -f tools/ml/compose.offline.yaml run --rm model-export
```

## Boundaries and reproducibility

- The Python base image is pinned by a multi-platform digest.
- CPU-only ARM64 and x86-64 PyTorch wheels are pinned by version and hash.
- Direct Python dependencies are pinned; transitive dependencies are not fully locked.
- The image copies only the export script, dependency list, and license.
- The run is non-root with a read-only root filesystem, dropped capabilities,
  two CPUs, and a 2 GB memory limit. Only its explicit bind mounts and temporary
  filesystem are writable.
- No ports, container service, GPU, Kubernetes cluster, or model-training claim
  is involved.
- The export checks ONNX validity and compares outputs against PyTorch fixtures.
  Numeric tolerances include the documented flat-image normalization exception.
- Architecture-specific floating-point behavior can differ. A reproducible
  workflow does not promise byte-identical artifacts on every architecture.

The original model/data provenance still needs review before public distribution;
containerizing it does not change licensing or privacy obligations.

## Verified platform

The container build and offline export were verified on Linux ARM64 through
Docker Desktop on Apple Silicon. All four numerical fixture checks passed their
documented tolerances. The x86-64 wheel is available and configured, but that
platform has not been run locally; do not claim it has been tested.
