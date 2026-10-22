# Reference Matcher Pilot v10

## Decision

Do not deploy this checkpoint. The run completed successfully and established a
useful learning direction, but it did not prove real-photo reference matching.

## Experiment

- Dataset: MIT-Adobe FiveK, with scene-disjoint train, validation, and test sets.
- Training: 5,000 pairs, three epochs, 128-pixel model inputs.
- Evaluation: 500 real expert pairs and 500 exact synthetic reference pairs at
  256 pixels.
- Model: 956,032-parameter reference-conditioned mixture of eight 33-cube LUTs.
- Best checkpoint: epoch 3.

## What improved

On held-out real expert edits, the model reduced mean CIEDE2000 from 10.521 for
the unchanged source to 9.787, an average improvement of 0.734. The later
scene-clustered rerun placed its 95% interval at 0.551 to 0.895 across 100 source
scenes and 500 expert observations. It also reduced clipping by 0.871 percentage
points and ran the model plus LUT prediction in about 0.78 milliseconds per image
on the Kaggle T4 measurement path.

On exact synthetic styles, the correct reference reduced CIEDE2000 by 1.330
relative to a shuffled reference. The scene-clustered 95% interval was 1.132 to
1.535. This demonstrates that the architecture can learn a reference-conditioned
transform when the desired relationship is identifiable.

## What failed

On real FiveK expert edits, using the correct reference improved CIEDE2000 by
only 0.028 relative to a shuffled reference after the current deterministic
evaluation path was rerun. Its scene-clustered 95% interval crossed zero widely
(-0.093 to 0.145). Mean SSIM was also 0.002 lower than the unchanged source, with
a confidence interval that crossed zero. The combined deployment decision was
therefore false.

The correct interpretation is that the pilot learned a general photographic
enhancement prior and exact synthetic conditioning, but not a dependable real
reference signal. More epochs alone would not address that evidence.

## Response

The next pilot strengthens reference learning without enlarging browser
inference:

1. Raise the correct-versus-wrong reference ranking weight from 0.25 to 1.0.
2. Train each target against two different scenes carrying the same treatment
   and penalize inconsistent LUT predictions.
3. Add a training-only FiveK expert classifier to make shared encoder features
   retain editing style rather than reference content.
4. Report every auxiliary loss independently and retain the same held-out gates.

The v10 checkpoint and dataset remain outside Git. This document records only
aggregate measurements and the decision they support.
