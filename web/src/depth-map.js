/** Relative inverse depth: 0 far, 1 near. Never label this as metric distance. */
export function normalizeDepth(values, width, height) {
  if (values.length !== width * height || !width || !height)
    throw new Error("Invalid depth map shape.");
  const sorted = Array.from(values).sort((a, b) => a - b);
  if (sorted.some((value) => !Number.isFinite(value)))
    throw new Error("Invalid depth map values.");
  const low = sorted[Math.floor((sorted.length - 1) * 0.02)];
  const high = sorted[Math.floor((sorted.length - 1) * 0.98)];
  if (high - low < 1e-5)
    throw new Error(
      "No reliable depth separation was found. Try a radial or linear blur.",
    );
  return Float32Array.from(values, (value) =>
    Math.max(0, Math.min(1, (value - low) / (high - low))),
  );
}

export function sampleDepth(map, x, y) {
  const px = Math.max(0, Math.min(map.width - 1, x * map.width - 0.5));
  const py = Math.max(0, Math.min(map.height - 1, y * map.height - 0.5));
  const x0 = Math.floor(px),
    y0 = Math.floor(py),
    tx = px - x0,
    ty = py - y0;
  const at = (xx, yy) =>
    map.values[
      Math.min(map.height - 1, yy) * map.width + Math.min(map.width - 1, xx)
    ];
  return (
    (at(x0, y0) * (1 - tx) + at(x0 + 1, y0) * tx) * (1 - ty) +
    (at(x0, y0 + 1) * (1 - tx) + at(x0 + 1, y0 + 1) * tx) * ty
  );
}

export function depthInputSize(width, height, maximum = 518) {
  const scale = Math.min(1, maximum / Math.max(width, height));
  return {
    width: Math.max(28, Math.round((width * scale) / 14) * 14),
    height: Math.max(28, Math.round((height * scale) / 14) * 14),
  };
}

/** Local depth spread suggests a starting focus band; it is not subject detection. */
export function focusAtPoint(map, x = 0.5, y = 0.5) {
  x = Math.max(0, Math.min(1, x));
  y = Math.max(0, Math.min(1, y));
  const cx = Math.round(x * (map.width - 1)),
    cy = Math.round(y * (map.height - 1));
  const radius = Math.max(
    1,
    Math.round(Math.min(map.width, map.height) * 0.018),
  );
  const samples = [];
  for (
    let yy = Math.max(0, cy - radius);
    yy <= Math.min(map.height - 1, cy + radius);
    yy++
  )
    for (
      let xx = Math.max(0, cx - radius);
      xx <= Math.min(map.width - 1, cx + radius);
      xx++
    )
      samples.push(map.values[yy * map.width + xx]);
  samples.sort((a, b) => a - b);
  const focus = sampleDepth(map, x, y) * 100;
  const low = samples[Math.floor((samples.length - 1) * 0.1)] * 100;
  const high = samples[Math.floor((samples.length - 1) * 0.9)] * 100;
  return {
    focus,
    range: Math.max(3, Math.min(18, Math.max(focus - low, high - focus) + 2)),
    focusPoint: { x, y },
  };
}

export function focusBounds(settings) {
  const focus = Number.isFinite(settings.focus) ? settings.focus : 50;
  const range = Number.isFinite(settings.range) ? settings.range : 12;
  return {
    low: Math.max(0, focus - range),
    high: Math.min(100, focus + range),
  };
}

export function settingsForFocusBounds(low, high) {
  low = Math.max(0, Math.min(99, low));
  high = Math.max(low + 1, Math.min(100, high));
  return { focus: (low + high) / 2, range: (high - low) / 2, focusPoint: null };
}
