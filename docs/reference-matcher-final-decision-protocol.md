# TST100K matcher: final go/no-go protocol

## Decision this experiment must settle

Decide whether a TST100K-trained reference matcher is safe and useful enough
to replace V11 assist as the optional learned control. The existing statistics
matcher remains the default and the fallback. A mean improvement alone is not
a release decision: the frozen selector passed average numerical gates but
produced a 16.23 Delta E 2000 regression on one held-out scene.

This is one bounded experiment, not an open-ended search. No result from any
previously opened test set may choose the model, loss, threshold, or guardrail.
If the new candidate fails its locked validation rules, do not open its final
partition. If it passes validation but fails final quality or browser checks,
record a no-go and stop rather than adjust to that final partition.

## Data and baselines

- Pin the same TST100K manifest revision and record its checksum. Exclude every
  scene used anywhere in earlier target or reference train, validation, or test
  splits, including both opened selector and v4 holdouts. A scene may occur in
  only one new partition, whether used as target or reference.
- Before image download or fitting, seal 1,024 training, 256 validation, and
  256 final target scenes with recorded seed, scene IDs, and partition checksums.
  Abort if that many unused, scene-disjoint triplets cannot be formed.
- Compare unchanged source, the current statistics matcher, frozen v3 LUT,
  frozen selector at threshold 0.60, and the proposed candidate. Include a
  deliberately wrong reference for every learned method. No expert pixels or
  expert-error measures may be inference features.

## One targeted change

The failure to address is the selector choosing v3 when its edit under-transfers
a substantial intended color or brightness change. V4 already tried
strong-edit-weighted LUT training and failed its predeclared validation gate;
do not repeat it. Freeze both candidate image methods. Fit a small linear
quantile regressor on the existing 33 browser-available features to predict a
_lower bound_ on v3's Delta E advantage over statistics. This makes a severe
loss costly in training, instead of treating every winning photo equally as
the binary logistic selector does. The training target is the expert-scored
advantage, but neither expert pixels nor expert-derived values enter inference.
Export the feature scaling and coefficients as a small JSON file for later
Python/browser parity checks. Try only quantiles 0.10, 0.25, and 0.40 and
route to v3 only when the predicted lower-bound gain exceeds 0.25 Delta E.
Choose the highest-gain validation candidate that passes every validation
gate; ties prefer the lower quantile. If none pass, stop. Do not fit another
selector or change this threshold on the final partition.

## Locked validation gates

All measurements use paired photo-level comparisons at the same 128-pixel
analysis resolution as the earlier experiments. An edit is "strong" if the
source-to-expert mean absolute RGB difference exceeds 0.08, matching the v4
protocol. Require at least 40 strong edits in validation; otherwise stop.

1. Mean Delta E 2000 improves by at least 0.5 versus statistics and by at
   least 0.3 versus the frozen selector, with both paired 95% bootstrap lower
   bounds above zero. Report the comparison with always-v3 too.
2. On strong edits, mean Delta E improves by at least 0.5 versus the frozen
   selector, with a positive paired 95% bootstrap lower bound.
3. At least 95% of photos are no more than 0.5 Delta E worse than statistics;
   no photo is more than 5.0 worse. Report the full tail, not just the mean.
4. Correct references outperform wrong references, with a positive paired
   95% bootstrap lower bound.
5. Mean SSIM falls by no more than 0.005 and clipping rises by no more than
   one percentage point versus statistics. Record edge error as an additional
   diagnostic. Inspect fixed-seed weak, random, and strong contact sheets.
6. The learned route uses v3 on at least 20% of photos, so choosing only the
   deterministic fallback cannot qualify as a successful learned matcher.

## One-time final decision

Only after validation selects one checkpoint and passes all gates, evaluate
the sealed final partition once with the same gates. Do not change the
checkpoint, weights, or rules after looking at final results. Passing the
128-pixel benchmark creates a _review candidate_, not a deployed feature.
Before replacing V11 assist, inspect original-resolution exports with a human
reviewer; establish Python/ONNX/browser pixel parity and integrity; measure
phone memory, latency, and failure fallback; and verify dataset-use conditions.
Any failed check means **no replacement**. Publish the numerical result and
failure cases regardless of outcome.

The experiment may use one time-capped Kaggle GPU run after a CPU-only split
preflight. Never overlap GPU runs or consume the final two hours of the user's
quota reserve. Keep source images and expert edits on Kaggle, and download only
small metrics and contact sheets until a checkpoint passes the final gates.
