import test from "node:test";
import assert from "node:assert/strict";
import { grainAt } from "../web/src/film-grain.js";
import {
  applyPhotoAdjustments,
  createDefaultEditSettings,
} from "../web/src/image-processing.js";
import { createMaskComponent } from "../web/src/masking.js";
const width = 64,
  height = 48;
const flat = new Uint8ClampedArray(width * height * 4);
for (let i = 0; i < flat.length; i += 4) flat.set([128, 128, 128, 123], i);
test("zero grain is exactly neutral; grain is repeatable and preserves alpha and monochrome", () => {
  const settings = createDefaultEditSettings();
  assert.deepEqual(
    applyPhotoAdjustments(flat, width, height, settings).data,
    flat,
  );
  settings.grain = 70;
  const a = applyPhotoAdjustments(flat, width, height, settings).data;
  assert.notDeepEqual(a, flat);
  assert.deepEqual(
    a,
    applyPhotoAdjustments(flat, width, height, settings).data,
  );
  for (let i = 0; i < a.length; i += 4) {
    assert.equal(a[i], a[i + 1]);
    assert.equal(a[i + 1], a[i + 2]);
    assert.equal(a[i + 3], 123);
  }
  settings.grainSize = 5;
  assert.notDeepEqual(
    a,
    applyPhotoAdjustments(flat, width, height, settings).data,
  );
});
test("grain texture uses normalized source coordinates across resolutions", () => {
  for (const size of [1, 2, 8])
    assert.ok(
      Math.abs(
        grainAt(49.5, 24.5, 100, 50, size) -
          grainAt(499.5, 249.5, 1000, 500, size),
      ) < 1e-10,
    );
});
test("grain inside a mask never changes excluded pixels", () => {
  const settings = createDefaultEditSettings();
  settings.masks = [
    {
      enabled: true,
      opacity: 1,
      components: [createMaskComponent()],
      adjustments: { ...createDefaultEditSettings(), grain: 100 },
    },
  ];
  const output = applyPhotoAdjustments(flat, width, height, settings).data;
  assert.deepEqual(output.slice(0, 4), flat.slice(0, 4));
  assert.notDeepEqual(output, flat);
});
