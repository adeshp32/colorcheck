import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeDepth,
  sampleDepth,
  depthInputSize,
  focusAtPoint,
  focusBounds,
  settingsForFocusBounds,
} from "../web/src/depth-map.js";
import {
  blurRadius,
  focusWeight,
  applyLensBlur,
} from "../web/src/lens-blur.js";
import { createDefaultEditSettings } from "../web/src/image-processing.js";
test("depth normalization rejects invalid and uninformative maps", () => {
  assert.throws(() => normalizeDepth([1, NaN], 2, 1), /Invalid/);
  assert.throws(() => normalizeDepth([1, 1], 2, 1), /reliable depth/);
  const values = normalizeDepth([0, 1, 2, 3, 4], 5, 1);
  assert.equal(values[0], 0);
  assert.equal(values[4], 1);
  assert.equal(
    sampleDepth(
      { values: new Float32Array([0, 1, 0, 1]), width: 2, height: 2 },
      0.5,
      0.5,
    ),
    0.5,
  );
});

test("focus selection derives a bounded local band and range handles preserve valid ordering", () => {
  const values = Float32Array.from({ length: 100 }, (_, i) =>
    i % 10 < 5 ? 0.2 : 0.8,
  );
  const map = { values, width: 10, height: 10 };
  const far = focusAtPoint(map, 0.1, 0.5),
    near = focusAtPoint(map, 0.9, 0.5);
  assert.ok(far.focus < near.focus);
  assert.ok(far.range >= 3 && far.range <= 18);
  assert.deepEqual(near.focusPoint, { x: 0.9, y: 0.5 });
  const settings = settingsForFocusBounds(25, 70);
  assert.deepEqual(focusBounds(settings), { low: 25, high: 70 });
  const edge = focusBounds(settingsForFocusBounds(100, -1));
  assert.ok(edge.low >= 0 && edge.high <= 100 && edge.high - edge.low >= 1);
});
test("analysis sizes are bounded patch multiples, preserving ordinary aspect ratios", () => {
  const size = depthInputSize(4032, 3024, 518);
  assert.equal(size.width % 14, 0);
  assert.equal(size.height % 14, 0);
  assert.ok(size.width <= 518 && size.height <= 518);
});
test("lens blur is opt-in, focus band is sharp, radius scales with resolution", () => {
  const edits = createDefaultEditSettings(),
    pixels = new Uint8ClampedArray([1, 2, 3, 255]);
  assert.equal(applyLensBlur(pixels, 1, 1, edits), pixels);
  assert.equal(focusWeight(0.5, edits.lensBlur), 0);
  assert.equal(focusWeight(0.9, edits.lensBlur), 0);
  assert.ok(focusWeight(0, edits.lensBlur) > 0);
  assert.equal(
    blurRadius({ amount: 50 }, 800, 600) * 2,
    blurRadius({ amount: 50 }, 1600, 1200),
  );
  edits.lensBlur.enabled = true;
  assert.throws(
    () => applyLensBlur(pixels, 1, 1, edits),
    /Analyze scene depth/,
  );
  assert.throws(
    () => applyLensBlur(pixels, 1, 1, edits, null, 0),
    /safe image limit/,
  );
});
