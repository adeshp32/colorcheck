# ColorCheck Photos

A standalone, on-device photo editor. The files in
`web/` can be hosted directly as a static website.
No Python server, Oracle instance, database, or image-upload endpoint is needed.
Use HTTPS in production so module workers load reliably.

## Working baseline

- JPEG, PNG, WebP, and HEIC/HEIF input up to 50 MB.
- Camera RAW input up to 120 MB, including DNG/Apple ProRAW and common Canon,
  Nikon, Sony, Fujifilm, Olympus, Panasonic, Pentax, and Sigma extensions.
- Decoded photos up to 50 megapixels.
- Optional reference image with independent palette and tonal matching strength.
- ColorCheck V11 research matching and optional upstream enhancement, both with
  adjustable strength, model integrity validation, and sampled clipping checks.
- Exposure, contrast, highlights, shadows, whites, blacks, and editable master/RGB curves.
- Eight overlapping color ranges with independent hue, saturation, and lightness.
- Warmth, tint, saturation, vibrance, B&W, and global/shadow/midtone/highlight grading.
- Sharpening, vignette, crop, aspect-ratio presets, 90-degree rotation, and horizontal flip.
- Numeric adjustment values, individual resets, a draggable crop, undo/redo, and hold-to-view-original comparison.
- Neutral dark editing canvas, three-state mobile tool sheets, compact view controls,
  and a tap-to-hide preview mode.
- Original-resolution cropped JPEG/PNG/WebP export, plus optional JSON settings report.
- Pixel processing in a module worker; no photos are submitted to the server.

## Quality boundaries

Matching uses bounded channel statistics, not a trained aesthetic model or semantic
understanding. Unrelated subjects can produce an unsuitable match; adjust its two
strength controls independently. Correction cannot recover clipped detail.
Quick Enhance is pretrained upstream. ColorCheck V11 was trained by this project
but remains experimental because it did not pass its held-out reference-discrimination gate.
Its integration is technically tested; real-photo quality improvement is not yet established.
Preview and export share the pixel engine. Sharpening operates at each render's
pixel scale, so its apparent detail differs between a scaled preview and a
full-resolution export. Use exported images to judge fine detail.

This baseline exports sRGB browser-canvas images. RAW files are decoded from sensor
data, demosaiced, and developed with camera white balance and camera color data,
but the resulting editor pipeline is 8-bit sRGB. It does not preserve RAW sensor
precision, HDR, high-bit-depth data, embedded color profiles, or original EXIF metadata.
Browser color conversion must be tested with real tagged photographs before
claiming professional color accuracy. JPEG and WebP export are lossy; PNG is
lossless relative to the rendered 8-bit image, not the original camera data.

The decoded-pixel limit is an admission limit, not a performance guarantee.
Mobile browser memory and performance vary. Large RAW files are presently a
desktop-oriented workflow because decode, demosaic, preview, and export can hold
several full image buffers. Extremely large dimensions can fail during browser
decoding before the image's dimensions can be checked.

No healing, automatic segmentation, denoising model, or upscaler is shipped yet.
These should be added with measured
quality, compatible licenses, and explicit device support rather than placeholder
controls. This is not a claim of parity with any existing photo editor.

## Verification

Run `npm test` for pixel-engine invariants. Test the
static page with desktop and mobile browser viewports, then validate exports on
real iPhone and Android devices before publishing a cross-device reliability claim.

The old video application is preserved in `archive/video-editor/` and is not
part of the photo editor's runtime or deployment.
