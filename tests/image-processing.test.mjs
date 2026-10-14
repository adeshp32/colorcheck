import assert from "node:assert/strict";
import {
  createDefaultEditSettings,
  calculateChannelStatistics,
  calculateReferenceMatch,
  applyPhotoAdjustments,
  applyToneCurve,
} from "../web/src/image-processing.js";

const pixels = new Uint8ClampedArray([
  32, 64, 128, 255, 180, 120, 40, 255, 240, 230, 220, 255, 90, 100, 110, 0,
]);
assert.deepEqual(
  applyPhotoAdjustments(pixels, 2, 2, createDefaultEditSettings()).data,
  pixels,
  "Neutral edits must preserve pixels and alpha",
);
const source = calculateChannelStatistics(pixels),
  same = calculateReferenceMatch(source, source),
  matched = createDefaultEditSettings();
matched.match = same;
matched.matchColor = 100;
matched.matchTone = 100;
assert.deepEqual(
  applyPhotoAdjustments(pixels, 2, 2, matched).data,
  pixels,
  "Matching an image to itself must not change it",
);
assert.throws(
  () => calculateChannelStatistics(new Uint8ClampedArray([0, 0, 0, 0])),
  /opaque/,
);
const bright = createDefaultEditSettings();
bright.exposure = 1;
assert.equal(applyPhotoAdjustments(pixels, 2, 2, bright).data[0], 64);
const monochrome = createDefaultEditSettings();
monochrome.bw = true;
const bw = applyPhotoAdjustments(pixels, 2, 2, monochrome).data;
assert.equal(bw[0], bw[1]);
assert.equal(bw[1], bw[2]);
assert.equal(bw[7], 255);
const gain = calculateReferenceMatch(
  { mean: [0.2, 0.2, 0.2], std: [0, 0.01, 1] },
  { mean: [0.6, 0.6, 0.6], std: [1, 1, 0] },
);
assert.ok(gain.gain.every((v) => v >= 0.65 && v <= 1.5));
for (const name of ["linear", "soft", "strong", "matte"]) {
  let last = -1;
  for (let i = 0; i <= 1000; i++) {
    const v = applyToneCurve(i / 1000, name);
    assert.ok(v >= 0 && v <= 1);
    assert.ok(v >= last, "Tone curves must remain monotonic");
    last = v;
  }
}
assert.ok(applyToneCurve(0.25, "strong") < 0.25);
assert.ok(applyToneCurve(0.75, "strong") > 0.75);
const extremes = createDefaultEditSettings();
for (const key of [
  "contrast",
  "highlights",
  "shadows",
  "temperature",
  "tint",
  "vibrance",
  "sharpen",
  "vignette",
])
  extremes[key] = 100;
const result = applyPhotoAdjustments(pixels, 2, 2, extremes);
assert.equal(result.data.length, pixels.length);
assert.equal(
  result.histogram.reduce((a, b) => a + b, 0),
  4,
);
console.log(
  "Photo engine: neutral output, matching, exposure, alpha, B&W, bounds, and curves passed.",
);
