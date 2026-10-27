/** Browser arithmetic for a small, offline-fitted deterministic match policy. */
export const ADAPTIVE_FEATURE_NAMES = Object.freeze([
  ...["r", "g", "b"].map((channel) => `source_mean_${channel}`),
  ...["r", "g", "b"].map((channel) => `reference_mean_${channel}`),
  ...["r", "g", "b"].map((channel) => `source_std_${channel}`),
  ...["r", "g", "b"].map((channel) => `reference_std_${channel}`),
  ...["r", "g", "b"].map((channel) => `mean_shift_${channel}`),
  ...["r", "g", "b"].map((channel) => `std_shift_${channel}`),
]);

const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

export function adaptiveFeatures(source, reference) {
  const channels = [source.mean, reference.mean, source.std, reference.std];
  if (
    channels.some(
      (values) =>
        values?.length !== 3 || values.some((v) => !Number.isFinite(v)),
    )
  )
    throw new Error("Expected finite RGB means and standard deviations");
  return [
    ...source.mean,
    ...reference.mean,
    ...source.std,
    ...reference.std,
    ...reference.mean.map((value, index) => value - source.mean[index]),
    ...reference.std.map((value, index) => value - source.std[index]),
  ];
}

export function predictAdaptiveStrengths(source, reference, policy) {
  if (
    JSON.stringify(policy?.featureNames) !==
    JSON.stringify(ADAPTIVE_FEATURE_NAMES)
  )
    throw new Error("Adaptive matcher feature schema mismatch");
  const features = adaptiveFeatures(source, reference);
  const { mean, scale, coefficients, intercepts } = policy;
  if (
    mean?.length !== features.length ||
    scale?.length !== features.length ||
    coefficients?.length !== 2 ||
    intercepts?.length !== 2 ||
    coefficients.some((row) => row?.length !== features.length) ||
    [...mean, ...scale, ...coefficients.flat(), ...intercepts].some(
      (v) => !Number.isFinite(v),
    ) ||
    scale.some((v) => v <= 0)
  )
    throw new Error("Invalid adaptive matcher coefficients");
  const normalized = features.map(
    (value, index) => (value - mean[index]) / scale[index],
  );
  return coefficients.map((row, index) =>
    clamp(
      row.reduce(
        (sum, weight, j) => sum + weight * normalized[j],
        intercepts[index],
      ),
      0,
      1,
    ),
  );
}

function clippedFraction(pixels, match, palette, tone) {
  let clipped = 0;
  let visible = 0;
  for (let i = 0; i < pixels.length; i += 4) {
    if (pixels[i + 3] < 128) continue;
    visible++;
    for (let channel = 0; channel < 3; channel++) {
      const value = pixels[i + channel] / 255;
      const output =
        value +
        (match.reference[channel] - match.source[channel]) * palette +
        (value - match.source[channel]) * (match.gain[channel] - 1) * tone;
      if (output <= 1 / 255 || output >= 254 / 255) {
        clipped++;
        break;
      }
    }
  }
  return visible ? clipped / visible : 0;
}

/** Limit new clipping without changing the learned direction of the edit. */
export function guardAdaptiveStrengths(
  pixels,
  match,
  strengths,
  maxAddedClipping = 0.01,
) {
  if (
    pixels.length % 4 ||
    strengths.length !== 2 ||
    strengths.some((v) => !Number.isFinite(v) || v < 0 || v > 1)
  )
    throw new Error("Invalid adaptive match input");
  const allowed = clippedFraction(pixels, match, 0, 0) + maxAddedClipping;
  if (clippedFraction(pixels, match, ...strengths) <= allowed) return strengths;
  let low = 0;
  let high = 1;
  for (let step = 0; step < 10; step++) {
    const middle = (low + high) / 2;
    if (
      clippedFraction(
        pixels,
        match,
        strengths[0] * middle,
        strengths[1] * middle,
      ) <= allowed
    )
      low = middle;
    else high = middle;
  }
  return strengths.map((value) => value * low);
}
