/** Oklab conversion: Bjorn Ottosson, https://bottosson.github.io/posts/oklab/.
 * Original bounded chroma transfer; no model or upstream matcher code is used.
 */
const bound = (v, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, v));
const smooth = (v) => (v = bound(v)) * v * (3 - 2 * v);
const linear = (v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
const encoded = (v) =>
  v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055;

export function rgbToOklab(r, g, b, out = new Float64Array(3)) {
  r = linear(r);
  g = linear(g);
  b = linear(b);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  out[0] = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  out[1] = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  out[2] = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  return out;
}
function labToLinear(L, a, b, out) {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  out[0] = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
  out[1] = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
  out[2] = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s;
}
function inGamut(rgb) {
  return (
    rgb[0] >= -1e-7 &&
    rgb[0] <= 1.0000001 &&
    rgb[1] >= -1e-7 &&
    rgb[1] <= 1.0000001 &&
    rgb[2] >= -1e-7 &&
    rgb[2] <= 1.0000001
  );
}
/** Reduce chroma on a fixed lightness/hue ray, rather than clipping RGB independently. */
export function oklabToGamutRgb(L, a, b, out = new Float64Array(3)) {
  L = bound(L);
  labToLinear(L, a, b, out);
  if (!inGamut(out)) {
    let low = 0,
      high = 1;
    for (let i = 0; i < 12; i++) {
      const scale = (low + high) / 2;
      labToLinear(L, a * scale, b * scale, out);
      if (inGamut(out)) low = scale;
      else high = scale;
    }
    labToLinear(L, a * low, b * low, out);
  }
  for (let c = 0; c < 3; c++) out[c] = bound(encoded(bound(out[c])));
  return out;
}
function weights(L) {
  return [
    Math.max(0, 1 - 2 * L),
    1 - Math.abs(2 * L - 1),
    Math.max(0, 2 * L - 1),
  ];
}
function emptyMoments() {
  return { n: 0, a: 0, b: 0, aa: 0, ab: 0, bb: 0 };
}
function accumulate(m, a, b, weight) {
  m.n += weight;
  m.a += a * weight;
  m.b += b * weight;
  m.aa += a * a * weight;
  m.ab += a * b * weight;
  m.bb += b * b * weight;
}
function finish(m) {
  const n = Math.max(1e-12, m.n),
    a = m.a / n,
    b = m.b / n;
  return {
    mean: [a, b],
    covariance: [
      Math.max(0, m.aa / n - a * a),
      m.ab / n - a * b,
      Math.max(0, m.bb / n - b * b),
    ],
  };
}
function statistics(pixels) {
  if (!pixels.length || pixels.length % 4)
    throw new Error("Matching requires RGBA pixels.");
  const global = emptyMoments(),
    bands = Array.from({ length: 3 }, emptyMoments);
  const histograms = [new Array(256).fill(0), new Array(256).fill(0)];
  const lab = new Float64Array(3);
  let n = 0,
    light = 0,
    light2 = 0;
  for (let i = 0; i < pixels.length; i += 4) {
    if (pixels[i + 3] < 128) continue;
    rgbToOklab(pixels[i] / 255, pixels[i + 1] / 255, pixels[i + 2] / 255, lab);
    const [L, a, b] = lab,
      chromaWeight = smooth((Math.hypot(a, b) - 0.005) / 0.025);
    n++;
    light += L;
    light2 += L * L;
    accumulate(global, a, b, chromaWeight);
    const w = weights(L);
    for (let j = 0; j < 3; j++) accumulate(bands[j], a, b, w[j] * chromaWeight);
    for (let c = 0; c < 2; c++)
      histograms[c][Math.round(bound((lab[c + 1] + 0.4) / 0.8) * 255)]++;
  }
  if (!n) throw new Error("The image has no opaque pixels to match.");
  const meanL = light / n;
  return {
    meanL,
    stdL: Math.sqrt(Math.max(0, light2 / n - meanL ** 2)),
    bands: bands.map((m) => finish(m.n < 8 ? global : m)),
    histograms,
  };
}
function multiply(A, B) {
  return [
    A[0] * B[0] + A[1] * B[2],
    A[0] * B[1] + A[1] * B[3],
    A[2] * B[0] + A[3] * B[2],
    A[2] * B[1] + A[3] * B[3],
  ];
}
function root(cov, regularization = 1e-4) {
  const a = cov[0] + regularization,
    b = cov[1],
    d = cov[2] + regularization;
  const determinant = Math.sqrt(Math.max(0, a * d - b * b));
  const divisor = Math.sqrt(a + d + 2 * determinant);
  return [
    (a + determinant) / divisor,
    b / divisor,
    b / divisor,
    (d + determinant) / divisor,
  ];
}
function inverse(A) {
  const d = A[0] * A[3] - A[1] * A[2];
  return [A[3] / d, -A[1] / d, -A[2] / d, A[0] / d];
}
/** Symmetric whitening/coloring map, with bounded principal-axis gains. */
function covarianceMap(source, reference) {
  const S = root(source),
    inv = inverse(S);
  const R = [
    reference[0] + 1e-4,
    reference[1],
    reference[1],
    reference[2] + 1e-4,
  ];
  const middle = multiply(multiply(S, R), S);
  const middleRoot = root(
    [middle[0], (middle[1] + middle[2]) / 2, middle[3]],
    0,
  );
  const T = multiply(multiply(inv, middleRoot), inv);
  const a = T[0],
    b = (T[1] + T[2]) / 2,
    d = T[3];
  const angle = Math.atan2(2 * b, a - d) / 2,
    c = Math.cos(angle),
    s = Math.sin(angle);
  const radius = Math.hypot(a - d, 2 * b),
    hi = bound((a + d + radius) / 2, 0.65, 1.5),
    lo = bound((a + d - radius) / 2, 0.65, 1.5);
  return [hi * c * c + lo * s * s, (hi - lo) * c * s, hi * s * s + lo * c * c];
}
function quantileMap(source, reference) {
  const n = source.reduce((a, b) => a + b),
    m = reference.reduce((a, b) => a + b);
  if (source.every((v, k) => Math.abs(v / n - reference[k] / m) < 1e-12))
    return source.map((_, i) => i);
  let total = 0,
    target = 0,
    j = 0;
  return source.map((count, i) => {
    total += count / n;
    while (j < 255 && target + reference[j] / m < total - 1e-12)
      target += reference[j++] / m;
    return j;
  });
}
export function buildPerceptualMatch(sourcePixels, referencePixels) {
  const source = statistics(sourcePixels),
    reference = statistics(referencePixels);
  return {
    version: 1,
    identity: JSON.stringify(source) === JSON.stringify(reference),
    sourceLightness: source.meanL,
    referenceLightness: reference.meanL,
    lightnessGain: bound(
      reference.stdL / Math.max(source.stdL, 0.02),
      0.65,
      1.5,
    ),
    bands: source.bands.map((s, i) => ({
      source: s.mean,
      reference: reference.bands[i].mean,
      matrix: covarianceMap(s.covariance, reference.bands[i].covariance),
    })),
    maps: source.histograms.map((hist, i) =>
      quantileMap(hist, reference.histograms[i]),
    ),
  };
}
function quantile(value, map) {
  const x = bound((value + 0.4) / 0.8) * 255,
    i = Math.floor(x),
    t = x - i;
  return ((map[i] * (1 - t) + map[Math.min(255, i + 1)] * t) / 255) * 0.8 - 0.4;
}
/** Allocation-free pixel path; scratch/output are reused by the render loop. */
export function applyPerceptualMatch(
  r,
  g,
  b,
  match,
  palette,
  tone,
  detail,
  out,
  scratch,
) {
  if (match.identity || (!palette && !tone && !detail)) {
    out[0] = r;
    out[1] = g;
    out[2] = b;
    return;
  }
  rgbToOklab(r, g, b, scratch);
  const L = scratch[0],
    a = scratch[1],
    bb = scratch[2];
  const midWeight = 1 - Math.abs(2 * L - 1);
  let da = 0,
    db = 0;
  for (let i = 0; i < 3; i++) {
    const w =
      i === 0
        ? Math.max(0, 1 - 2 * L)
        : i === 1
          ? midWeight
          : Math.max(0, 2 * L - 1);
    const band = match.bands[i],
      x = a - band.source[0],
      y = bb - band.source[1],
      T = band.matrix;
    da += w * (band.reference[0] + T[0] * x + T[1] * y - a);
    db += w * (band.reference[1] + T[1] * x + T[2] * y - bb);
  }
  const magnitude = Math.hypot(da, db),
    limit = magnitude > 0.08 ? 0.08 / magnitude : 1;
  const protection = smooth((Math.hypot(a, bb) - 0.01) / 0.05);
  da =
    da * limit * palette +
    (detail ? bound(quantile(a, match.maps[0]) - a, -0.04, 0.04) * detail : 0);
  db =
    db * limit * palette +
    (detail
      ? bound(quantile(bb, match.maps[1]) - bb, -0.04, 0.04) * detail
      : 0);
  const lightness = bound(
    L +
      bound(
        match.referenceLightness +
          (L - match.sourceLightness) * match.lightnessGain -
          L,
        -0.15,
        0.15,
      ) *
        tone,
  );
  // Exact neutral input stays neutral, independent of a colored reference.
  if (r === g && g === b) {
    out[0] = out[1] = out[2] = encoded(lightness ** 3);
    return;
  }
  oklabToGamutRgb(lightness, a + da * protection, bb + db * protection, out);
}
