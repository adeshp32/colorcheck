/** Resolution-independent masks live in source-image coordinates, before cropping. */
const bound = (v) => Math.max(0, Math.min(1, v));
const smooth = (v) => {
  const t = bound(v);
  return t * t * (3 - 2 * t);
};

export function createMaskComponent(type = "radial", operation = "add") {
  return {
    type,
    operation,
    x: 0.5,
    y: 0.5,
    rx: 0.3,
    ry: 0.3,
    angle: 0,
    x2: 0.8,
    y2: 0.5,
    feather: 0.5,
  };
}
export function componentCoverage(component, x, y) {
  const dx = x - component.x,
    dy = y - component.y;
  if (component.type === "linear") {
    const vx = component.x2 - component.x,
      vy = component.y2 - component.y;
    return (
      1 - smooth((dx * vx + dy * vy) / Math.max(0.000001, vx * vx + vy * vy))
    );
  }
  const angle = (component.angle * Math.PI) / 180,
    cos = component.cos ?? Math.cos(angle),
    sin = component.sin ?? Math.sin(angle);
  const a = (dx * cos + dy * sin) / Math.max(0.0001, component.rx),
    b = (-dx * sin + dy * cos) / Math.max(0.0001, component.ry),
    distance = Math.sqrt(a * a + b * b);
  if (component.feather <= 0) return distance <= 1 ? 1 : 0;
  return 1 - smooth((distance - (1 - component.feather)) / component.feather);
}
/** Hoist geometry constants outside preview/export pixel loops. */
export function prepareMask(mask) {
  return {
    ...mask,
    components: mask.components.map((component) => ({
      ...component,
      cos: Math.cos((component.angle * Math.PI) / 180),
      sin: Math.sin((component.angle * Math.PI) / 180),
    })),
  };
}
export function maskCoverage(mask, x, y, rgb) {
  let coverage = 0;
  for (const component of mask.components) {
    const value = componentCoverage(component, x, y);
    if (component.operation === "subtract") coverage *= 1 - value;
    else if (component.operation === "intersect") coverage *= value;
    else coverage = Math.max(coverage, value);
  }
  if (mask.invert) coverage = 1 - coverage;
  if (mask.refinement === "luminance") {
    const l = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255;
    const feather = Math.max(0.001, mask.rangeSoftness ?? 0.1);
    coverage *=
      smooth((l - mask.lumaMin + feather) / feather) *
      smooth((mask.lumaMax + feather - l) / feather);
  } else if (mask.refinement === "color") {
    const color = mask.color ?? [128, 128, 128];
    const distance =
      Math.hypot(rgb[0] - color[0], rgb[1] - color[1], rgb[2] - color[2]) /
      (255 * Math.sqrt(3));
    coverage *=
      1 - smooth(distance / Math.max(0.001, mask.colorTolerance ?? 0.25));
  }
  return bound(coverage * (mask.opacity ?? 1));
}

/** Inverse of canvas rotation/flip; used for direct manipulation on the full-photo view. */
export function sourcePoint(u, v, width, height, settings) {
  const angle = (settings.rotation * Math.PI) / 180,
    cos = Math.cos(angle),
    sin = Math.sin(angle);
  const swapped = Math.abs(settings.rotation % 180) === 90;
  const x = (u - 0.5) * (swapped ? height : width),
    y = (v - 0.5) * (swapped ? width : height);
  return {
    x: bound(((x * cos + y * sin) * (settings.flip ? -1 : 1)) / width + 0.5),
    y: bound((-x * sin + y * cos) / height + 0.5),
  };
}

export function hasLocalAdjustments(edits) {
  if (
    edits.colorMix &&
    Object.values(edits.colorMix).some(
      (band) => band.hue || band.saturation || band.lightness,
    )
  )
    return true;
  if (
    edits.curves &&
    Object.values(edits.curves).some((points) =>
      points?.some((point) => point.x !== point.y),
    )
  )
    return true;
  return (
    [
      "exposure",
      "contrast",
      "highlights",
      "shadows",
      "whites",
      "blacks",
      "temperature",
      "tint",
      "saturation",
      "vibrance",
      "sharpen",
      "vignette",
      "grain",
      "enhanceStrength",
    ].some((key) => edits[key] !== 0) ||
    edits.bw ||
    edits.curve !== "linear" ||
    (edits.match &&
      (edits.matchColor ||
        edits.matchTone ||
        edits.matchDistributionStrength ||
        edits.matchV11Strength)) ||
    Object.values(edits.grades).some(
      (grade) => grade.amount && grade.saturation,
    )
  );
}

/** Two-finger source-space transform, independent of photo zoom and screen density. */
export function transformMaskPinch(
  shape,
  start,
  current,
  allowRotation = false,
) {
  const clamp = (v, min = 0, max = 1) => Math.max(min, Math.min(max, v));
  const vector = (points) => ({
    x: points[1].x - points[0].x,
    y: points[1].y - points[0].y,
  });
  const a = vector(start),
    b = vector(current);
  const scale = Math.hypot(b.x, b.y) / Math.max(0.0001, Math.hypot(a.x, a.y));
  const angle = allowRotation ? Math.atan2(b.y, b.x) - Math.atan2(a.y, a.x) : 0;
  const dx = (current[0].x + current[1].x - start[0].x - start[1].x) / 2;
  const dy = (current[0].y + current[1].y - start[0].y - start[1].y) / 2;
  if (shape.type === "radial")
    return {
      ...shape,
      x: clamp(shape.x + dx),
      y: clamp(shape.y + dy),
      rx: clamp(shape.rx * scale, 0.005, 1.5),
      ry: clamp(shape.ry * scale, 0.005, 1.5),
      angle: ((shape.angle + (angle * 180) / Math.PI + 540) % 360) - 180,
    };
  const cx = (shape.x + shape.x2) / 2 + dx,
    cy = (shape.y + shape.y2) / 2 + dy;
  const vx = ((shape.x2 - shape.x) * scale) / 2,
    vy = ((shape.y2 - shape.y) * scale) / 2;
  const rx = vx * Math.cos(angle) - vy * Math.sin(angle),
    ry = vx * Math.sin(angle) + vy * Math.cos(angle);
  return {
    ...shape,
    x: clamp(cx - rx),
    y: clamp(cy - ry),
    x2: clamp(cx + rx),
    y2: clamp(cy + ry),
  };
}

/** Rotate around the shape's center only when the explicit rotate control is active. */
export function rotateMaskComponent(shape, start, current) {
  const cx = shape.type === "linear" ? (shape.x + shape.x2) / 2 : shape.x;
  const cy = shape.type === "linear" ? (shape.y + shape.y2) / 2 : shape.y;
  const delta =
    Math.atan2(current.y - cy, current.x - cx) -
    Math.atan2(start.y - cy, start.x - cx);
  if (shape.type === "radial")
    return {
      ...shape,
      angle: ((shape.angle + (delta * 180) / Math.PI + 540) % 360) - 180,
    };
  const rotate = (x, y) => ({
    x: cx + (x - cx) * Math.cos(delta) - (y - cy) * Math.sin(delta),
    y: cy + (x - cx) * Math.sin(delta) + (y - cy) * Math.cos(delta),
  });
  const first = rotate(shape.x, shape.y);
  const last = rotate(shape.x2, shape.y2);
  if (
    [first.x, first.y, last.x, last.y].some((value) => value < 0 || value > 1)
  )
    return shape;
  return { ...shape, x: first.x, y: first.y, x2: last.x, y2: last.y };
}
