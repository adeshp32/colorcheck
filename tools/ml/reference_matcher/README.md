# Reference Matcher Training

This package trains ColorCheck's own compact, reference-conditioned 3D LUT
predictor. It is separate from the upstream pretrained enhancement model already
shipped in the browser.

## Goal in one sentence

Given an unedited target photograph and an edited reference photograph, predict
a bounded color transformation that moves the target toward the reference's
visual treatment without replacing the target's content or composition.

The model is deliberately a global color model. It learns tone, palette,
contrast, and saturation relationships through a 3D lookup table (LUT); it is
not a generative image model and it does not perform local segmentation.

## Data contract

The FiveK ZIP remains outside Git and is never redistributed. Its root must
contain `raw/`, `a/`, `b/`, `c/`, `d/`, and `e/`, with matching filenames in
every directory. A deterministic manifest assigns the source scene and all five
expert variants to one split, preventing scene leakage.

Each supervised sample consists of:

- the unedited target scene;
- a different scene edited by expert A, B, C, D, or E as the reference;
- that same expert's edit of the target scene as the expected output.

This is proxy supervision for reference matching, not proof of a universally
correct photographic style. The shuffled-reference evaluation checks whether
the model uses the reference rather than learning only generic enhancement.

Training uses a two-source curriculum. Half of the default training pairs use
real FiveK expert edits. The other half apply one deterministic, bounded editing
recipe to two unrelated raw scenes: one becomes the reference and the other the
expected target. These synthetic pairs provide exact supervision for arbitrary
exposure, contrast, gamma, white-balance, saturation, shadow, highlight, and
black-level relationships. The held-out report evaluates real expert edits and
synthetic reference transfer separately; both must pass their evidence gates.

Checkpoint selection uses the same balance before the test set is touched.
Every epoch is evaluated on real expert edits and exact synthetic shared-style
pairs from held-out scenes. The arithmetic mean of their DeltaE76 scores selects
best.pt, so neither photographic polish nor reference responsiveness can choose
the deployed model alone.

Training also includes a pairwise wrong-reference objective. For each batch, the
true reference and a reference carrying a different style identifier are scored
together. The true reference must reconstruct the expected edit by a measurable
margin. This targets reference use directly while adding no parameters or work
to exported browser inference.

## Reproducible commands

Create a dedicated environment, then run a short end-to-end smoke experiment:

```sh
python3 -m venv .local/reference-matcher-env
.local/reference-matcher-env/bin/pip install -r tools/ml/reference_matcher/requirements.txt
.local/reference-matcher-env/bin/python -m tools.ml.reference_matcher.train \
  --dataset-zip "/Volumes/Untitled/archive (2).zip" \
  --epochs 1 --max-train-pairs 32 --max-validation-pairs 16
```

After the smoke run succeeds, benchmark one complete epoch before selecting the
final epoch count:

```sh
.local/reference-matcher-env/bin/python -m tools.ml.reference_matcher.train \
  --dataset-zip "/Volumes/Untitled/archive (2).zip" \
  --epochs 1
```

Export the best checkpoint and calibrate INT8 quantization with held-out images:

```sh
.local/reference-matcher-env/bin/python -m tools.ml.reference_matcher.export_onnx \
  --checkpoint .local/reference-matcher/best.pt \
  --splits .local/reference-matcher/splits.json \
  --evaluation-summary .local/reference-matcher/summary.json \
  --dataset-zip "/Volumes/Untitled/archive (2).zip"
```

The exporter always produces FP32 and calibrated INT8 QDQ models. Learned LUT
bases are stored as UINT8 because they dominate model size. The manifest
recommends INT8 only when it is smaller and both complete-LUT and rendered-pixel
differences remain within declared FP32 error bounds. Browser compatibility and
held-out image quality remain required deployment gates.

Long runs write `last.pt` every epoch with optimizer and scheduler state. Resume
an interrupted experiment without restarting it:

```sh
.local/reference-matcher-env/bin/python -m tools.ml.reference_matcher.train \
  --dataset-zip "/Volumes/Untitled/archive (2).zip" \
  --epochs 30 --resume .local/reference-matcher/last.pt
```

## Kaggle GPU workflow

The Kaggle notebook uses the same modules as local training, but reads extracted
files from `/kaggle/input/adobe-fivek`. This avoids repeated random seeks through
the 28.5 GB ZIP on removable media. CUDA mixed precision is enabled automatically,
while reported metrics are still calculated in float32.

The first private notebook version is intentionally a smoke run: 256 training
pairs and 64 validation/test pairs for one epoch. It proves that Kaggle can mount
the data, import the exact repository code, train on its GPU, save checkpoints,
and complete every evaluation. Full training is enabled only after that run is
reviewed.

The optimized curriculum trains and exports at 128-by-128 because the model
predicts one global LUT rather than spatial output. Validation and testing remain
at 256-by-256 to retain stronger edge and local-structure evidence. A bounded
per-worker tensor cache avoids decoding the same resized FiveK scene repeatedly.
None of these choices reduce the user's export dimensions: the browser applies
the resulting LUT to the original-resolution photograph.

For an extracted local or Kaggle dataset, use `--dataset-root` instead of
`--dataset-zip`:

```sh
python -m tools.ml.reference_matcher.train \
  --dataset-root /kaggle/input/adobe-fivek \
  --output-dir /kaggle/working/colorcheck-reference-matcher \
  --epochs 5 --batch-size 16 --workers 2 --mixed-precision auto
```

`train.py` saves three human-readable experiment records alongside checkpoints:

- `splits.json` identifies the exact photographs in each partition;
- `history.json` records training time and validation metrics per epoch; and
- `summary.json` compares the final model against unchanged images and incorrect
  shuffled references.

The Kaggle notebook also writes `held-out-comparisons.jpg`, a deterministic
contact sheet of source, reference, expected, learned, and statistics-baseline
images. It supports qualitative review for casts, clipping, and photographic
plausibility; it never overrides the quantitative deployment gates.

The final held-out evaluation is intentionally broader than the training loss.
It reports scene-clustered 95% bootstrap confidence intervals for CIEDE2000,
SSIM, PSNR, luminance, chroma, edges, clipping, and absolute error. The five expert
variants remain measured, but confidence resampling treats their shared source
photograph as one independent unit. It compares
the model against both an identity baseline and ColorCheck's existing bounded
channel-statistics matcher, stratifies results by FiveK expert, checks whether a
wrong reference degrades performance, detects collapsed LUT-basis usage, and
records model/LUT latency, CUDA peak memory, and parameter count. Explicit
evidence gates must pass before a checkpoint is considered for ONNX export.
The export manifest additionally verifies that its checkpoint epoch matches that
summary and withholds a recommended browser artifact unless both the held-out
quality gates and rendered-pixel quantization tolerances pass.

After export, set REFERENCE_MODEL_ARTIFACT_DIR to the export directory and run
npm run test:reference-model. The deterministic Chromium probe uses the exact
ONNX Runtime Web package shipped by the site.

The manifest stores no dataset photograph. It reconstructs two portable
synthetic inputs and compares 64 sparse LUT values between native ONNX Runtime
and the site's WebAssembly runtime.

## Honest interpretation

Running this pipeline performs original PyTorch training: gradients update the
encoder, coefficient predictor, and learned LUT bases. FiveK provides the
supervision; it does not make the resulting model automatically superior. Keep
the dataset citation and research license with experiment records, and do not
commit photographs, checkpoints, or caches to the repository.
