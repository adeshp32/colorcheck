/** Histogram transfer inspired by hahnec/color-matcher's HM method. */
const LEVELS = 256;

function histogram(pixels) {
  if (pixels.length % 4 !== 0) throw new Error("Expected RGBA pixels");
  const counts = [
    new Uint32Array(LEVELS),
    new Uint32Array(LEVELS),
    new Uint32Array(LEVELS),
  ];
  let opaque = 0;
  for (let i = 0; i < pixels.length; i += 4) {
    if (pixels[i + 3] < 128) continue;
    opaque++;
    for (let channel = 0; channel < 3; channel++)
      counts[channel][pixels[i + channel]]++;
  }
  if (!opaque) throw new Error("Matching requires opaque pixels");
  return { counts, opaque };
}

function cumulative(counts) {
  const result = new Float64Array(LEVELS);
  let total = 0;
  for (let level = 0; level < LEVELS; level++) {
    total += counts[level];
    result[level] = total;
  }
  for (let level = 0; level < LEVELS; level++) result[level] /= total;
  return result;
}

export function buildHistogramMaps(sourcePixels, referencePixels) {
  const source = histogram(sourcePixels);
  const reference = histogram(referencePixels);
  return source.counts.map((counts, channel) => {
    const sourceCdf = cumulative(counts);
    const referenceCdf = cumulative(reference.counts[channel]);
    const map = new Uint8Array(LEVELS);
    let destination = 0;
    for (let level = 0; level < LEVELS; level++) {
      while (
        destination < LEVELS - 1 &&
        referenceCdf[destination] < sourceCdf[level]
      )
        destination++;
      map[level] = destination;
    }
    return map;
  });
}

export function applyHistogramMaps(pixels, maps, strength = 1) {
  if (pixels.length % 4 !== 0) throw new Error("Expected RGBA pixels");
  if (!Number.isFinite(strength) || strength < 0 || strength > 1)
    throw new RangeError("Strength must be between zero and one");
  if (maps.length !== 3 || maps.some((map) => map.length !== LEVELS))
    throw new Error("Expected three 256-level maps");
  const output = new Uint8ClampedArray(pixels.length);
  for (let i = 0; i < pixels.length; i += 4) {
    if (pixels[i + 3] < 128) {
      output.set(pixels.subarray(i, i + 4), i);
      continue;
    }
    for (let channel = 0; channel < 3; channel++) {
      const original = pixels[i + channel];
      output[i + channel] =
        original + (maps[channel][original] - original) * strength;
    }
    output[i + 3] = pixels[i + 3];
  }
  return output;
}
