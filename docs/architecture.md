# Architecture

## Responsibility boundaries

The active product separates browser responsibilities, deliberately without a framework
or a build pipeline. The static `web/` directory is the production artifact.

| Module                 | Owns                                                                                         | Does not own                   |
| ---------------------- | -------------------------------------------------------------------------------------------- | ------------------------------ |
| `editor-controller.js` | File decoding, UI events, edit history, geometry, preview scheduling, download orchestration | Pixel-transform mathematics    |
| `image-processing.js`  | Channel statistics, bounded reference match, tonal/color/detail transforms                   | DOM, file access, networking   |
| `render-worker.js`     | Request IDs, transferable buffers, background processing, error responses                    | UI state or stored photographs |
| `edit-history.js`      | Bounded undo/redo snapshots and redo invalidation                                            | Image buffers or DOM events    |

`index.html` defines the editor's semantic controls. `editor.css` handles
responsive layout, not image processing. `tools/serve.mjs` only serves local
development files and does not accept uploads.

Optional ML has three additional boundaries: `learned-enhancement.js` owns the
lazy worker/cancellation interface, `enhancement-worker.js` owns model loading
and inference, and `enhancement-lut.js` owns interpolation and clipping assessment.
They do not replace the reference-statistics engine. Model inference runs once
per requested analysis; preview/export reuse the transform.

## Data flow

```text
Selected File
  -> browser ImageBitmap decode
  -> original bitmap retained in browser memory
  -> preview pixels (longest edge at most 1200 pixels)
  -> edit settings + pixels transferred to module worker
  -> shared image-processing engine
  -> returned RGBA buffer
  -> crop / rotation / flip applied with canvas geometry
  -> visible preview

Export
  -> original bitmap pixels + current settings
  -> same worker and pixel engine
  -> original-resolution geometry
  -> JPEG / PNG / WebP encoding
  -> local download, optionally followed by settings JSON
```

The reference is sampled separately to calculate channel statistics. Only the
derived matching settings enter the pixel pipeline. No file is sent to an API.

## State and concurrency

An edit settings object is the source of truth. Editing does not modify the
original bitmap. Slider interactions update the preview continuously and commit
one undo entry on change. Undo/redo restores settings, not full image copies.
History is bounded to 60 entries.

Worker messages have request IDs to pair responses with promises. Preview
revisions prevent an older render from replacing newer edits. Repeated preview
requests coalesce while processing is active. Export disables duplicate requests.
Cancellation terminates the processing worker and creates a fresh worker.

Reference and target loads also use revision counters so a slower earlier decode
cannot replace a newer selection. Superseded bitmaps are closed.

## Why this structure

Pure processing functions can be tested without a browser. The worker keeps
pixel loops off the UI thread. The controller translates user intentions into
settings and passes them through the same engine for preview and export.

The controller is currently the largest module. Extract geometry or
export orchestration when those responsibilities gain independent complexity,
not simply to increase the file count. Tiled processing and selective masks are
future architectural work, not existing capabilities.
