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

`masking.js` defines resolution-independent radial/linear coverage, feathering,
shape composition, range refinement, and inverse display coordinates.
`mask-controls.js` owns mask selection, numeric controls, overlays, and gestures.
Masks and their local adjustment settings are plain objects in the existing
undo history, not stored full-resolution bitmaps. The processing worker applies
global adjustments first, then blends each enabled mask's local result in stack
order. Cropping, rotation, and flipping happen afterward, so masks remain anchored
to source-image coordinates. Preview and export share this path.

There are at most eight masks, each with up to eight geometric components.
Components support union (add), subtraction, and intersection. Whole-mask
inversion happens before optional color/luminance intersection and opacity.
Color, tone, matching, enhancement strength, sharpening, and vignette can be local;
geometry and output settings remain whole-photo operations. Mask selection is UI
state; edits, mask names, and geometry are undoable. This release does not include
brush painting, automatic subject segmentation, or hair matting.

On mobile the image workspace fills the viewport above a compact tool strip.
Tool menus overlay the workspace without resizing the photo. Selecting an adjustment
portals its existing DOM control into a compact floating sheet; Done restores it.
`mobile-editor.js` owns these portals, region shortcuts, fit/zoom/pan, and fullscreen
(with a CSS fallback where native fullscreen is unavailable). The page itself need
not scroll to perform an edit. Two-finger navigation cancels mask geometry dragging.
Region buttons select the shared whole-photo or mask adjustment scope; they do not
create independent per-slider mask stacks. Selected coverage is cyan, excluded coverage
gray; the overlay checkbox hides this visualization without changing exported pixels.

`tone-curves.js` implements shape-preserving cubic interpolation and lookup tables;
`curve-editor.js` owns draggable points, channel selection, numeric input, and keyboard
editing. `color-mixer.js` owns eight overlapping HSL hue ranges. Both features run in
the same worker/export pipeline and work within the selected mask.

`workspace-layout.js` owns display-only photo fitting and the right, bottom,
and floating tool-panel positions. Viewer resize and canvas geometry changes
recalculate the fitted dimensions without changing image or export resolution.
Floating tools support pointer dragging, keyboard movement, and resizing;
positions stay within the viewport. Docking does not recreate controls or reset
edit state. On narrow screens, right docking resolves to the bottom layout.

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

Worker messages have request IDs to pair responses with promises. Repeated preview
requests coalesce while processing is active. During a drag, the latest completed
frame remains visible while newer settings render; a source identity check prevents
an older photo from replacing a new selection. Interactive previews use a 640-pixel
longest edge, then refine to the standard 1200-pixel preview after input settles.
Export disables duplicate requests and always starts from original-resolution pixels.
Cancellation terminates the processing worker and creates a fresh worker.

Reference and target loads also use revision counters so a slower earlier decode
cannot replace a newer selection. Superseded bitmaps are closed.

## Why this structure

Pure processing functions can be tested without a browser. The worker keeps
pixel loops off the UI thread. The controller translates user intentions into
settings and passes them through the same engine for preview and export.

The controller is currently the largest module. Extract geometry or
export orchestration when those responsibilities gain independent complexity,
not simply to increase the file count. Tiled processing and automatic semantic
segmentation remain future architectural work, not existing capabilities.
