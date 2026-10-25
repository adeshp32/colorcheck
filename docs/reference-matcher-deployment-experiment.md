# Reference matcher: deployment-oriented selector experiment

## Objective

Reduce the number of photographs on which reference matching looks worse than
ColorCheck's current statistics matcher. The frozen v3 LUT model improves
average color error, but its fresh-scene audit lost to the current matcher on
72 of 160 targets. V4's stronger-edit training improved the relevant
validation subset by only 0.258 Delta E 2000, below its predeclared 0.5 gate.
Neither result supports replacing the live matcher.

The next question is whether a **small, locally executable quality selector**
can choose between the frozen v3 LUT output and the unchanged statistics
matcher on each photograph. This is a new supervised model, not another LUT
fine-tune. Expert edits supply training labels only; they are unavailable and
must never be required at inference. The selector should add negligible
browser cost and must have a deterministic fallback to the current matcher.

## Data and leakage controls

- Use the pinned TST100K manifest. Exclude every target or reference scene in
  v3 train/validation/test, the 160-scene fresh audit, and the sealed v4
  holdout. Exclude a scene from all selector partitions if it appears in any
  other partition as either target or reference.
- Before fitting anything, deterministically select 1,024 training, 256
  validation, and 256 final-holdout target scenes using one recorded seed.
  Save row lists and SHA-256 checksums. If the counts or scene-disjointness
  checks fail, stop before fetching images or training.
- Keep all images and expert edits in private Kaggle scratch. Download only
  small metrics and contact sheets for review; do not publish dataset copies.
- Generate candidate outputs with the exact frozen v3 checkpoint and current
  statistics matcher. Do not refit either image-processing method. Derive the
  selector's binary training label from which candidate has lower Delta E
  2000 against the expert edit, with a documented tie band of 0.25. Never use
  ground-truth edit size, expert pixels, or candidate errors as input features.

## Model and validation rule

Train a regularized logistic regression on compact features available from
the source, reference, and two candidate outputs: luminance/chroma summaries,
candidate color-shift magnitude, clipping, and candidate disagreement. Record
the exact feature schema, normalization statistics, coefficient vector, and
random seed. A linear selector is deliberately small enough to port to plain
JavaScript and check numerically against Python; no server inference is needed.

Fit coefficients on the selector training partition only. Use validation
binary log loss to choose one of three predeclared regularization strengths
(`C` = 0.1, 1, 10), breaking ties toward stronger regularization. Then test
decision thresholds `0.50, 0.55, ..., 0.95` on the same validation partition;
choose the threshold with the greatest validation mean Delta E gain over
always using statistics matching, breaking ties toward the higher threshold.
The chosen threshold must satisfy all of these validation constraints:

1. At least 90% of photos are no more than 0.5 Delta E worse than statistics
   matching; report the full worse-than-2.0 tail as well.
2. Mean gain over statistics matching is at least 0.5 Delta E, with a paired
   95% bootstrap interval whose lower bound is above zero.
3. The selected output retains a positive correct-reference advantage over a
   deliberately wrong reference.
4. The LUT is selected for at least 20% of photos, so always choosing the
   existing matcher cannot pass as a new capability.
5. Mean SSIM falls by no more than 0.005 and clipping rises by no more than
   one percentage point versus statistics matching.

If no candidate and threshold meet every rule, stop. Do not look at final
images or revise these gates after seeing them. The selector predicts a
**relative safety decision**, not a claim that either result is objectively
beautiful.

## One-time final evaluation and deployment gates

After locking the selector, evaluate once on the sealed 256-scene final
holdout. Compare selector, v3-only, statistics-only, unchanged source, and
wrong-reference controls using paired photo-level bootstrap intervals,
per-photo wins/losses, Delta E 2000, SSIM, edge error, clipping, and fixed-seed
weak/random/strong contact sheets. The same validation thresholds must hold
on final data; do not select another threshold or checkpoint from these
results. Inspect results at original photo resolution as a separate quality
check; the 128-pixel benchmark is insufficient for a release decision.

Even a final benchmark pass is **not deployment**. Before offering this as a
user-visible experimental option, verify Python-to-browser numerical parity
for both v3 LUT and selector, run phone memory/latency tests, inspect hard
photographs with a human reviewer, preserve the existing matcher as an
immediate fallback, and make no unsupported quality claims. Failure at any
gate leaves the live editor unchanged.

## Budget

Run the manifest preflight on Kaggle CPU first. Stage only selected images at
the existing paced request rate and never overlap GPU jobs. Check live Kaggle
quota before a GPU run and preserve at least two hours. The selector itself
can train on CPU; candidate generation may use one time-capped GPU session if
CPU inference is impractical. Check the user's 40% weekly Codex usage ceiling
before implementation and pause before crossing it.
