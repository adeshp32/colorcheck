# Reference Matcher Pilot v11

## Decision

Do not deploy this checkpoint. V11 strengthened validation conditioning and
general correction quality, but the strict held-out test did not establish a
dependable advantage from the correct real-photo reference.

## Experiment

- Dataset: MIT-Adobe FiveK with scene-disjoint train, validation, and test sets.
- Training: 5,000 pairs, three epochs, 128-pixel model inputs.
- Evaluation: 500 real expert pairs and 500 exact synthetic pairs at 256 pixels.
- Model: 956,032-parameter mixture of eight learned 33-cube LUTs.
- Best checkpoint: epoch 3.

## Evidence

Real validation correct-reference gain increased from 0.234 DeltaE76 after the
first epoch to 0.332 after the third. On the stricter held-out evaluation, the
model improved CIEDE2000 over the unchanged source by 0.846, with a scene-clustered
95% interval of 0.687 to 0.994. This was about 15% larger than v10's mean gain.
The SSIM change also moved from negative in v10 to positive in v11, although its
confidence interval still crossed zero.

The held-out correct-reference advantage was only 0.028 CIEDE2000, with a 95%
interval from -0.078 to 0.130. V11 therefore passed five of seven real-photo
evidence gates but failed structural certainty and correct-reference
discrimination. Exact synthetic reference transfer passed all seven gates.

## Response

V12 targets the two remaining failures without turning the model into a heavy
image generator:

1. Add differentiable RGB-and-luminance histograms for tonal-distribution context.
2. Rank correct and wrong references in perceptual Lab as well as raw RGB.
3. Train on 12,000 pairs over five epochs with a larger share of real expert edits.
4. Preserve the same 500-pair held-out controls and predeclared deployment gates.

The v11 checkpoint and dataset remain outside Git. This report records aggregate
measurements and the resulting decision.
