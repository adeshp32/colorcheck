# Development Conventions

## Naming and layout

Use lowercase kebab-case for folders and source filenames. Use camelCase for
functions and variables, and name functions by responsibility:
`calculateReferenceMatch`, `applyPhotoAdjustments`, `decodePhoto`, and
`commitEditHistory` describe concrete operations.

Production code belongs in `web/`. Tests belong in `tests/`. Developer-only tools
belong in `tools/`. Historical code belongs in `archive/`, never in the active
runtime import graph. Dependencies are pinned in `package-lock.json`.

## Make changes

```sh
npm ci
npm run dev
npm run format
npm test
npm run test:browser
```

The browser test starts and stops its own static server on an ephemeral port.
For an installed Chrome browser, use `PHOTO_BROWSER_CHANNEL=chrome npm run test:browser`.
CI installs Playwright Chromium and runs formatting, engine, and browser checks.

## Verification boundaries

Engine tests cover neutral edits, identical-reference matching, transparency,
exposure, monochrome, bounded gain, and monotonic curves. Browser tests exercise
file selection, matching, editing history, wheel keyboard input, cropped export,
unsupported formats, mobile overflow, and the absence of upload requests.

Generated fixtures test software behavior, not photographic quality. Real-device
testing, tagged-color image comparisons, large-image memory profiling, and visual
quality evaluation remain separate requirements.

## Explain the project

An accurate implementation summary is:

> A static, privacy-oriented photo editor that uses bounded reference statistics
> for adjustable color matching. A pure pixel engine runs in a browser worker;
> non-destructive settings drive both preview and full-resolution export.

Do not describe the current matching algorithm as trained ML, claim professional
RAW/HDR support, or imply that browser tests prove all-device reliability.
