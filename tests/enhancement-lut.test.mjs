import assert from "node:assert/strict";
import test from "node:test";
import {
  interpolateEnhancement,
  blendEnhancement,
  assessEnhancement,
  validateEnhancementLut,
} from "../web/src/enhancement-lut.js";
import {
  applyPhotoAdjustments,
  createDefaultEditSettings,
} from "../web/src/image-processing.js";

function identityLut() {
  const lut = new Float32Array(3 * 33 ** 3);
  for (let b = 0; b < 33; b++)
    for (let g = 0; g < 33; g++)
      for (let r = 0; r < 33; r++) {
        const i = b * 33 * 33 + g * 33 + r;
        lut[i] = r / 32;
        lut[33 ** 3 + i] = g / 32;
        lut[2 * 33 ** 3 + i] = b / 32;
      }
  return lut;
}
test("LUT axes are correct and zero strength is exactly neutral", () => {
  const lut = identityLut(),
    rgb = [0.2, 0.5, 0.8],
    out = interpolateEnhancement(lut, rgb);
  out.forEach((v, i) => assert.ok(Math.abs(v - rgb[i]) < 0.0001));
  assert.deepEqual(blendEnhancement(rgb, lut, 0), rgb);
});
test("per-channel correction is bounded even for aggressive model outputs", () => {
  const lut = new Float32Array(3 * 33 ** 3).fill(3),
    out = blendEnhancement([0.4, 0.4, 0.4], lut, 100);
  out.forEach((v) => assert.ok(Math.abs(v - 0.4) <= 0.250001));
});
test("invalid, nonfinite transforms are rejected", () => {
  assert.throws(() => validateEnhancementLut(new Float32Array(3)), /invalid/);
  const lut = identityLut();
  lut[20] = NaN;
  assert.throws(() => validateEnhancementLut(lut), /invalid/);
});
test("clipping guardrail reduces an unsafe suggested strength to zero", () => {
  const assessment = assessEnhancement(
    new Uint8ClampedArray([254, 254, 254, 255]),
    new Float32Array(3 * 33 ** 3).fill(2),
  );
  assert.equal(assessment.recommendedStrength, 0);
  assert.equal(assessment.clippingAfter, 0);
});
test("same transform is used by preview/export engine and alpha survives", () => {
  const edits = createDefaultEditSettings(),
    pixels = new Uint8ClampedArray([128, 128, 128, 100]);
  assert.deepEqual(
    applyPhotoAdjustments(pixels, 1, 1, edits, identityLut()).data,
    pixels,
  );
  edits.enhanceStrength = 100;
  const result = applyPhotoAdjustments(
    pixels,
    1,
    1,
    edits,
    new Float32Array(3 * 33 ** 3).fill(0.8),
  );
  assert.ok(result.data[0] > pixels[0]);
  assert.equal(result.data[3], 100);
});
