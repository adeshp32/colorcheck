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
4. Contrast and the selected monotonic tone-curve preset.
5. Temperature and tint channel offsets.
6. Global and luminance-weighted shadow/midtone/highlight color grading.
7. Saturation, vibrance, or monochrome conversion.
8. Radial vignette and bounded 8-bit output.
9. Optional neighborhood sharpening.

If learned enhancement is enabled, its bounded LUT transform is applied before
the above sequence. It is separate from reference matching and has its own
strength. See [learned enhancement](learned-enhancement.md).

Crop, rotation, and flip are geometric canvas operations after pixel processing.
Alpha is preserved by the pixel engine. JPEG export composites transparency onto
white because JPEG does not carry alpha.

## Important trade-offs

- Calculations use browser-decoded, gamma-encoded sRGB values, not a calibrated
  scene-linear or perceptually uniform color pipeline.
- Channel statistics do not identify skin, sky, subjects, or lighting sources.
- Tone-curve presets are monotonic; arbitrary editable curve points are not shipped.
- Grading ranges overlap smoothly using source luminance weights.
- Preview and export use the same algorithm, but sharpening depends on pixel scale.
- The histogram is a diagnostic luminance estimate, not a calibrated exposure meter.
- Clamping can discard out-of-range values; no algorithm restores clipped source detail.

These choices make the baseline understandable and testable. Improving perceptual
matching, color management, and edge-preserving detail requires measured comparison
against real photographs before changing public quality claims.
