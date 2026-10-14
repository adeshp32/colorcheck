# ColorCheck Photos

A standalone, on-device photo editor. The files in
`web/` can be hosted directly as a static website.
No Python server, Oracle instance, database, or image-upload endpoint is needed.
Use HTTPS in production so module workers load reliably.

## Working baseline

- JPEG, PNG, and WebP input; up to 50 MB compressed and 24 megapixels decoded.
- Optional reference image with independent palette and tonal matching strength.
- Optional pretrained enhancement, with adjustable strength and sampled clipping checks.
- Exposure, contrast, highlights, shadows, whites, blacks, and tone-curve presets.
- Warmth, tint, saturation, vibrance, B&W, and global/shadow/midtone/highlight grading.
- Sharpening, vignette, crop, aspect-ratio presets, 90-degree rotation, and horizontal flip.
- Numeric adjustment values, individual resets, a draggable crop, undo/redo, and original comparison.
- Original-resolution cropped JPEG/PNG/WebP export, plus optional JSON settings report.
- Pixel processing in a module worker; no photos are submitted to the server.

## Quality boundaries

Matching uses bounded channel statistics, not a trained aesthetic model or semantic
understanding. Unrelated subjects can produce an unsuitable match; adjust its two
strength controls independently. Correction cannot recover clipped detail.
The separate enhancement model is pretrained upstream, not trained by ColorCheck.
Its integration is technically tested; real-photo quality improvement is not yet established.
Preview and export share the pixel engine. Sharpening operates at each render's
pixel scale, so its apparent detail differs between a scaled preview and a
full-resolution export. Use exported images to judge fine detail.

This baseline exports sRGB browser-canvas images. It does not preserve camera RAW,
HDR, high-bit-depth data, embedded color profiles, or original EXIF metadata.
Browser color conversion must be tested with real tagged photographs before
claiming professional color accuracy. JPEG and WebP export are lossy; PNG is
lossless relative to the rendered 8-bit image, not the original camera data.

The decoded-pixel limit is an admission limit, not a performance guarantee.
Mobile browser memory and performance vary. Extremely large dimensions can fail
during browser decoding before the image's dimensions can be checked.

No healing, segmentation, denoising model, upscaler, local adjustment masks, or
custom curve-point editing is shipped yet. These should be added with measured
quality, compatible licenses, and explicit device support rather than placeholder
controls. This is not a claim of parity with any existing photo editor.

## Verification

Run `npm test` for pixel-engine invariants. Test the
static page with desktop and mobile browser viewports, then validate exports on
real iPhone and Android devices before publishing a cross-device reliability claim.

The old video application is preserved in `archive/video-editor/` and is not
part of the photo editor's runtime or deployment.
