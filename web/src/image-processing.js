import { blendEnhancementInto } from "./enhancement-lut.js";
export const clamp = (v, min = 0, max = 1) => Math.min(max, Math.max(min, v));
/** Neutral, serializable settings. Crop coordinates and strengths are percentages. */
export function createDefaultEditSettings() {
  return {
    exposure: 0,
    enhancementId: null,
    enhanceStrength: 0,
    contrast: 0,
    highlights: 0,
    shadows: 0,
    whites: 0,
    blacks: 0,
    temperature: 0,
    tint: 0,
    saturation: 0,
    vibrance: 0,
    sharpen: 0,
    vignette: 0,
    bw: false,
    curve: "linear",
    matchColor: 0,
    matchTone: 0,
    match: null,
    rotation: 0,
    flip: false,
    crop: { x: 0, y: 0, w: 100, h: 100 },
    grades: Object.fromEntries(
      ["global", "shadows", "midtones", "highlights"].map((k) => [
        k,
        { hue: 0, saturation: 0, amount: 20 },
      ]),
    ),
  };
}
/** Mean/spread in normalized RGB; mostly transparent pixels do not affect the match. */
export function calculateChannelStatistics(data) {
  const mean = [0, 0, 0],
    variance = [0, 0, 0];
  let count = 0;
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] < 128) continue;
    count++;
    for (let c = 0; c < 3; c++) mean[c] += data[i + c] / 255;
  }
  if (!count) throw new Error("The image has no opaque pixels to match.");
  for (let c = 0; c < 3; c++) mean[c] /= count;
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] < 128) continue;
    for (let c = 0; c < 3; c++)
      variance[c] += (data[i + c] / 255 - mean[c]) ** 2;
  }
  return { mean, std: variance.map((v) => Math.sqrt(v / count)) };
}
/** Derive bounded spread gains and mean offsets; this is not learned inference. */
export function calculateReferenceMatch(source, reference) {
  return {
    gain: source.std.map((v, c) =>
      clamp(reference.std[c] / Math.max(v, 0.015), 0.65, 1.5),
    ),
    source: source.mean,
    reference: reference.mean,
  };
}
export function hueToRgb(hue) {
  const h = (((hue % 360) + 360) % 360) / 60,
    x = 1 - Math.abs((h % 2) - 1);
  return [
    [1, x, 0],
    [x, 1, 0],
    [0, 1, x],
    [0, x, 1],
    [x, 0, 1],
    [1, 0, x],
  ][Math.floor(h)];
}
export function applyToneCurve(v, name) {
  if (name === "matte") return 0.035 + 0.93 * v;
  const amount = name === "strong" ? 0.35 : name === "soft" ? 0.16 : 0;
  return clamp(v + amount * Math.sin((v - 0.5) * Math.PI * 2) * 0.25);
}
/**
 * Pure RGBA transformation shared by preview and export. Does not mutate input.
 * Processing is gamma-encoded sRGB, not scene-linear camera RAW processing.
 * Returns an 8-bit pixel buffer and a diagnostic 64-bin luminance histogram.
 */
export function applyPhotoAdjustments(
  data,
  width,
  height,
  edits,
  enhancementLut = null,
) {
  const out = new Uint8ClampedArray(data.length),
    grades = Object.entries(edits.grades)
      .filter(([, g]) => g.amount && g.saturation)
      .map(([range, g]) => {
        const rgb = hueToRgb(g.hue),
          mean = rgb.reduce((a, b) => a + b, 0) / 3;
        return {
          range,
          rgb: rgb.map(
            (v) =>
              (((((v - mean) * g.saturation) / 100) * g.amount) / 100) * 0.35,
          ),
        };
      });
  const histogram = new Uint32Array(64);
  const exposure = 2 ** edits.exposure,
    contrast = 1 + edits.contrast / 100,
    temperature = (edits.temperature / 100) * 0.08,
    tintRed = (edits.tint / 100) * 0.03,
    tintGreen = (edits.tint / 100) * 0.06,
    matchColor = edits.matchColor / 100,
    matchTone = edits.matchTone / 100,
    enhanced = new Float64Array(3);
  // Scalars avoid allocating multiple RGB arrays and callbacks for every pixel.
  for (let i = 0; i < data.length; i += 4) {
    let r = data[i] / 255,
      g = data[i + 1] / 255,
      b = data[i + 2] / 255;
    if (enhancementLut && edits.enhanceStrength > 0) {
      blendEnhancementInto(
        r,
        g,
        b,
        enhancementLut,
        edits.enhanceStrength,
        enhanced,
      );
      r = enhanced[0];
      g = enhanced[1];
      b = enhanced[2];
    }
    if (edits.match) {
      const m = edits.match;
      r =
        r +
        (m.reference[0] - m.source[0]) * matchColor +
        (r - m.source[0]) * (m.gain[0] - 1) * matchTone;
      g =
        g +
        (m.reference[1] - m.source[1]) * matchColor +
        (g - m.source[1]) * (m.gain[1] - 1) * matchTone;
      b =
        b +
        (m.reference[2] - m.source[2]) * matchColor +
        (b - m.source[2]) * (m.gain[2] - 1) * matchTone;
    }
    r *= exposure;
    g *= exposure;
    b *= exposure;
    const l = clamp(0.2126 * r + 0.7152 * g + 0.0722 * b);
    const shadow = (1 - l) ** 2,
      highlight = l * l;
    const lift =
      (edits.shadows / 100) * shadow * 0.25 +
      (edits.highlights / 100) * highlight * 0.25 +
      (edits.blacks / 100) * (1 - l) ** 4 * 0.15 +
      (edits.whites / 100) * l ** 4 * 0.15;
    r = applyToneCurve((r - 0.5) * contrast + 0.5 + lift, edits.curve);
    g = applyToneCurve((g - 0.5) * contrast + 0.5 + lift, edits.curve);
    b = applyToneCurve((b - 0.5) * contrast + 0.5 + lift, edits.curve);
    r += temperature;
    b -= temperature;
    g -= tintGreen;
    r += tintRed;
    b += tintRed;
    for (const grade of grades) {
      const weight =
        grade.range === "global"
          ? 1
          : grade.range === "shadows"
            ? shadow
            : grade.range === "highlights"
              ? highlight
              : 4 * l * (1 - l);
      r += grade.rgb[0] * weight;
      g += grade.rgb[1] * weight;
      b += grade.rgb[2] * weight;
    }
    const gray = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    const chroma = Math.max(r, g, b) - Math.min(r, g, b),
      sat = edits.bw
        ? 0
        : Math.max(
            0,
            1 +
              edits.saturation / 100 +
              (edits.vibrance / 100) * (1 - clamp(chroma)),
          );
    const px = (i / 4) % width,
      py = Math.floor(i / 4 / width),
      radius = ((px / width - 0.5) ** 2 + (py / height - 0.5) ** 2) * 2;
    const vignette = 1 - (edits.vignette / 100) * radius * 0.65;
    out[i] = clamp((gray + (r - gray) * sat) * vignette) * 255;
    out[i + 1] = clamp((gray + (g - gray) * sat) * vignette) * 255;
    out[i + 2] = clamp((gray + (b - gray) * sat) * vignette) * 255;
    out[i + 3] = data[i + 3];
    histogram[Math.min(63, Math.floor(clamp(gray) * 64))]++;
  }
  if (edits.sharpen > 0) {
    const copy = out.slice(),
      amount = (edits.sharpen / 100) * 0.65;
    for (let y = 1; y < height - 1; y++)
      for (let x = 1; x < width - 1; x++) {
        const i = (y * width + x) * 4;
        for (let c = 0; c < 3; c++) {
          const blur =
            (copy[i - 4 + c] +
              copy[i + 4 + c] +
              copy[i - width * 4 + c] +
              copy[i + width * 4 + c]) /
            4;
          out[i + c] = copy[i + c] + amount * (copy[i + c] - blur);
        }
      }
  }
  return { data: out, histogram };
}
