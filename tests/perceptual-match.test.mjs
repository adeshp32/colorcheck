import test from "node:test";
import assert from "node:assert/strict";
import {
  rgbToOklab,
  oklabToGamutRgb,
  buildPerceptualMatch,
} from "../web/src/perceptual-match.js";
import {
  applyPhotoAdjustments,
  calculatePerceptualReferenceMatch,
  createDefaultEditSettings,
} from "../web/src/image-processing.js";

const fixture = (count = 512) =>
  Uint8ClampedArray.from({ length: count * 4 }, (_, i) =>
    i % 4 === 3 ? 255 : (i * 37 + (i % 19)) % 256,
  );
function render(source, reference, palette = 100, tone = 0, detail = 0) {
  const edits = createDefaultEditSettings();
  Object.assign(edits, {
    match: calculatePerceptualReferenceMatch(source, reference),
    matchColor: palette,
    matchTone: tone,
    matchDistributionStrength: detail,
  });
  return {
    edits,
    data: applyPhotoAdjustments(source, source.length / 4, 1, edits).data,
  };
}

test("Oklab conversion round trips sRGB without altering ordinary in-gamut colors", () => {
  const pixels = fixture();
  for (let i = 0; i < pixels.length; i += 4) {
    const rgb = Array.from(pixels.slice(i, i + 3), (v) => v / 255);
    const out = oklabToGamutRgb(...rgbToOklab(...rgb));
    for (let c = 0; c < 3; c++) assert.ok(Math.abs(out[c] - rgb[c]) < 0.00001);
  }
});
test("new matching is exactly neutral at zero strength, and identical references are identity", () => {
  const pixels = fixture();
  assert.deepEqual(render(pixels, fixture(311), 0, 0, 0).data, pixels);
  assert.deepEqual(render(pixels, pixels, 100, 100, 100).data, pixels);
});
test("palette and distribution protect the entire gray ramp from a colored reference", () => {
  const grays = Uint8ClampedArray.from({ length: 1024 }, (_, i) =>
    i % 4 === 3 ? 255 : Math.floor(i / 4),
  );
  const out = render(grays, fixture(), 100, 0, 100).data;
  assert.deepEqual(out, grays);
});
test("palette changes colors without changing Oklab lightness beyond 8-bit rounding", () => {
  const source = fixture(),
    reference = fixture(311);
  for (let i = 0; i < reference.length; i += 4) {
    reference[i] = Math.min(255, reference[i] + 60);
    reference[i + 2] = Math.max(0, reference[i + 2] - 60);
  }
  const out = render(source, reference).data;
  let changed = 0,
    worst = 0;
  for (let i = 0; i < source.length; i += 4) {
    const a = rgbToOklab(...Array.from(source.slice(i, i + 3), (v) => v / 255));
    const b = rgbToOklab(...Array.from(out.slice(i, i + 3), (v) => v / 255));
    worst = Math.max(worst, Math.abs(a[0] - b[0]));
    changed +=
      Math.abs(out[i] - source[i]) +
      Math.abs(out[i + 1] - source[i + 1]) +
      Math.abs(out[i + 2] - source[i + 2]);
  }
  assert.ok(worst < 0.004, `Lightness drift ${worst}`);
  assert.ok(
    changed > source.length,
    "Palette transfer must actually use the reference",
  );
});
test("tone is independent, monotonic on neutrals and does not introduce a colored cast", () => {
  const source = Uint8ClampedArray.from({ length: 1024 }, (_, i) =>
    i % 4 === 3 ? 255 : Math.floor(i / 4),
  );
  const reference = Uint8ClampedArray.from(source, (v, i) =>
    i % 4 === 3 ? v : Math.round(Math.sqrt(v / 255) * 255),
  );
  const out = render(source, reference, 0, 100).data;
  let previous = -1;
  for (let i = 0; i < out.length; i += 4) {
    assert.equal(out[i], out[i + 1]);
    assert.equal(out[i + 1], out[i + 2]);
    assert.ok(out[i] >= previous);
    previous = out[i];
  }
  assert.notDeepEqual(out, source);
});
test("gamut compression preserves lightness and hue instead of clipping channels", () => {
  const target = [0.7, 0.6, 0.4],
    rgb = oklabToGamutRgb(...target),
    lab = rgbToOklab(...rgb);
  assert.ok(rgb.every((v) => Number.isFinite(v) && v >= 0 && v <= 1));
  assert.ok(Math.abs(lab[0] - target[0]) < 1e-5);
  assert.ok(
    Math.abs(Math.atan2(lab[2], lab[1]) - Math.atan2(target[2], target[1])) <
      1e-5,
  );
  assert.ok(Math.hypot(lab[1], lab[2]) < Math.hypot(target[1], target[2]));
});
test("sparse and flat colors yield finite bounded covariance transforms; alpha is preserved", () => {
  const source = new Uint8ClampedArray([80, 40, 20, 255, 200, 40, 180, 0]);
  const reference = new Uint8ClampedArray([20, 40, 220, 255, 0, 0, 0, 0]);
  const match = buildPerceptualMatch(source, reference);
  for (const band of match.bands) {
    assert.ok(band.matrix.every(Number.isFinite));
    const [a, b, d] = band.matrix,
      radius = Math.hypot(a - d, 2 * b);
    assert.ok(
      (a + d - radius) / 2 >= 0.65 - 1e-9 && (a + d + radius) / 2 <= 1.5 + 1e-9,
    );
  }
  assert.deepEqual(
    match,
    buildPerceptualMatch(source.slice(0, 4), reference.slice(0, 4)),
  );
  const out = render(source, reference, 100, 100, 100).data;
  assert.equal(out[3], 255);
  assert.equal(out[7], 0);
  assert.throws(
    () => buildPerceptualMatch(new Uint8Array(3), reference),
    /RGBA/,
  );
  assert.throws(
    () => buildPerceptualMatch(new Uint8Array(4), reference),
    /opaque/,
  );
});
test("perceptual records survive structured cloning and compose with masks and other edits", () => {
  const source = fixture(),
    reference = fixture(311);
  const { edits } = render(source, reference, 65, 45, 30);
  const cloned = structuredClone(edits);
  cloned.exposure = 0.2;
  cloned.saturation = 10;
  cloned.vignette = -10;
  assert.deepEqual(
    applyPhotoAdjustments(source, 512, 1, cloned),
    applyPhotoAdjustments(source, 512, 1, structuredClone(cloned)),
  );
  const local = createDefaultEditSettings();
  local.masks = [
    {
      id: "match",
      enabled: true,
      opacity: 1,
      components: [
        {
          type: "radial",
          operation: "add",
          x: 0.5,
          y: 0.5,
          rx: 0.2,
          ry: 0.8,
          feather: 0,
          angle: 0,
        },
      ],
      adjustments: cloned,
    },
  ];
  const out = applyPhotoAdjustments(source, 512, 1, local).data;
  assert.deepEqual(out.slice(0, 4), source.slice(0, 4));
  assert.notDeepEqual(out, source);
});
