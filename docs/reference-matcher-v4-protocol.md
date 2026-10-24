# Reference matcher v4: predeclared experiment

## Question

Can a training-only emphasis on stronger intended edits fix the v3 model's
under-correction without sacrificing its structure, clipping, or ability to
follow the correct reference? This is a controlled research experiment, not a
website release. The hypothesis comes from the completed visual audits; their
test images and scores must not choose a v4 checkpoint or tune its weights.

## Fixed inputs and training change

- Mount the private v3 training output and warm-start its selected epoch-8
  checkpoint. Reuse **only** its 1,024 training and 160 validation triplets,
  pinned TST100K revision, 128-pixel training images, and compact eight-basis
  33-cube LUT architecture. Never train on its 320 test triplets or the later
  160-scene fresh audit.
- Run four more epochs with AdamW learning rate `0.0001`, batch size 8, two
  image-loading workers, random seed `9103`, and the same mixed-precision policy. Keep the v3
  reconstruction, perceptual color, structural, smoothness, monotonicity,
  wrong-reference ranking, and neutral-reference losses unchanged.
- Add exactly two training-only terms. For each image, measure the mean absolute
  RGB difference between source and expert edit. Set an importance weight to
  `clamp(0.75 + difference / batch_mean_difference, 0.75, 2.0)`, then normalize
  weights to mean 1. Add `0.25 * weighted_pixel_L1` to the existing loss. Also
  add `0.25 * channel_mean_L1`, the absolute distance between the three output
  channel means and the expert edit's channel means. The first term makes
  larger edits count more; the second asks the output to reach the intended
  overall color/brightness shift. Neither term adds browser inference work.
- Save every epoch's validation metrics. Select exactly one checkpoint with the
  existing validation score: `mean Delta E 2000 - correct-reference gain over
a wrong reference`. Do not select on any test result or contact sheet.

## Validation decision before opening the final holdout

Compare the selected v4 checkpoint and frozen v3 on the same 160 validation
targets. Define a **strong edit** in advance as source-to-expert mean absolute
RGB change of at least `0.08` on the `[0, 1]` scale. Report the strong-edit
count; if fewer than 20, its result is inconclusive. Continue to final testing
only if all of these hold on validation:

1. Strong-edit mean Delta E 2000 improves by at least `0.5` versus v3.
2. Overall mean Delta E 2000 is no more than `0.1` worse than v3.
3. Mean SSIM drops by no more than `0.005`, and clipping rises by no more than
   one percentage point versus v3.
4. The correct-reference advantage over wrong references remains positive.

If validation fails, record the outcome and stop. Do not adjust these terms
after viewing final-holdout results. A later variant would need a new protocol
and another untouched holdout.

## Untouched final evaluation

Before the GPU run, a CPU-only manifest preflight will exclude every target and
reference scene in all v3 train/validation/test splits **and** the later
160-scene audit. From the remaining pinned manifest, select 256 unique target
scenes by a deterministic SHA-256 rank with seed `6109`. Check that the
expert edit matches each target's scene and that its reference is different.
Write the selected rows and a manifest checksum before training. If fewer
than 256 eligible rows exist, stop and revise the protocol before any GPU use;
do not reduce the count after viewing model results.

The CPU preflight passed with 256 unique targets, 59 strong-edit validation
targets, and sealed manifest SHA-256
`a1f9bdb468707e729703e4b8915283d0314b82b355ffb87e1d3cf94afa740b8a`.

The reproducible preflight is generated with
`python -m tools.ml.tst100k.build_v4_preflight_notebook` and runs privately as
`adides567/colorcheck-tst100k-v4-preflight`. Its only image downloads are the
old validation triplets needed to count strong edits; the new final-holdout
images are not opened until the validation decision is frozen.

The final set is opened **once**, only after v4's checkpoint and validation
decision are frozen. On all 256 scenes compare v4, frozen v3, ColorCheck's
existing statistics matcher, unchanged source, and a deliberately wrong
reference. Report paired photo-level bootstrap intervals for Delta E 2000,
plus SSIM, edge error, clipping, per-photo win rate, and weak/random/strong
contact sheets. A research advance needs a positive paired v4-versus-v3 color
gain with a 95% interval above zero, maintained correct-reference advantage,
and no meaningful structural or clipping regression. **Automatic replacement**
has a higher bar: at least 70% per-photo wins against the current matcher,
no large-loss tail, human visual review, and browser parity/performance tests.
The strong-edit label uses the expert answer and is never a production-time
routing rule.

## Cost and safety

This is one private Kaggle GPU run, estimated under 2.5 hours including paced
image staging; verify the live GPU quota and preserve at least two hours before
launch. Do not overlap GPU kernels. Keep image data in Kaggle scratch and
download only small metrics/contact sheets locally. Do not change the deployed
site or advertise v4 as better before final evaluation and ONNX/browser,
phone-performance, and output-quality checks. Pause before the user's 40%
weekly Codex usage ceiling.
