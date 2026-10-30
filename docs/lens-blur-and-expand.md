# Lens blur and Expand

## Status and scope

Included in the approved editor release. The reference matcher remains the
default; its color-separation update is documented separately in
`perceptual-reference-matcher.md`. No Qwen, SepLUT, V11, new training or generative image
model is involved. Depth Anything predicts a depth map; the renderer averages
existing photo pixels. Expand adds solid black pixels only.

Depth analysis cannot perfectly resolve hair, glass, reflections, thin wires or
occluded surfaces. This implementation is an approximate depth-guided gather
renderer, not a reconstruction of hidden background or a physical lens simulator.
Desktop Chromium tests do not prove actual iPhone/Android performance.

## Alternatives reviewed

- Depth Anything V2 Small: selected first because its 24.8M-parameter model has
  Apache-2.0 weights and an existing ONNX Community browser-compatible export.
  It estimates relative inverse depth, not reliable distance in meters.
  https://github.com/DepthAnything/Depth-Anything-V2
- Depth Anything 3: newer geometry/depth family. Its multi-view capabilities do
  not by themselves establish a better small-model browser portrait result.
  No DA3-versus-V2 quality benchmark was performed here.
  https://github.com/ByteDance-Seed/Depth-Anything-3
- Apple Depth Pro: metric-depth candidate, but its released checkpoint is about
  1.9GB and has a distinct Apple license. Not selected for a low-resource browser.
  https://github.com/apple/ml-depth-pro
- Dr.Bokeh: valuable occlusion-aware rendering research; not integrated or
  benchmarked here. https://arxiv.org/abs/2308.08843
- glfx.js lens blur: efficient six-bladed bokeh, but its brightness power is an
  approximation, with float-texture requirements. Reviewed, not copied.
  https://github.com/evanw/glfx.js
- pmndrs/postprocessing: its established 64-tap disk convolution is the rendering
  basis adapted here. Our version adds linear-light accumulation, relative-depth
  rejection, polygonal apertures, alpha handling and padded tiled execution.
  https://github.com/pmndrs/postprocessing/blob/main/src/materials/glsl/convolution.bokeh.frag

This is a practical initial selection, not a claim to have evaluated every
open-source model or to deliver the world's most advanced blur.

## Model provenance and privacy

- Export: `onnx-community/depth-anything-v2-small`, revision
  `64fe43eba7f8a384b02fe3fadaa26cbba35548d8`.
- Artifact: `onnx/model_quantized.onnx`, 27,258,801 bytes.
- SHA256: `fcf51f1b230362b28690bb9d1809bf0431f29cad20534e3f589bd7285547f20d`.
- Apache-2.0 license retained alongside the served model. Attribution to
  Lihe Yang, Bingyi Kang, Zilong Huang, Zhen Zhao, Xiaogang Xu, Jiashi Feng and
  Hengshuang Zhao, and the ONNX Community export maintainers.
- `npm run prepare:depth` downloads the pinned artifact at development time,
  verifies it, then splits it into two same-origin static-host-sized chunks.
- The user's browser downloads weights only on explicit Analyze photo. No photo
  leaves the device; the existing same-origin-only CSP is unchanged.
- Each chunk and the reassembled model are checked by byte count and SHA256.
  Browser caching is optional; storage failures do not prevent analysis.
- Module Worker, single-thread ONNX Runtime Web WASM, disabled graph fusion,
  ImageNet normalization. Original aspect ratio with multiples of14; maximum
  analysis edge518 on desktop,252 for coarse-pointer devices. These smaller
  analysis sizes are deployment choices, not a new depth-quality benchmark.
- Float32 depth is normalized between its2nd/98th percentiles. Flat/nonfinite
  predictions are rejected. No meters or confidence calibration are claimed.

## Blur and geometry

- Blur is off until explicitly enabled, or a radial/linear blur is created.
- Automatic mode offers behind-focus, in-front, both sides, focus plane and an
  in-focus band. Tap-to-focus maps through crop, rotation, flip and border offsets.
- Manual modes reuse source-coordinate radial/linear masks, including feathering,
  subtraction, opacity and existing color/luminance refinements. By default a
  new blur mask blurs outside its shape. It requires no model download.
- Blur amount has a0.1-step slider and exact numeric entry. Focus is selected by
  dragging the depth-map reticle or picking on the photo. Auto focus uses the
  visible photo's center and a small local depth-spread heuristic, not semantic
  subject detection. A histogram band controls both focus boundaries. Fine
  adjustment reduces map/range drag movement to one fifth; keyboard movement and
  optional exact0.1-step Far/Near fields remain available. Touch handles have
  44px targets; numeric fields use16px text to avoid iOS input zoom. Focus edits
  are undoable and interrupted drags restore the previous settings.
- Bokeh and refinement live in a closed disclosure rather than competing with
  the focus map and amount control. Aperture choices are
  circular or5--9 blades, with adjustable blade roundness and depth-edge
  protection; a dedicated button rotates the aperture15degrees.
- Mask movement/resizing does not rotate it. The explicit rotate control unlocks
  rotation and resets when another mask/component is selected. Linear endpoint
  projections and boundary-aware pinches preserve orientation rather than
  independently clamping endpoints. Drawing new geometry is an explicit mode.
- Shader accumulation uses high-precision floating-point linear-light RGB and
  returns sRGB. Alpha is preserved. This is not a generative renderer.
- GPU work uses768px tiles with a radius-dependent halo. Radius scales with the
  source image's short edge so preview and export use the same normalized effect.
  No whole-image float color buffer or per-aperture image stack is allocated.
- Unsupported/lost WebGL2 contexts, excessive radii and image budgets raise a
  visible error instead of silently reducing export resolution. The existing
  editor can continue with blur disabled. No claim of perfect occlusion recovery.
- Expand is non-destructive per-edge black padding measured relative to the
  cropped image. Linked edges, frame handles, keyboard adjustments, reset,
  undo/redo and export share settings. Crop remains separate from Expand.
  Border pixels are opaque black; interior transparency is preserved.
- Output allocation guard:50MP and16,384px per edge. Blur additionally respects
  the device pixel limit:12.6MP on coarse-pointer/low-memory devices,25MP by
  default,50MP when the browser reports at least8GB device memory. These are
  conservative limits, not measured guarantees about available browser RAM.
  Large exports can require disabling blur or borders.

## Color precision: important unfinished requirement

**The editor is still 8-bit sRGB.** RAW decoding currently requests8-bit output
from LibRaw; browser canvas processing is also8-bit. Floating-point blur does
not restore discarded RAW precision or make the whole application16-bit/HDR.

PNG and JPEG source sample precision is reported only when explicit supported
headers establish it. Palette index precision is distinguished from RGB sample
precision. Other formats, including RAW/HEIC, remain marked unverified; no
guess is presented as fact. This is bounded header inspection, not a general
file-forensics validator.

A true high-bit-depth path still requires retaining16-bit/float decoded pixels,
updating every adjustment/mask/export boundary, defining color profiles and
linear-light conversions, and precision-specific reference tests. That migration
is not silently included in this feature and must not be advertised as complete.

## Verification

`npm test` covers neutral settings, depth normalization, precision headers,
resolution-aware blur strength, Expand geometry/budget checks and mask rotation.
`npm run test:browser` retains the existing editor regression coverage.
`npm run test:lens` exercises real ONNX depth inference, depth-selective sharpness,
linear-light behavior, aperture differences, alpha, mask on/off, PNG export,
black borders, undo/redo, narrow layouts and model-unavailable fallback.

Initial actual desktop Chromium depth inference was about1.8seconds on the
synthetic textured portrait fixture. This is not a phone benchmark or depth
accuracy score. The model was not fine-tuned. Representative real-photo edge
review and actual-phone profiling remain necessary before production approval.

The user-supplied588x350 sunset JPEG also completed real depth inference locally
in about1.4seconds. Its map separates foreground water from distant sky, but
this is a single visual example without depth ground truth, not accuracy proof.
All63 unit tests and the existing desktop/mobile editor suite passed. The new
lens suite also checks exact same-resolution PNG preview/export pixel equality,
model-unavailable fallback and Expand frame/keyboard crop preservation.

Focus UI tests verify the five-to-one drag sensitivity, exact fractional range
entry, keyboard edits, undo and actual Chromium touch-event drags at320/390px.
Screenshots were reviewed for narrow-screen layout. Emulated touch is not an
actual-phone performance measurement. The reference-matching color calculation
is updated separately in the same release; no depth model is used for matching.

The simplified focus interaction follows established patterns reviewed in
[Lightroom Lens Blur](https://helpx.adobe.com/in/lightroom/web/edit-photos/apply-effects/apply-lens-blur.html)
and [Affinity depth of field](https://s3-eu-west-1.amazonaws.com/affinity-docs/help/photo_beta/English.lproj/pages/Filters/filter_DOFBlur.html):
choose a focus point, adjust its range, and disclose secondary controls. These
are interaction references, not claims of equal rendering quality.

## Upstream renderer license

The altered bokeh adaptation is marked in `web/src/lens-blur.js`. The original
postprocessing copyright and permissive zlib license are retained in
`web/vendor/bokeh/LICENSE.txt`. Do not describe the source as unmodified upstream
or remove its notice.
