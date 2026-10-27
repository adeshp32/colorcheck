# Adaptive deterministic matcher pilot

ColorCheck's current reference match shifts each RGB channel toward the
reference's average color and adjusts its spread. The user can control palette
and tone strengths; clicking Match reference starts at 65% and 45%. This pilot
tests whether offline learning can choose better starting strengths for each
pair of photos. It does not replace the matching arithmetic, use the V11 LUT,
or put an ML runtime or image upload into the browser.

## Locked pilot

- Input: the pinned TST100K revision
  `63bf13833b75407c862d608c3d81281d0a35b61f` and the previously
  reserved final-decision manifest, SHA-256
  `b7c4b0a0977c2cdf6d998351d9fcc4a95d5b18eb4070defa6b6ac5637c1fee08`.
- Use only the first 192 training and 64 validation triplets. The final
  partition is never staged or read. No previously opened test partition is
  used to choose model settings.
- For each training pair, search a fixed grid of palette/tone settings against
  the expert edit at 64 pixels using a Kaggle GPU. Favor the current 65%/45% starting point in
  ties and mildly penalize added clipping. Fit a standardized two-output Ridge
  regression to 18 source/reference color-statistic features. Select the
  regularization from 1, 10, or 100 by validation mean RGB error only.
- Compare the selected rule against fixed 65%/45%, unchanged images, and a
  deliberately wrong reference. The fixed matcher is the primary baseline.
  Report paired bootstrap uncertainty, losses per photo, and clipping.
- Pass only if validation mean normalized RGB error improves by at least
  0.002, its paired 95% interval is wholly positive, at least 90% of photos
  lose no more than 0.02, the worst loss is at most 0.08, the correct
  reference beats the wrong one, and mean clipping exceeds the fixed matcher
  by no more than 0.01.

Passing this small, same-dataset validation would justify a larger,
predeclared audit, not deployment. Before site integration, review representative
photos, compare full-resolution exports, test Python/browser numerical parity,
and check performance and fallback behavior on phones. A failed gate leaves the
current matcher unchanged. Model coefficients are marked `researchOnly` and
`web/src/adaptive-reference-match.js` is not imported by the live editor.

## Code map

- `tools/ml/tst100k/adaptive_rules_core.py`: mirrors the browser match and
  produces per-photo training labels.
- `tools/ml/tst100k/train_adaptive_rules.py`: stages only selected pairs,
  fits and evaluates the candidate, and writes small JSON outputs on Kaggle.
- `tools/ml/tst100k/build_adaptive_rules_notebook.py`: packages the reviewed
  modules into a reproducible private notebook.
- `web/src/adaptive-reference-match.js`: candidate browser arithmetic and a
  clipping guard, currently disconnected from the editor.
