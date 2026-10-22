# Reference Matcher Architecture

## Product contract

The learned system accepts a target photograph and a separate edited reference.
It predicts a bounded 33-by-33-by-33 RGB lookup table (LUT), not replacement
pixels. ONNX Runtime Web executes the exported model locally, and the existing
renderer applies the LUT before the editor's non-destructive adjustment stack.
The original photograph therefore remains available for strength changes,
masking, undo/redo, and full-resolution export.

## Why the model and editor remain separate

A global LUT can represent nonlinear exposure, tone, white-balance, palette,
saturation, curve, color-mixer, and grading behavior. It cannot infer an honest
crop, add photographic grain, restore missing detail, or know which subject the
user intends to mask without corresponding labels. Those tools remain explicit,
reversible operations. This separation keeps the learned suggestion useful while
preserving precise control.

| Editor capability                         | Learned role           | Runtime behavior                                                           |
| ----------------------------------------- | ---------------------- | -------------------------------------------------------------------------- |
| Reference palette and tone                | Direct                 | Target and reference condition a residual global LUT.                      |
| Exposure, tonal ranges, RGB curves        | Representable          | LUT supplies a starting treatment; controls remain independently editable. |
| HSL color mixer and four-way grading      | Representable          | LUT may reproduce the look; eight-band and tonal controls refine it.       |
| Radial/linear masks and range refinements | Compositional          | The same LUT strength can be applied globally or inside any enabled mask.  |
| Sharpen, vignette, monochrome, grain      | Deterministic          | Applied after learned color so users retain exact intent.                  |
| Crop, rotate, flip                        | Deterministic geometry | Applied after pixel processing and never predicted from FiveK.             |
| Preview, undo/redo, export                | Shared pipeline        | One serialized edit state drives preview and original-resolution export.   |

## Training curriculum

Real FiveK pairs teach photographic judgment from five professional editors.
They do not specify the exact parameters behind an arbitrary reference look.
The complementary synthetic curriculum applies one bounded editing recipe to
two unrelated raw scenes. The transformed reference and expected target then
share known exposure, contrast, gamma, channel balance, saturation, shadow,
highlight, and black-level intent. This forces the model to read the reference
rather than merely learning a generic enhancement.

Checkpoint selection follows that two-part contract. Every epoch receives
DeltaE76 scores for real validation pairs, shuffled real references, and
synthetic shared-style pairs on held-out scenes. The score starts with balanced
real/synthetic error and then rewards the real correct-reference gain or
penalizes its reversal. The untouched test split is evaluated only after
selection.

Three training-only controls defend against generic enhancement. The same target
is evaluated with its correct reference and a known-wrong style; the correct
reference must produce the closer result by a fixed margin. A second reference
from another scene carrying the same treatment must lead to a compatible LUT,
which discourages scene-content leakage. A small expert classifier trains the
shared reference features to preserve FiveK's editing-style signal. The extra
branches and classifier are omitted from ONNX, so browser inference remains one
target/reference pass through the original predictor.

Synthetic recipes also provide exact LUT supervision. Each labeled recipe is
evaluated over all 35,937 points of the 33-cube color lattice, so training covers
colors that may be absent from one image crop and directly optimizes the same
artifact later executed in the browser.
Full-cube labels are materialized only for training batches; validation and test
loaders avoid that unused memory and computation without changing their images
or metrics.

The encoder processes target and reference in one batch for a compact ONNX graph.
Its predictor uses source features, reference features, signed and absolute
differences, feature interactions, and channel statistics to blend eight learned
LUT bases. The complete model remains under one million parameters before
quantization.

The bases start from mild paired photographic anchors: warm/cool, higher/lower
contrast, higher/lower saturation, and opposing gamma curves. Their mean remains
near neutral, but their differences make reference-conditioned coefficients
visually and mathematically meaningful from the first update. Softmax preserves
a smooth convex mixture while every LUT value remains trainable.

Training and exported inference use 128-by-128 target/reference samples because
the output is a global color transform, not a spatial image. Held-out evaluation
uses 256-by-256 images for stronger structural measurements. The browser applies
the predicted LUT to the original-resolution pixels, so this optimization changes
analysis cost rather than final image dimensions or encoder quality.

## Evidence before deployment

A checkpoint is not copied into the website because training completed. The
untouched scene-level test split must establish all of the following:

1. Improvement over identity and the current bounded statistics matcher.
2. Better results with the correct reference than a shuffled reference.
3. Nontrivial response to reference changes without mean-weight or dominant-basis collapse.
4. Scene-clustered 95% confidence intervals for CIEDE2000, SSIM, PSNR, MAE,
   luminance, chroma, edge agreement, and clipping. All five expert variants
   remain observations, but one source photograph remains one resampling unit.
5. Separate evidence on real expert edits and exact synthetic reference pairs.
6. PyTorch-to-ONNX and FP32-to-INT8 rendered-pixel parity.
7. Browser artifact size, inference latency, peak memory, integrity, and fallback
   checks on representative mobile and desktop devices.

Quality gates require both a scene-clustered confidence interval above zero and
a predeclared minimum practical effect. A large test set therefore cannot promote
a change that is statistically detectable but too small to be useful.

Export and promotion are separate operations. Research artifacts may be emitted
for parity testing, but the manifest names no recommended production artifact
unless the checkpoint matches its evaluation summary, every held-out quality
gate passes, and INT8 rendered-pixel divergence stays within tolerance.

Wrong-reference controls always select a different FiveK expert label when the
batch permits it. Latency measures exactly one target/reference inference and LUT
construction; the extra control inference is excluded. Clipping is the percentage
of image pixels where at least one output channel reaches the display boundary.

Only a model that passes those gates replaces the current upstream enhancement
artifact. Manual editing remains available if model loading or inference fails.
