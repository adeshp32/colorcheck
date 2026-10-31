/** Overlapping hue bands avoid hard boundaries between neighboring colors. */
export const COLOR_BANDS = [
  ["red", "Red", 0, "#eb5353"],
  ["orange", "Orange", 30, "#ed9a45"],
  ["yellow", "Yellow", 60, "#e4cc3f"],
  ["green", "Green", 120, "#51b875"],
  ["aqua", "Aqua", 180, "#44c9cc"],
  ["blue", "Blue", 240, "#5586df"],
  ["purple", "Purple", 270, "#a271dc"],
  ["magenta", "Magenta", 300, "#dc64b7"],
];
export function prepareColorMix(mix) {
  if (
    !mix ||
    !Object.values(mix).some(
      (band) => band.hue || band.saturation || band.lightness,
    )
  )
    return null;
  return COLOR_BANDS.map(([id, , center]) => ({
    center,
    hue: mix[id]?.hue ?? 0,
    saturation: (mix[id]?.saturation ?? 0) / 100,
    lightness: (mix[id]?.lightness ?? 0) / 100,
  }));
}
/** Writes into reusable scratch space; achromatic pixels are deliberately protected. */
export function mixColorInto(r, g, b, bands, out) {
  const originalR = r,
    originalG = g,
    originalB = b;
  r = Math.max(0, Math.min(1, r));
  g = Math.max(0, Math.min(1, g));
  b = Math.max(0, Math.min(1, b));
  const max = Math.max(r, g, b),
    min = Math.min(r, g, b),
    delta = max - min;
  if (delta < 1e-8) {
    out[0] = r;
    out[1] = g;
    out[2] = b;
    return;
  }
  let hue =
    max === r
      ? (g - b) / delta
      : max === g
        ? (b - r) / delta + 2
        : (r - g) / delta + 4;
  hue = (hue * 60 + 360) % 360;
  const light = (max + min) / 2,
    sat = delta / (1 - Math.abs(2 * light - 1));
  let left = bands.length - 1;
  for (let i = 0; i < bands.length - 1; i++)
    if (hue >= bands[i].center && hue < bands[i + 1].center) {
      left = i;
      break;
    }
  const a = bands[left],
    bnd = bands[(left + 1) % bands.length];
  const fraction =
    (hue - a.center) /
    ((bnd.center > a.center ? bnd.center : bnd.center + 360) - a.center);
  const t = fraction * fraction * (3 - 2 * fraction),
    inv = 1 - t;
  if (!(
    a.hue * inv + bnd.hue * t ||
    a.saturation * inv + bnd.saturation * t ||
    a.lightness * inv + bnd.lightness * t
  )) {
    out[0] = originalR;
    out[1] = originalG;
    out[2] = originalB;
    return;
  }
  const h = ((hue + a.hue * inv + bnd.hue * t + 360) % 360) / 60;
  const s = Math.max(
    0,
    Math.min(1, sat * (1 + a.saturation * inv + bnd.saturation * t)),
  );
  const l = Math.max(
    0,
    Math.min(
      1,
      light +
        (a.lightness * inv + bnd.lightness * t) * 0.5 * Math.min(1, sat * 4),
    ),
  );
  const chroma = (1 - Math.abs(2 * l - 1)) * s,
    x = chroma * (1 - Math.abs((h % 2) - 1)),
    m = l - chroma / 2;
  const sector = Math.floor(h);
  out[0] =
    (sector === 0 || sector === 5
      ? chroma
      : sector === 1 || sector === 4
        ? x
        : 0) + m;
  out[1] =
    (sector === 1 || sector === 2
      ? chroma
      : sector === 0 || sector === 3
        ? x
        : 0) + m;
  out[2] =
    (sector === 3 || sector === 4
      ? chroma
      : sector === 2 || sector === 5
        ? x
        : 0) + m;
}
