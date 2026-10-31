import test from "node:test";
import assert from "node:assert/strict";
import {
  sampleCurve,
  buildCurveTable,
  lookupCurve,
} from "../web/src/tone-curves.js";
import { prepareColorMix, mixColorInto } from "../web/src/color-mixer.js";
import {
  applyPhotoAdjustments,
  createDefaultEditSettings,
} from "../web/src/image-processing.js";
import { createMaskComponent } from "../web/src/masking.js";

test("editable curves preserve identity, remain bounded and do not overshoot monotonic points", () => {
  const identity = [
    { x: 0, y: 0 },
    { x: 1, y: 1 },
  ];
  const points = [
    { x: 0, y: 0.03 },
    { x: 0.25, y: 0.1 },
    { x: 0.65, y: 0.8 },
    { x: 1, y: 0.96 },
  ];
  const table = buildCurveTable(identity);
  let previous = 0;
  for (let i = 0; i <= 1000; i++) {
    const x = i / 1000,
      value = sampleCurve(points, x);
    assert.ok(Math.abs(lookupCurve(table, x) - x) < 1e-6);
    assert.ok(value >= previous && value >= 0.03 && value <= 0.96 + 1e-10);
    previous = value;
  }
  for (const point of points)
    assert.ok(Math.abs(sampleCurve(points, point.x) - point.y) < 1e-10);
});
test("red-channel curves do not alter green, blue or alpha", () => {
  const edits = createDefaultEditSettings();
  edits.curves = {
    red: [
      { x: 0, y: 0 },
      { x: 1, y: 0.5 },
    ],
  };
  const result = applyPhotoAdjustments(
    new Uint8ClampedArray([160, 100, 80, 91]),
    1,
    1,
    edits,
  ).data;
  assert.deepEqual([...result], [80, 100, 80, 91]);
});
test("individual color adjustments protect grays and untouched hue ranges", () => {
  const bands = prepareColorMix({
      red: { hue: 40, saturation: -50, lightness: 20 },
    }),
    out = new Float64Array(3);
  mixColorInto(0.5, 0.5, 0.5, bands, out);
  assert.deepEqual([...out], [0.5, 0.5, 0.5]);
  mixColorInto(0, 0, 1, bands, out);
  assert.deepEqual([...out], [0, 0, 1]);
  mixColorInto(1, 0, 0, bands, out);
  assert.ok(out[1] > 0 && out[0] > out[2]);
  assert.equal(
    prepareColorMix({ red: { hue: 0, saturation: 0, lightness: 0 } }),
    null,
  );
});
test("color interpolation is continuous across red wraparound and bounded", () => {
  const bands = prepareColorMix({
      red: { hue: 60, saturation: 100, lightness: 50 },
    }),
    a = new Float64Array(3),
    b = new Float64Array(3);
  mixColorInto(1, 0, 0.00001, bands, a);
  mixColorInto(1, 0.00001, 0, bands, b);
  for (let i = 0; i < 3; i++)
    assert.ok(Math.abs(a[i] - b[i]) < 0.0001 && a[i] >= 0 && a[i] <= 1);
});
test("curves-only and color-only masks affect selected pixels, never the outside", () => {
  const size = 20,
    pixels = new Uint8ClampedArray(size * size * 4);
  for (let i = 0; i < pixels.length; i += 4) pixels.set([180, 40, 40, 123], i);
  for (const settings of [
    {
      curves: {
        red: [
          { x: 0, y: 0 },
          { x: 1, y: 0.5 },
        ],
      },
    },
    { colorMix: { red: { hue: 40, saturation: 0, lightness: 0 } } },
  ]) {
    const edits = createDefaultEditSettings();
    edits.masks = [
      {
        enabled: true,
        opacity: 1,
        components: [createMaskComponent()],
        adjustments: { ...createDefaultEditSettings(), ...settings },
      },
    ];
    const result = applyPhotoAdjustments(pixels, size, size, edits).data;
    assert.deepEqual(result.slice(0, 4), pixels.slice(0, 4));
    const i = (10 * size + 10) * 4;
    assert.notDeepEqual(result.slice(i, i + 3), pixels.slice(i, i + 3));
    assert.equal(result[i + 3], 123);
  }
});
