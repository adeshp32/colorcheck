# Architecture

## Responsibility boundaries

The active product separates browser responsibilities without a UI framework.
The static `web/` directory is the production artifact; codec and ML dependencies
are prepared into vendored browser assets before they are committed.

| Module                  | Owns                                                                                         | Does not own                   |
| ----------------------- | -------------------------------------------------------------------------------------------- | ------------------------------ |
| `editor-controller.js`  | File decoding, UI events, edit history, geometry, preview scheduling, download orchestration | Pixel-transform mathematics    |
| `image-processing.js`   | Channel statistics, bounded reference match, tonal/color/detail transforms                   | DOM, file access, networking   |
| `render-worker.js`      | Request IDs, transferable buffers, background processing, error responses                    | UI state or stored photographs |
| `edit-history.js`       | Bounded undo/redo snapshots and redo invalidation                                            | Image buffers or DOM events    |
| `photo-decoder.js`      | Format admission and lazy native/HEIC/RAW decoding                                           | Editing or export transforms   |
| `raw-decoder-worker.js` | LibRaw demosaic, camera white balance, and sRGB development                                  | UI state or adjustment math    |

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
Color, tone, matching, enhancement strength, sharpening, grain, and vignette can be local;
geometry and output settings remain whole-photo operations. Mask selection is UI
state; edits, mask names, and geometry are undoable. This release does not include
brush painting, automatic subject segmentation, or hair matting.

On mobile the image workspace fills the viewport above a compact tool strip.
Tool menus overlay the workspace without resizing the photo. The main tray supports
hidden, peek, and expanded positions. Selecting an adjustment portals its existing
DOM control into a matching three-state bottom sheet; Done restores it.
`mobile-editor.js` owns these portals, region shortcuts, compact view controls,
fit/zoom/pan, tap-to-hide preview mode, and fullscreen (with a CSS fallback where
native fullscreen is unavailable). The page itself need not scroll to perform an
edit. The tool strip stays anchored at the bottom, menus open upward over at most
40% of the viewport, and only the menu's contents scroll. Holding the eye control
temporarily reveals the unedited photo without changing edit history.
The compact LinkedIn footer remains visible below the tool strip outside fullscreen.
When a mask is selected for editing, two-finger gestures resize/rotate its geometry,
not the image. Radial edge handles and linear endpoints also support one-finger
dragging. Geometry gestures commit one undo entry. Outside mask editing, pinch
gestures zoom the photo normally.
Region buttons select the shared whole-photo or mask adjustment scope; they do not
create independent per-slider mask stacks. Selected coverage is cyan, excluded coverage
gray; the overlay checkbox hides this visualization without changing exported pixels.

`tone-curves.js` implements shape-preserving cubic interpolation and lookup tables;
`curve-editor.js` owns draggable points, channel selection, numeric input, and keyboard
editing. `color-mixer.js` owns eight overlapping HSL hue ranges. Both features run in
the same worker/export pipeline and work within the selected mask.

`film-grain.js` generates deterministic, monochrome procedural texture. Grain strength
and size are non-destructive settings; a normalized source-coordinate field keeps
the pattern stable as preview resolution changes. Full-resolution export regenerates
that same field, rather than baking a lower-resolution preview into the photo.

`workspace-layout.js` owns display-only photo fitting and the right, bottom,
and floating tool-panel positions. Viewer resize and canvas geometry changes
recalculate the fitted dimensions without changing image or export resolution.
Floating tools support pointer dragging, keyboard movement, and resizing;
positions stay within the viewport. Docking does not recreate controls or reset
edit state. On narrow screens, right docking resolves to the bottom layout.

ML has four additional boundaries. `v11-reference.js` and
`v11-reference-worker.js` own ColorCheck V11's lazy target/reference analysis;
`learned-enhancement.js` and `enhancement-worker.js` own the optional upstream
single-photo enhancer; and `enhancement-lut.js` owns the shared bounded
interpolation and clipping assessment. Each run produces a reversible LUT edit
for the whole photo or selected mask. LUTs are retained by model-result ID so
undo/redo and different masks can refer to different analyses. Neither path
mutates manual controls or replaces explicit crop, detail, and local-edit
decisions. Inference runs once per request; preview and original-resolution
export reuse the transform.

## Data flow

```text
Selected File
  -> native ImageBitmap, lazy HEIC decode, or lazy LibRaw development
  -> camera RAW becomes an 8-bit sRGB ImageBitmap after demosaic
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

HEIC uses a lazily imported decoder with its own worker. Camera RAW uses a dedicated
module worker and a locally served LibRaw WebAssembly binary. RAW development uses
the recorded camera white balance, camera color matrix, AHD demosaicing, highlight
reconstruction, and sRGB output. This creates a useful camera-aware starting image,
but the current canvas/pixel pipeline is 8-bit after development. A future true
high-bit-depth workflow must keep linear 16-bit or floating-point pixels through
adjustment and export rather than merely changing this decoder.

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
