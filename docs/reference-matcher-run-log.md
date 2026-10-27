# Reference matcher research run log

Kaggle account: `adides567`. All runs are private. Training requests a GPU;
the visual and fresh-scene audits use CPU only.
Elapsed times below are the last timestamps in Kaggle execution logs, so they
are estimates rather than billing records. The user's October 23 estimate of
20 GPU-hours remaining is the budget baseline. Reserve at least two hours.

| Run                                 | Kaggle version                                  | Approximate time | Outcome                                                                                           |
| ----------------------------------- | ----------------------------------------------- | ---------------: | ------------------------------------------------------------------------------------------------- |
| TST100K pilot                       | `colorcheck-tst100k-reference-pilot/1`          |           11 min | Correct-reference and identity gains passed; current-matcher confidence gate failed.              |
| Expanded validation, first attempt  | `colorcheck-tst100k-expanded-validation/1`      |            1 min | Stopped before training: only 499 scene-disjoint test pairs available for a request of 512.       |
| Expanded validation, second attempt | `colorcheck-tst100k-expanded-validation/2`      |           13 min | Stopped before training: upstream image host returned HTTP 429.                                   |
| Expanded validation, paced attempt  | `colorcheck-tst100k-expanded-validation/3`      |           75 min | Completed: 1024/160/320 pairs; all three predeclared color gates passed.                          |
| Held-out visual audit (CPU only)    | `colorcheck-tst100k-visual-review/1`            |           15 min | Completed: 12 contact-sheet examples and per-scene comparison for all 320 test targets.           |
| Fresh-scene audit (CPU only)        | `colorcheck-tst100k-fresh-evaluation/1`         |           19 min | Completed: frozen checkpoint on 160 targets, excluding all prior target/reference scenes.         |
| V4 protocol preflight (CPU only)    | `colorcheck-tst100k-v4-preflight/1`             |            7 min | Passed: sealed 256-target holdout; 59/160 validation targets meet the strong-edit definition.     |
| V4 strong-edit training (GPU)       | `colorcheck-tst100k-v4-strong-edit-training/1`  |           48 min | Completed; selected epoch 4, but the predeclared strong-edit gain gate failed.                    |
| Selector split preflight (CPU only) | `colorcheck-tst100k-selector-preflight/1`       |           <1 min | Passed: reserved 1024/256/256 new target scenes; no GPU or image downloads.                       |
| Selector validation (GPU-assisted)  | `colorcheck-tst100k-selector-validation/1`      |           49 min | Passed all six predeclared validation gates; final photos remain sealed.                          |
| Selector final audit (GPU-assisted) | `colorcheck-tst100k-selector-final-audit/1`     |           11 min | Passed all six locked numerical gates on 256 untouched scenes; visual weak cases block promotion. |
| Final decision preflight (CPU only) | `colorcheck-tst100k-final-decision-preflight/1` |           <1 min | Passed: 1024/256/256 fresh target scenes; no images staged.                                       |

Conservative spend against the stated 20-hour baseline: **about 196 minutes**
for the second and third expanded attempts, v4, selector validation, and final audit.
That leaves about 16 hours 44 minutes total, or 14 hours 44 minutes spendable
after preserving a two-hour reserve. The pilot and first attempt may have already been
reflected in the user's remaining-hours estimate; count them again if Kaggle's
own usage page shows otherwise. These are wall-clock estimates, not billed GPU
hours; the v4 kernel metadata requested GPU but its output log did not name the
actual device or report remaining quota. Do not launch simultaneous GPU runs.

Version 3's scene-disjoint test has 320 targets. Mean Delta E 2000 is 9.60 for
the trained model, 11.38 for the current statistics matcher, 10.86 for the
unchanged image, and 10.85 when the model gets a wrong reference. The paired
gain over the current matcher is 1.78 (95% bootstrap interval 1.17 to 2.42),
and the correct-reference gain is 1.25 (1.04 to 1.45). SSIM is 0.914 versus
0.875 for statistics matching; mean clipping is 1.68% versus 15.08%. These
are benchmark measurements at 128 px, not a claim about full-resolution
photographic quality or browser performance. A visual review, export parity,
and mobile performance check remain required before deployment.

Next: follow the predeclared [v4 protocol](reference-matcher-v4-protocol.md),
starting with its CPU preflight, then test a candidate against its sealed final
holdout only after validation passes.
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
real-world generalization. The [v4 protocol](reference-matcher-v4-protocol.md)
now predeclares a failure-oriented training objective and a newly sealed final
holdout; neither completed test set is used for model selection.

The v4 preflight used Kaggle CPU and no GPU time. The holdout manifest has 256
unique target scenes, no target/reference scene collision, and SHA-256
`a1f9bdb468707e729703e4b8915283d0314b82b355ffb87e1d3cf94afa740b8a`.
The old validation split contains 59 strong edits under the protocol's 0.08
mean RGB-change rule, above its minimum of 20. These checks allowed the GPU
training run to proceed without opening the sealed holdout.

The private v4 GPU run completed on October 24 (approximately 08:11-08:59 UTC,
based on its 2,861-second execution log and completion check). Validation
selected epoch 4 using the frozen rule. On the 59 strong-edit validation
targets, mean Delta E 2000 improved from **11.865 (v3) to 11.606 (v4)**: a
**0.258** gain, below the predeclared **0.5** minimum. The other validation
gates passed: overall Delta E 8.909 to 8.806, SSIM 0.9171 to 0.9161,
clipping 1.42% to 1.22%, and correct-reference advantage 1.304 (positive).
The overall decision is **fail** because all gates were required. The sealed
256-scene final holdout remains unopened. Do not use it to rehabilitate this
checkpoint, and do not promote v4 to the site. A new experiment requires a
new predeclared objective and validation decision, with a separate untouched
final holdout if it reaches final testing.

The [deployment-oriented selector experiment](reference-matcher-deployment-experiment.md)
began with private Kaggle CPU preflight version 1 on October 24 local time.
Its execution log ends at about 27 seconds. It reserved 1,024 training, 256
validation, and 256 final target scenes. An independent local check confirmed
zero overlap among the partitions and zero overlap with all **3,366** scenes
used by v3 train/validation/test, the fresh audit, or the sealed v4 holdout.
The pinned dataset revision is `63bf13833b75407c862d608c3d81281d0a35b61f`.
Full split checksum: `5cf65a621ca1c33475a1f3579b22caa4f0e3f33ec563df176202950e7272afa8`;
final-partition checksum: `a0e8940a69c494bef7648949364d6fefe0a7187ef0ab575d41a0a54d280fe399`.
No selector model has been fitted, and no final images have been opened. Kaggle's
status endpoint still reported RUNNING after the output and completion log were
available; the artifacts themselves are complete and hash-verified.

The selector validation notebook is generated from the checked-in Python
modules, requests one GPU session, and has a 2.5-hour execution cap. GPU is
used only to produce frozen candidate outputs and evaluation metrics; the
regularized logistic selector is fitted on the new training partition. Its
regularization and decision threshold are chosen only from the 256 validation
targets under the predeclared gates. No final-partition photos are staged.

The private selector validation run completed on October 25. Kaggle's execution
log ends at about 2,949 seconds (49 minutes), including paced staging of 3,834
files (2.60 GB); it used a Tesla T4. The model used 968 non-tied training labels
and 241 non-tied validation labels. Validation log loss chose `C=0.1`; the
predeclared threshold search selected `0.60`. On all 256 validation targets,
the selected output beat the unchanged statistics matcher by **1.963 mean
Delta E 2000** (paired 95% bootstrap interval **1.403 to 2.578**). It was no
more than 0.5 Delta E worse on **91.4%** of targets; 5.5% had a loss greater
than 2.0 Delta E. It chose the LUT for 40.6% of targets, retained a positive
correct-reference advantage of 2.993 Delta E, improved mean SSIM from 0.8853
to 0.9124, and reduced mean clipping from 13.87% to 9.09%. All six validation
gates passed. The selector coefficient file has 33 features and is marked
research-only. This is a **validation candidate**, not independent final
evidence or a deployment decision. The 256 final images remained unopened
until the separate private final audit was launched on October 25. No result
from that audit may be used to change the selector, threshold, or checkpoint.

The separate one-time final audit completed on October 25, using a Tesla T4.
The private execution log ends at about 683 seconds (11 minutes), including
paced staging of 768 files (506 MB) on Kaggle. The frozen v3 checkpoint,
selector coefficients, feature schema, and threshold of 0.60 were unchanged.
The final manifest checksum matched
`a0e8940a69c494bef7648949364d6fefe0a7187ef0ab575d41a0a54d280fe399`.
All six predeclared **numerical** gates passed on 256 untouched target scenes:

- Mean Delta E 2000 was **8.765** for the selector, **10.725** for the current
  statistics matcher, **8.828** for always using v3, and **9.978** for the
  unchanged photo. Selector gain over statistics was **1.960**, paired 95%
  bootstrap interval **1.349 to 2.576**. Its additional average gain over
  always using v3 was only **0.063** Delta E.
- The correct reference beat a wrong reference by **3.740** Delta E on average
  (paired interval **3.036 to 4.478**). The LUT was selected on **37.1%** of
  photos; the rest fell back to statistics matching.
- **90.6%** of photos were no more than 0.5 Delta E worse than statistics,
  just above the locked 90% gate. **5.1%** lost more than 2.0 Delta E. Among
  256 photos, 68 improved versus statistics, 27 worsened, and 161 tied exactly
  because the selector chose the statistics fallback.
- Mean SSIM was **0.9133** versus **0.8854** for statistics. Mean clipping was
  **8.87%** versus **13.92%**. Edge MAE was **0.00890** versus **0.00946**.

The three private contact sheets (four worst, four fixed-random, four best)
were inspected at 256-pixel review size. The strongest cases avoid visible
overexposure, heavy casts, or crushed shadows from the statistics candidate.
The weak sheet exposes a serious tail: scene `02010` is **16.23 Delta E worse**
than statistics. Its selected LUT stays near the green source while the
reference/expected look is pink-purple; other weak examples also under-transfer
the intended look. These are genuine failure cases, not a numerical artifact
to conceal. The contact sheets are research material, not public dataset copies.

**Decision:** the frozen selector is a credible research candidate with an
independently replicated mean improvement, but this is **not** a production
promotion. The small incremental mean gain over always-v3, near-threshold
nonregression rate, severe individual miss, 128-pixel benchmark, unknown
full-resolution appearance, missing browser parity and phone benchmarks,
and dataset-use review remain. Do not tune this selector against the opened
final partition. Any next model experiment needs a newly declared protocol
and genuinely new validation/final scenes. The live editor remains unchanged.

## Final risk-aware decision experiment

The [locked protocol](reference-matcher-final-decision-protocol.md) tests a
different routing objective after the earlier V4 strong-edit weighting failed.
Private CPU preflight version 1 completed on October 26. It excluded 6,203
earlier target or reference scenes and reserved 1,024 training, 256 validation,
and 256 final target scenes. Its manifest checksum is
`b7c4b0a0977c2cdf6d998351d9fcc4a95d5b18eb4070defa6b6ac5637c1fee08`;
the sealed final checksum is
`d2793beaa619e406424d231190f7d4eafea1f24f64cf4c63b72ec7cb564269c3`.
Only JSON manifests were read. No GPU time was used and no photos were staged.
