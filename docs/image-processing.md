# Image Processing

## Reference matching

`calculateChannelStatistics` measures mean and standard deviation for each RGB
channel of sampled pixels. Pixels with alpha below 128 are excluded from matching
statistics; an entirely transparent image cannot supply a reference.

`calculateReferenceMatch` derives channel mean offsets and spread gains. Gains
are clamped to 0.65-1.5, with a minimum denominator to avoid unstable division in
nearly uniform channels. This bounds correction magnitude but is not a semantic
or perceptual correctness guarantee.

Palette strength blends mean offsets. Tone strength blends spread changes around
the source mean. They are independent so users can borrow a palette without
forcing the reference's contrast. Matching an image to itself is neutral.

## Adjustment order

`applyPhotoAdjustments` applies:

1. Reference mean and channel-spread matching.
2. Exposure, using `2 ** exposure` as the multiplier.
3. Luminance-weighted shadow/highlight and black/white adjustments.
4. Contrast, the tone-curve preset, then optional editable master/R/G/B curves.
5. Temperature and tint channel offsets.
6. Global and luminance-weighted shadow/midtone/highlight color grading.
7. Optional eight-range hue/saturation/lightness color mixer.
8. Saturation, vibrance, or monochrome conversion.
9. Radial vignette and bounded 8-bit output.
10. Optional neighborhood sharpening and deterministic film-grain overlay.
11. Enabled local mask adjustments.

If learned enhancement is enabled, its bounded LUT transform is applied before
the above sequence. It is separate from reference matching and has its own
strength. See [learned enhancement](learned-enhancement.md).

Crop, rotation, and flip are geometric canvas operations after pixel processing.
Alpha is preserved by the pixel engine. JPEG export composites transparency onto
white because JPEG does not carry alpha.

Film grain provides strength (0-100) and size (1-8) controls and can be applied
inside a mask. It adds the same noise value to R/G/B, is stable across renders,
and uses normalized source coordinates before crop/rotation. Zero strength leaves
pixels untouched. It is a creative effect, not recovered photographic detail;
final clamping can clip bright/dark noise at the output bounds.

## Important trade-offs

- Calculations use browser-decoded, gamma-encoded sRGB values, not a calibrated
  scene-linear or perceptually uniform color pipeline.
- Channel statistics do not identify skin, sky, subjects, or lighting sources.
- Editable curves support up to 16 ordered points per channel, with numeric 0-255
  input/output values. Shape-preserving cubic interpolation avoids overshoot between
  monotonic points; users can deliberately draw nonmonotonic curves. Processing uses
  1024-sample per-channel tables with linear lookup interpolation.
- The color mixer interpolates smoothly between eight hue-band centers, not semantic
  objects or every unique pixel color. Achromatic pixels remain protected. Mix controls
  work globally or within a mask and are part of undo/redo and exported settings.
- Grading ranges overlap smoothly using source luminance weights.
- Preview and export use the same algorithm, but sharpening depends on pixel scale.
- The histogram is a diagnostic luminance estimate, not a calibrated exposure meter.
- Clamping can discard out-of-range values; no algorithm restores clipped source detail.

These choices make the baseline understandable and testable. Improving perceptual
matching, color management, and edge-preserving detail requires measured comparison
against real photographs before changing public quality claims.

## Quality-preserving efficiency

Neutral curves bypass sine calculations; zero white/black/vignette settings skip their
unused math. Intermediate local-mask passes omit unused histograms. Cached display
overlays avoid rerasterizing unchanged geometry. Pixel and histogram regression hashes
cover the existing neutral, tone, grading, matching, and detail paths. These shortcuts
do not reduce export dimensions, image bit depth, or encoder quality; preview sizing
remains separate from the original-resolution export.
