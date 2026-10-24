# Reference matcher research run log

Kaggle account: `adides567`. All runs are private. Training uses a Tesla T4
GPU; the visual and fresh-scene audits use CPU only.
Elapsed times below are the last timestamps in Kaggle execution logs, so they
are estimates rather than billing records. The user's October 23 estimate of
20 GPU-hours remaining is the budget baseline. Reserve at least two hours.

| Run                                 | Kaggle version                             | Approximate time | Outcome                                                                                     |
| ----------------------------------- | ------------------------------------------ | ---------------: | ------------------------------------------------------------------------------------------- |
| TST100K pilot                       | `colorcheck-tst100k-reference-pilot/1`     |           11 min | Correct-reference and identity gains passed; current-matcher confidence gate failed.        |
| Expanded validation, first attempt  | `colorcheck-tst100k-expanded-validation/1` |            1 min | Stopped before training: only 499 scene-disjoint test pairs available for a request of 512. |
| Expanded validation, second attempt | `colorcheck-tst100k-expanded-validation/2` |           13 min | Stopped before training: upstream image host returned HTTP 429.                             |
| Expanded validation, paced attempt  | `colorcheck-tst100k-expanded-validation/3` |           75 min | Completed: 1024/160/320 pairs; all three predeclared color gates passed.                    |
| Held-out visual audit (CPU only)    | `colorcheck-tst100k-visual-review/1`       |           15 min | Completed: 12 contact-sheet examples and per-scene comparison for all 320 test targets.     |
| Fresh-scene audit (CPU only)        | `colorcheck-tst100k-fresh-evaluation/1`    |           19 min | Completed: frozen checkpoint on 160 targets, excluding all prior target/reference scenes.   |

Conservative spend against the stated 20-hour baseline: **about 88 minutes**
for the second and third expanded attempts, leaving about 18 hours 32 minutes
before the two-hour reserve. The pilot and first attempt may have already been
reflected in the user's remaining-hours estimate; count them again if Kaggle's
own usage page shows otherwise. Do not launch simultaneous GPU runs.

Version 3's scene-disjoint test has 320 targets. Mean Delta E 2000 is 9.60 for
the trained model, 11.38 for the current statistics matcher, 10.86 for the
unchanged image, and 10.85 when the model gets a wrong reference. The paired
gain over the current matcher is 1.78 (95% bootstrap interval 1.17 to 2.42),
and the correct-reference gain is 1.25 (1.04 to 1.45). SSIM is 0.914 versus
0.875 for statistics matching; mean clipping is 1.68% versus 15.08%. These
are benchmark measurements at 128 px, not a claim about full-resolution
photographic quality or browser performance. A visual review, export parity,
and mobile performance check remain required before deployment.

Next: define a validation-only strategy for large intended color and brightness
changes, then test a newly trained candidate against a separate final holdout.
No browser checkpoint has been promoted.

The private `colorcheck-tst100k-visual-review/1` run mounted version 3's
checkpoint and test split. It used Kaggle CPU, so it did not spend the GPU
budget. The trained model was worse than the current matcher on **133 of 320**
held-out targets (41.6%), even though its average score was better. Four
worst, four fixed-random, and four best examples were reviewed side by side
with the current matcher and expected edit. Strong cases avoid the current
matcher's obvious overexposure or color cast while retaining source detail.
Weak cases show that the trained output can stay too close to the source when
the intended edit substantially changes color or brightness. The reference
and target photographs often depict different subjects, so pixelwise visual
similarity to the reference is not the objective. These examples are a quality
audit, not a way to select model settings.

**Decision:** promising research checkpoint, not a drop-in replacement. Do not
deploy until a fresh evaluation confirms improvement, failure cases have a
documented fallback, and ONNX/browser parity and phone performance pass.

The fresh-scene audit is an additional same-dataset evaluation, not a wholly
independent dataset. It uses a frozen checkpoint and excludes every scene in
the prior training, validation, and test partitions from both target and
reference positions. Its 160 triplets are ranked reproducibly with seed 3091.
It compares the model with the unchanged image, current statistics matcher,
and wrong-reference control; it reports Delta E 2000, SSIM, edge error, and
clipping, plus weak/random/strong visual examples. No GPU time was spent.

The run excluded **2,553 prior scenes** before selecting 160 fresh targets.
Mean Delta E 2000 was 9.16 for the trained model, 10.52 for the current
matcher, 10.56 for unchanged images, and 10.49 with wrong references. Paired
model-versus-current improvement was 1.36 (95% bootstrap interval 0.52 to
2.31); correct-versus-wrong-reference improvement was 1.33 (0.99 to 1.66).
Mean SSIM was 0.921 versus 0.889, edge error 0.0093 versus 0.0105, and
clipping 1.10% versus 11.90%. However, the model was worse than the current
matcher on **72 of 160** scenes (45%). The weak-case sheet again shows output
that stays near the source when the expected edit has a stronger cast or
brightness change. The random sheet has mixed quality; the strong sheet shows
clear avoidance of the current matcher's clipping and heavy color casts.

**Research conclusion:** the average improvement and reference sensitivity
replicate on untouched scenes, but the 45% per-image loss rate is too high for
an automatic replacement. This same-dataset audit does not establish
real-world generalization. Pause further training until a failure-oriented
objective and untouched final evaluation are predeclared; do not tune against
either completed test set.
