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
      "enhanceStrength",
    ].some((key) => edits[key] !== 0) ||
    edits.bw ||
    edits.curve !== "linear" ||
    (edits.match && (edits.matchColor || edits.matchTone)) ||
    Object.values(edits.grades).some(
      (grade) => grade.amount && grade.saturation,
    )
  );
}
