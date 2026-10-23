import assert from "node:assert/strict";
import test from "node:test";
import {
  interpolateEnhancement,
  blendEnhancement,
  blendEnhancementInto,
  assessEnhancement,
  validateEnhancementLut,
} from "../web/src/enhancement-lut.js";
import {
  applyPhotoAdjustments,
  createDefaultEditSettings,
} from "../web/src/image-processing.js";
import { createMaskComponent } from "../web/src/masking.js";

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
test("allocation-free LUT interpolation matches the reference implementation", () => {
  const lut = Float32Array.from({ length: 3 * 33 ** 3 }, (_, i) =>
    Math.sin(i * 0.01),
  );
  const output = new Float64Array(3);
  for (let i = 0; i < 100; i++) {
    const rgb = [i / 99, (i % 17) / 16, (i % 23) / 22];
    for (const strength of [0, 35, 100]) {
      blendEnhancementInto(...rgb, lut, strength, output);
      assert.deepEqual([...output], blendEnhancement(rgb, lut, strength));
    }
  }
});
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
test("model IDs select the correct learned LUT for independent edit scopes", () => {
  const pixels = new Uint8ClampedArray([128, 128, 128, 255]),
    warm = createDefaultEditSettings(),
    cool = createDefaultEditSettings(),
    transforms = {
      warm: new Float32Array(3 * 33 ** 3).fill(0.8),
      cool: new Float32Array(3 * 33 ** 3).fill(0.2),
    };
  Object.assign(warm, { enhancementId: "warm", enhanceStrength: 100 });
  Object.assign(cool, { enhancementId: "cool", enhanceStrength: 100 });
  assert.ok(
    applyPhotoAdjustments(pixels, 1, 1, warm, transforms).data[0] > 128,
  );
  assert.ok(
    applyPhotoAdjustments(pixels, 1, 1, cool, transforms).data[0] < 128,
  );
});
test("learned LUT composes with the complete pixel tool stack and local masks", () => {
  const width = 16,
    height = 16,
    pixels = Uint8ClampedArray.from(
      { length: width * height * 4 },
      (_, index) => (index % 4 === 3 ? 137 : (index * 29 + 40) % 256),
    ),
    edits = createDefaultEditSettings(),
    local = createDefaultEditSettings();
  Object.assign(edits, {
    enhanceStrength: 40,
    exposure: 0.25,
    contrast: 12,
    highlights: -8,
    shadows: 9,
    whites: 4,
    blacks: -3,
    temperature: 7,
    tint: -5,
    saturation: 8,
    vibrance: 11,
    sharpen: 10,
    vignette: 6,
    grain: 5,
    grainSize: 2,
    match: {
      source: [0.4, 0.45, 0.5],
      reference: [0.45, 0.4, 0.55],
      gain: [1.05, 0.95, 1.08],
    },
    matchColor: 20,
    matchTone: 15,
    colorMix: { red: { hue: 8, saturation: 6, lightness: 3 } },
    curves: {
      master: [
        { x: 0, y: 0.02 },
        { x: 0.5, y: 0.53 },
        { x: 1, y: 0.98 },
      ],
    },
  });
  edits.grades.midtones = { hue: 210, saturation: 12, amount: 10 };
  local.enhanceStrength = 20;
  local.exposure = 0.1;
  local.colorMix = { blue: { hue: -4, saturation: 5, lightness: 2 } };
  edits.masks = [
    {
      enabled: true,
      invert: false,
      opacity: 0.8,
      components: [createMaskComponent()],
      refinement: "none",
      adjustments: local,
    },
  ];
  const result = applyPhotoAdjustments(
    pixels,
    width,
    height,
    edits,
    identityLut(),
  ).data;
  assert.notDeepEqual(result, pixels);
  for (let index = 3; index < result.length; index += 4)
    assert.equal(result[index], 137);
});
