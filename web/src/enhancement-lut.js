/** The research LUT layout is channel / blue / green / red, not RGB-interleaved. */
export function interpolateEnhancement(lut, rgb) {
  const size = 33,
    plane = size ** 3,
    scale = 32 / 1.0001;
  const coordinates = rgb.map((v) => Math.max(0, Math.min(1, v)) * scale);
  const low = coordinates.map(Math.floor),
    fraction = coordinates.map((v, i) => v - low[i]);
  const out = [0, 0, 0];
  for (let b = 0; b < 2; b++)
    for (let g = 0; g < 2; g++)
      for (let r = 0; r < 2; r++) {
        const weight =
          (r ? fraction[0] : 1 - fraction[0]) *
          (g ? fraction[1] : 1 - fraction[1]) *
          (b ? fraction[2] : 1 - fraction[2]);
        const offset =
          (low[2] + b) * size * size + (low[1] + g) * size + low[0] + r;
        for (let channel = 0; channel < 3; channel++)
          out[channel] += lut[channel * plane + offset] * weight;
      }
  return out;
}

/** Enhancement cannot shift an individual channel by more than 0.25 at full strength. */
export function blendEnhancement(rgb, lut, strength) {
  const enhanced = interpolateEnhancement(lut, rgb),
    amount = Math.max(0, Math.min(100, strength)) / 100;
  return rgb.map(
    (v, c) => v + Math.max(-0.25, Math.min(0.25, enhanced[c] - v)) * amount,
  );
}

/** Allocation-free equivalent used by the full-image rendering loop. */
export function blendEnhancementInto(r, g, b, lut, strength, out) {
  const scale = 32 / 1.0001,
    size = 33,
    plane = size ** 3;
  const x = Math.max(0, Math.min(1, r)) * scale,
    y = Math.max(0, Math.min(1, g)) * scale,
    z = Math.max(0, Math.min(1, b)) * scale,
    ix = Math.floor(x),
    iy = Math.floor(y),
    iz = Math.floor(z),
    fx = x - ix,
    fy = y - iy,
    fz = z - iz;
  out[0] = out[1] = out[2] = 0;
  for (let dz = 0; dz < 2; dz++)
    for (let dy = 0; dy < 2; dy++)
      for (let dx = 0; dx < 2; dx++) {
        const weight =
          (dx ? fx : 1 - fx) * (dy ? fy : 1 - fy) * (dz ? fz : 1 - fz);
        const offset = (iz + dz) * size * size + (iy + dy) * size + ix + dx;
        for (let channel = 0; channel < 3; channel++)
          out[channel] += lut[channel * plane + offset] * weight;
      }
  const amount = Math.max(0, Math.min(100, strength)) / 100;
  out[0] = r + Math.max(-0.25, Math.min(0.25, out[0] - r)) * amount;
  out[1] = g + Math.max(-0.25, Math.min(0.25, out[1] - g)) * amount;
  out[2] = b + Math.max(-0.25, Math.min(0.25, out[2] - b)) * amount;
}

export function validateEnhancementLut(lut) {
  if (
    !(lut instanceof Float32Array) ||
    lut.length !== 3 * 33 ** 3 ||
    lut.some((v) => !Number.isFinite(v) || Math.abs(v) > 5)
  )
    throw new Error(
      "The enhancement model returned an invalid color transform.",
    );
}

/** Reduce the initial suggestion if it introduces over one percentage point of clipping. */
export function assessEnhancement(pixels, lut, strengths = [35, 25, 15, 0]) {
  validateEnhancementLut(lut);
  const clipped = (rgb) => rgb.some((v) => v <= 0 || v >= 1);
  let count = 0,
    before = 0;
  for (let i = 0; i < pixels.length; i += 4) {
    if (pixels[i + 3] < 128) continue;
    count++;
    if (clipped([pixels[i] / 255, pixels[i + 1] / 255, pixels[i + 2] / 255]))
      before++;
  }
  if (!count)
    throw new Error("No opaque pixels are available for enhancement.");
  for (const strength of strengths) {
    let after = 0,
      change = 0;
    for (let i = 0; i < pixels.length; i += 4) {
      if (pixels[i + 3] < 128) continue;
      const rgb = [pixels[i] / 255, pixels[i + 1] / 255, pixels[i + 2] / 255],
        out = blendEnhancement(rgb, lut, strength);
      if (clipped(out)) after++;
      change += out.reduce((sum, v, c) => sum + Math.abs(v - rgb[c]), 0) / 3;
    }
    if (after / count <= before / count + 0.01 || strength === 0)
      return {
        recommendedStrength: strength,
        clippingBefore: before / count,
        clippingAfter: after / count,
        meanChannelChange: change / count,
      };
  }
}
