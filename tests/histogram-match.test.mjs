import assert from "node:assert/strict";
import test from "node:test";
import {
  applyHistogramMaps,
  buildHistogramMaps,
} from "../web/src/histogram-match.js";
import {
  applyPhotoAdjustments,
  calculateChannelStatistics,
  calculateDistributionMatch,
  calculateReferenceMatch,
  createDefaultEditSettings,
} from "../web/src/image-processing.js";

test("same-image transfer preserves all occupied colors and alpha", () => {
  const pixels = new Uint8ClampedArray([
    12, 42, 88, 255, 12, 42, 88, 255, 170, 190, 230, 255, 20, 30, 40, 0,
  ]);
  const maps = buildHistogramMaps(pixels, pixels);
  assert.deepEqual(applyHistogramMaps(pixels, maps), pixels);
  assert.deepEqual(applyHistogramMaps(pixels, maps, 0), pixels);
});

test("a quantile transfer learns a nonlinear tonal change", () => {
  const source = new Uint8ClampedArray(256 * 4);
  const reference = new Uint8ClampedArray(256 * 4);
  for (let level = 0; level < 256; level++) {
    const offset = level * 4;
    for (let channel = 0; channel < 3; channel++) {
      source[offset + channel] = level;
      reference[offset + channel] = Math.round((level / 255) ** 2 * 255);
    }
    source[offset + 3] = reference[offset + 3] = 255;
  }
  const output = applyHistogramMaps(
    source,
    buildHistogramMaps(source, reference),
  );
  assert.deepEqual(output, reference);
});

test("invalid inputs do not silently produce a transform", () => {
  const empty = new Uint8ClampedArray([0, 0, 0, 0]);
  assert.throws(() => buildHistogramMaps(empty, empty), /opaque/);
  assert.throws(() => buildHistogramMaps(new Uint8Array(3), empty), /RGBA/);
  assert.throws(() => applyHistogramMaps(empty, [], 1), /three/);
  assert.throws(() => applyHistogramMaps(empty, [], 2), /Strength/);
});

test("distribution detail is opt-in, bounded, and shared by the pixel engine", () => {
  const target = new Uint8ClampedArray([
    20, 20, 20, 255, 60, 60, 60, 255, 120, 120, 120, 255, 180, 180, 180, 0,
  ]);
  const reference = new Uint8ClampedArray([
    15, 15, 15, 255, 30, 30, 30, 255, 60, 60, 60, 255, 120, 120, 120, 0,
  ]);
  const edits = createDefaultEditSettings();
  edits.match = calculateDistributionMatch(
    target,
    reference,
    calculateReferenceMatch(
      calculateChannelStatistics(target),
      calculateChannelStatistics(reference),
    ),
  );
  const unchanged = applyPhotoAdjustments(target, 2, 2, edits).data;
  assert.deepEqual(unchanged, target);
  edits.matchDistributionStrength = 100;
  const refined = applyPhotoAdjustments(target, 2, 2, edits).data;
  assert.notDeepEqual(refined, unchanged);
  for (let i = 0; i < target.length; i += 4) {
    assert.equal(refined[i + 3], target[i + 3]);
    for (let channel = 0; channel < 3; channel++)
      assert.ok(Math.abs(refined[i + channel] - unchanged[i + channel]) <= 31);
  }
});
