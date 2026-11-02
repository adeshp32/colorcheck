/** Shape-preserving cubic Hermite interpolation with sorted, bounded control points. */
export function constrainCurvePoint(points, index, x, y) {
  const last = points.length - 1,
    previous = points[index - 1],
    next = points[index + 1],
    spacing = 8 / 255;
  let safeX = index === 0 ? 0 : index === last ? 1 : x;
  if (previous && next) {
    const available = Math.max(0, next.x - previous.x),
      safeSpacing = Math.min(spacing, available / 3);
    safeX = Math.max(
      previous.x + safeSpacing,
      Math.min(next.x - safeSpacing, safeX),
    );
  }
  const previousY = previous?.y ?? 0,
    nextY = next?.y ?? 1,
    availableY = Math.max(0, nextY - previousY),
    verticalSpacing = Math.min(4 / 255, availableY / 3),
    minimumY = previous ? previousY + verticalSpacing : 0,
    maximumY = next ? nextY - verticalSpacing : 1;
  return {
    x: Math.max(0, Math.min(1, safeX)),
    y: Math.max(minimumY, Math.min(maximumY, y)),
  };
}

export function sampleCurve(points, value) {
  const x = Math.max(0, Math.min(1, value));
  if (!points || points.length < 2) return x;
  const n = points.length,
    h = [],
    slope = [];
  for (let i = 0; i < n - 1; i++) {
    h.push(Math.max(0.000001, points[i + 1].x - points[i].x));
    slope.push((points[i + 1].y - points[i].y) / h[i]);
  }
  const tangent = (i) => {
    if (i === 0) return slope[0];
    if (i === n - 1) return slope[n - 2];
    if (slope[i - 1] * slope[i] <= 0) return 0;
    const a = 2 * h[i] + h[i - 1],
      b = h[i] + 2 * h[i - 1];
    return (a + b) / (a / slope[i - 1] + b / slope[i]);
  };
  let i = 0;
  while (i < n - 2 && x > points[i + 1].x) i++;
  const t = (x - points[i].x) / h[i],
    t2 = t * t,
    t3 = t2 * t;
  const y =
    (2 * t3 - 3 * t2 + 1) * points[i].y +
    (t3 - 2 * t2 + t) * h[i] * tangent(i) +
    (-2 * t3 + 3 * t2) * points[i + 1].y +
    (t3 - t2) * h[i] * tangent(i + 1);
  return Math.max(0, Math.min(1, y));
}
export function buildCurveTable(points) {
  if (!points) return null;
  return Float32Array.from({ length: 1024 }, (_, i) =>
    sampleCurve(points, i / 1023),
  );
}
export function lookupCurve(table, value) {
  if (!table) return value;
  const x = Math.max(0, Math.min(1, value)) * 1023,
    i = Math.floor(x),
    next = Math.min(1023, i + 1);
  return table[i] + (table[next] - table[i]) * (x - i);
}
