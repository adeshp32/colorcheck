import assert from "node:assert/strict";
import test from "node:test";
import {
  ADAPTIVE_FEATURE_NAMES,
  adaptiveFeatures,
  guardAdaptiveStrengths,
  predictAdaptiveStrengths,
} from "../web/src/adaptive-reference-match.js";

const source = { mean: [0.4, 0.5, 0.6], std: [0.1, 0.2, 0.3] };
const reference = { mean: [0.5, 0.4, 0.6], std: [0.2, 0.2, 0.15] };

test("feature order contains only target and reference measurements", () => {
  const expected = [
    0.4, 0.5, 0.6, 0.5, 0.4, 0.6, 0.1, 0.2, 0.3, 0.2, 0.2, 0.15, 0.1, -0.1, 0,
    0.1, 0, -0.15,
  ];
  adaptiveFeatures(source, reference).forEach((value, index) =>
    assert.ok(Math.abs(value - expected[index]) < 1e-12),
  );
});

test("fitted coefficients use fixed, bounded browser arithmetic", () => {
  const policy = {
    featureNames: ADAPTIVE_FEATURE_NAMES,
    mean: Array(18).fill(0),
    scale: Array(18).fill(1),
    coefficients: [Array(18).fill(0), Array(18).fill(0)],
    intercepts: [0.65, 0.45],
  };
  assert.deepEqual(
    predictAdaptiveStrengths(source, reference, policy),
    [0.65, 0.45],
  );
  policy.coefficients[0][12] = 10;
  assert.deepEqual(
    predictAdaptiveStrengths(source, reference, policy),
    [1, 0.45],
  );
  assert.throws(
    () =>
      predictAdaptiveStrengths(source, reference, {
        ...policy,
        featureNames: [],
      }),
    /schema/,
  );
});

test("guard reduces predicted strengths when they newly clip the target", () => {
  const pixels = new Uint8ClampedArray([
    200, 100, 80, 255, 210, 100, 80, 255, 220, 100, 80, 255, 230, 100, 80, 255,
  ]);
  const match = {
    source: [0.84, 0.4, 0.32],
    reference: [1, 0.4, 0.32],
    gain: [1, 1, 1],
  };
  const guarded = guardAdaptiveStrengths(pixels, match, [1, 0.5]);
  assert.ok(guarded[0] < 1);
  assert.ok(guarded[0] >= 0);
  assert.ok(guarded[1] < 0.5);
  assert.deepEqual(guardAdaptiveStrengths(pixels, match, [0, 0]), [0, 0]);
});
