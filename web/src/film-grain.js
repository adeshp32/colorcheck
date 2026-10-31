/** Stable monochrome grain: the same normalized texture is used for preview and export. */
function noise(x, y) {
  let value = Math.imul(x, 374761393) ^ Math.imul(y, 668265263) ^ 1376312589;
  value = Math.imul(value ^ (value >>> 13), 1274126177);
  return ((value ^ (value >>> 16)) >>> 0) / 4294967295 - 0.5;
}
export function grainAt(x, y, width, height, size = 1) {
  const scale = 2048 / (Math.max(width, height) * Math.max(1, size));
  const u = (x + 0.5) * scale,
    v = (y + 0.5) * scale;
  const ix = Math.floor(u),
    iy = Math.floor(v),
    dx = u - ix,
    dy = v - iy;
  const sx = dx * dx * (3 - 2 * dx),
    sy = dy * dy * (3 - 2 * dy);
  const a = noise(ix, iy),
    b = noise(ix + 1, iy),
    c = noise(ix, iy + 1),
    d = noise(ix + 1, iy + 1);
  return (a + (b - a) * sx) * (1 - sy) + (c + (d - c) * sx) * sy;
}
