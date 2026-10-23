# ColorCheck Photos

Reference-guided photo matching and editing, entirely on your device.

Open a photo, add an optional reference, adjust the match, and export at the
original resolution. The active application is a static website: no Oracle,
Python backend, account, or photo-upload service is required.

## What works today

- Independent palette and tone matching strengths.
- Featured ColorCheck V11 reference-conditioned research model, trained in
  PyTorch and exported to ONNX for guarded, adjustable browser inference.
- Optional Quick Enhance, using an upstream PyTorch model exported to ONNX.
- Exposure, contrast, highlights, shadows, whites, blacks, and editable master/RGB curves.
- Eight-range hue, saturation, and lightness mixing, globally or inside masks.
- Film-grain overlay with adjustable strength and size, globally or inside masks.
- Warmth, tint, saturation, vibrance, monochrome, and four tonal grading ranges.
- Crop, aspect-ratio presets, rotation, flip, sharpening, and vignette.
- Numeric controls, individual resets, hold-to-view-original comparison, and undo/redo.
- Local radial and linear masks with inside/outside selection, feathering,
  add/subtract/intersect shapes, and color/luminance refinement.
- Neutral dark canvas with an image-first mobile workspace, three-state tool sheets,
  tap-to-hide preview mode, compact zoom controls, pan, and fullscreen.
- Local HEIC/HEIF decoding for default iPhone photos.
- Local camera RAW development for DNG/ProRAW and common Canon, Nikon, Sony,
  Fujifilm, Olympus, Panasonic, Pentax, and Sigma formats.
- Full-resolution JPEG, PNG, or WebP export and optional JSON settings report.

JPEG/PNG/WebP/HEIC input is limited to 50 MB, camera RAW input to 120 MB, and
decoded photos to 50 megapixels. RAW files are genuinely decoded and demosaiced
with LibRaw, camera white balance, and camera color data. The developed image then
enters the existing 8-bit sRGB adjustment engine; edits do not yet retain the
sensor's original 12/14/16-bit precision.
Reference matching is statistical and adjustable; it does not guarantee an exact
match between unrelated scenes. Read [quality and compatibility](docs/quality-and-compatibility.md).

## Run locally

Node.js 22 or newer:

```sh
npm ci
npm run dev
```

Open `http://127.0.0.1:8012/`. Node is needed for development tooling, not for
production image processing. The browser executes the photo editor. Do not open
`web/index.html` through a `file://` URL: browser module and worker security rules
prevent the editor runtime and local codecs from loading correctly there.

```sh
npm test
npx playwright install chromium
npm run test:browser
npm run format:check
```

## Repository map

```text
web/                         Deploy this directory as a static website
  index.html                 Accessible editor layout and tool controls
  src/
    editor-controller.js     Files, edit history, controls, preview, and export
    photo-decoder.js          Native, HEIC, and camera RAW decode routing
    raw-decoder-worker.js     Local LibRaw demosaic and sRGB development
    v11-reference-worker.js   Verified target/reference V11 ONNX inference
    image-processing.js      Pure pixel transforms and reference statistics
    edit-history.js          Bounded, isolated undo/redo settings snapshots
    masking.js               Source-coordinate mask coverage and range refinement
    mask-controls.js         Local adjustment scope, mask gestures, and overlays
    mobile-editor.js         Overlay control portals, region shortcuts, and view gestures
    curve-editor.js          Draggable curve points and numeric channel controls
    tone-curves.js           Shape-preserving curve interpolation and lookup tables
    color-mixer.js           Smooth eight-band HSL color adjustments
    film-grain.js            Repeatable, resolution-independent monochrome grain
    render-worker.js         Background-thread processing message boundary
  styles/editor.css          Mobile-first layout and desktop inspector
  assets/icons/              Locally served Lucide icons and license
  assets/brand/              Original ColorCheck wordmark, unchanged
  vendor/heic/               Lazy HEIC decoder and license
  vendor/libraw/             Lazy camera RAW decoder, WASM, and licenses
  _headers                   Cloudflare Pages security headers
tests/
  image-processing.test.mjs   Pixel invariants and correction bounds
  edit-history.test.mjs       Undo/redo, isolation, and history limits
  photo-editor.browser.cjs   End-to-end editing, export, and mobile checks
tools/serve.mjs               Local static development server
docs/                        Architecture, algorithms, quality, and deployment
archive/video-editor/        Former Python/video product, retained for history
```

## Understand the implementation

Start with [architecture](docs/architecture.md), then
[image processing](docs/image-processing.md) and
[reference matcher architecture](docs/reference-matcher-architecture.md),
[model card](docs/reference-matcher-model-card.md), and
[data card](docs/reference-matcher-data-card.md), then
[development conventions](docs/development.md). These describe what the code does,
why responsibilities are separated, and which trade-offs remain.

The private [TST100K pilot](docs/reference-matcher-tst100k-pilot.md) tests whether
direct triplet supervision improves reference use before any new model is shipped.

The normal editor uses browser APIs. V11 and Quick Enhance lazily load locally
served ONNX Runtime Web models; there are no remote
analytics or photo-upload services. Prettier and Playwright are development tools.
Icons are from Lucide; licenses accompany all third-party assets.

See [learned enhancement](docs/learned-enhancement.md) for both models' PyTorch
provenance, exports, download sizes, numerical checks, and current quality limits.
The export and validation job also has a separate [Docker workflow](docs/ml-container.md).
Docker is developer tooling, not a hosting dependency for the editor.

## Publish

Deploy `web/` to a static host. For Cloudflare Pages, use no build command and
`web` as the output directory. See [deployment](docs/deployment.md) for the
domain transition and security checks. Repository changes do not themselves
replace the currently running video website.

## Historical video application

The previous FastAPI/FFmpeg application, tests, deployment files, documentation,
and experimental training code live under [archive/video-editor](archive/video-editor/ARCHIVE.md).
They are not dependencies of the photo editor and are excluded from its CI.
