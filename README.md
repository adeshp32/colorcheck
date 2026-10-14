# ColorCheck Photos

Reference-guided photo matching and editing, entirely on your device.

Open a photo, add an optional reference, adjust the match, and export at the
original resolution. The active application is a static website: no Oracle,
Python backend, account, or photo-upload service is required.

## What works today

- Independent palette and tone matching strengths.
- Optional learned enhancement, using an upstream PyTorch model exported to ONNX.
- Exposure, contrast, highlights, shadows, whites, blacks, and tone-curve presets.
- Warmth, tint, saturation, vibrance, monochrome, and four tonal grading ranges.
- Crop, aspect-ratio presets, rotation, flip, sharpening, and vignette.
- Numeric controls, individual resets, before/after comparison, and undo/redo.
- Full-resolution JPEG, PNG, or WebP export and optional JSON settings report.

JPEG/PNG/WebP input is limited to 50 MB and 24 megapixels. This baseline is an
8-bit sRGB editor, not a RAW developer or an image-restoration system.
Reference matching is statistical and adjustable; it does not guarantee an exact
match between unrelated scenes. Read [quality and compatibility](docs/quality-and-compatibility.md).

## Run locally

Node.js 22 or newer:

```sh
npm ci
npm run dev
```

Open `http://127.0.0.1:8012/`. Node is needed for development tooling, not for
production image processing. The browser executes the photo editor.

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
    image-processing.js      Pure pixel transforms and reference statistics
    edit-history.js          Bounded, isolated undo/redo settings snapshots
    render-worker.js         Background-thread processing message boundary
  styles/editor.css          Mobile-first layout and desktop inspector
  assets/icons/              Locally served Lucide icons and license
  assets/brand/              Original ColorCheck wordmark, unchanged
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
[development conventions](docs/development.md). These describe what the code does,
why responsibilities are separated, and which trade-offs remain.

The normal editor uses browser APIs. Optional learned enhancement lazily loads
locally served ONNX Runtime Web and a pretrained model; there are no remote
analytics or photo-upload services. Prettier and Playwright are development tools.
Icons are from Lucide; licenses accompany all third-party assets.

See [learned enhancement](docs/learned-enhancement.md) for the PyTorch export,
model provenance, download sizes, numerical checks, and current quality limits.
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
