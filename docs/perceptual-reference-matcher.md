# Perceptual reference matching

## Status

Included in the approved editor release. Newly applied reference matches use this
path. Existing Palette strength, Tone strength and experimental Distribution
detail controls remain in place; initial strengths remain65/45/0. No trained
model, image generation, photo upload or additional download is involved.

This is a mathematical change, not evidence that every reference pair looks
better. Visual feature testing remains with the user. The existing8-bit sRGB
working pipeline is unchanged.

## Changes

- Convert sRGB into Oklab, separating perceptual lightness from two color axes.
  Palette strength changes color without directly changing lightness. Tone
  strength changes lightness separately. Palette-only preservation is subject
  to the editor's final8-bit rounding.
- Measure color means and joint color variation separately in three smoothly
  blended lightness bands. This lets shadows, midtones and highlights receive
  different transfers without geometric masks or hard region boundaries.
- Use a regularized symmetric covariance transfer on the two color axes,
  rather than just shifting RGB averages. Principal-axis gains stay between
  0.65 and1.5; the palette displacement is limited to0.08 Oklab units.
- Exclude mostly transparent pixels from analysis. Downweight near-neutral
  pixels when estimating color statistics; use global statistics when a band
  has fewer than8 effective samples.
- Apply a smooth neutral-protection weight, zero below0.01 chroma and full at
  0.06. Exact RGB grays remain exactly gray. This deliberately transfers less
  of a warm/cool reference cast onto white, gray and near-gray objects.
- Experimental Distribution detail now refines the two color-axis quantile
  distributions for new matches, bounded to0.04 units per axis. It does not
  independently remap RGB channels or alter lightness. It remains off initially.
- Reduce out-of-gamut color intensity with a12-step search along the requested
  lightness/hue ray. Final channel clamping handles numerical tolerances only;
  this is not a promise of zero endpoint pixels after8-bit rounding or later
  user adjustments.
- Run reference analysis and image rendering in the existing module worker.
  Preserve source buffers, retain serializable settings for history, and discard
  an analysis result if its photo, reference or active editing scope changed.

## Technical Map

- `web/src/perceptual-match.js`: sRGB/Oklab conversions, weighted moments,
  regularized covariance mapping, color quantiles, neutral protection and gamut
  compression. Pixel processing reuses output/scratch arrays.
- `web/src/image-processing.js`: `calculatePerceptualReferenceMatch` constructs a
  versioned match. `applyPhotoAdjustments` dispatches new records to this path;
  records without `perceptual.version=1` retain the original RGB calculation.
- `web/src/render-worker.js`: handles reference-analysis requests and the same
  pixel transformation for preview/export.
- `web/src/editor-controller.js`: asynchronous Match reference action, busy state
  and stale-result guards. No changes to crop/mask coordinates or export sizing.

For source covariance S and reference covariance R, each color-band transform
uses the symmetric Gaussian transport formula
`T = S^(-1/2) (S^(1/2) R S^(1/2))^(1/2) S^(-1/2)` after adding
`1e-4 * I` to each covariance. Its eigenvalues are then bounded. Transfers are
blended according to source lightness. This is not object/subject recognition:
it cannot identify sky, skin or vegetation, nor does it associate corresponding
objects in unrelated compositions.

Oklab conversion is credited to
[Bjorn Ottosson](https://bottosson.github.io/posts/oklab/).
The implementation is original; it does not copy another matcher's source code.

## Verification

- `npm test`:63 tests passed, including8 new matcher tests for identity,
  gray-ramp protection, palette lightness, tone monotonicity, hue-preserving
  gamut reduction, sparse/flat statistics, alpha and local-mask composition.
- `npm run test:match`: browser-worker/shared-engine pixels match exactly on the
  fixed fixture at1440/320/390px; undo/redo, overflow and no-upload checks pass.
- `npm run test:browser`: existing crop, masks, curves, color wheels, enhancement,
  undo/redo and full-resolution PNG export coverage passes. Tests now await
  asynchronous matching and the full crop frame before direct touch injection.
- `npm run test:lens`: real depth model, fine focus gestures, blur rendering,
  Expand, preview/export equality and fallback tests pass.
- Original legacy-renderer hash fixtures remain unchanged.
- One local Node26 synthetic1MP-pair measurement: about165ms analysis and221ms
  image rendering. Both tasks run off the UI thread in the app. This is not an
  actual-phone benchmark or a claim that performance is unchanged on all devices.

No Kaggle splits, checkpoints, scientific gates or research results were changed.
