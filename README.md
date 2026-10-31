# ColorCheck

ColorCheck is a browser-based photo editor centered on adjustable reference
matching. This public repository contains the deterministic matcher and selected
interface source for review.

## Public source

- Perceptual palette separation in Oklab.
- Independent palette, tone, and distribution controls.
- Bounded covariance and histogram transforms.
- Gamut-aware output instead of independent RGB clipping.
- Core editing controls, responsive interface styles, icons, and branding.
- Focused tests for matcher invariants and interface utilities.

## Privacy

Photos and references are processed in the browser. ColorCheck does not require
an account, photo-upload service, database, or third-party analytics. Button
theme choices last only for the current page and are not retained in browser
storage.

## Repository boundary

This is intentionally not the complete production repository. Model weights,
browser model runtimes, inference workers, training pipelines, notebooks,
experiment records, deployment configuration, and private research are not
included. The production application is maintained separately.

The deterministic reference matcher is implemented in:

- `web/src/perceptual-match.js`
- `web/src/histogram-match.js`
- `web/src/image-processing.js`

The files under `web/` preserve the public interface and matcher source layout,
but this repository is a reviewable source snapshot rather than a production
deployment package.

## Tests

Node.js 22 or newer:

```sh
npm test
```

## Third-party attribution

The Oklab conversion follows Björn Ottosson's published color-space equations.
Histogram transfer is informed by the histogram-matching method documented by
the open-source `hahnec/color-matcher` project. Lucide icon attribution is
included with the icon assets.
