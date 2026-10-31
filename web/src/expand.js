/** Borders are output geometry, not generated image content. Percentages refer to the cropped image. */
export function expandedGeometry(width, height, expand = {}) {
  expand ??= {};
  const safe = (value) =>
    Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  const left = Math.round((width * safe(expand.left)) / 100);
  const right = Math.round((width * safe(expand.right)) / 100);
  const top = Math.round((height * safe(expand.top)) / 100);
  const bottom = Math.round((height * safe(expand.bottom)) / 100);
  return {
    left,
    right,
    top,
    bottom,
    width: width + left + right,
    height: height + top + bottom,
  };
}

export function assertOutputSize(width, height) {
  if (
    !Number.isSafeInteger(width) ||
    !Number.isSafeInteger(height) ||
    width < 1 ||
    height < 1 ||
    width * height > 50_000_000 ||
    Math.max(width, height) > 16384
  )
    throw new Error(
      "Expanded output exceeds the safe canvas limit. Reduce the borders or image size.",
    );
}
