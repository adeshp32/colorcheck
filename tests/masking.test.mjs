import test from "node:test";
import assert from "node:assert/strict";
import {
  createMaskComponent,
  maskCoverage,
  sourcePoint,
} from "../web/src/masking.js";
import {
  createDefaultEditSettings,
  applyPhotoAdjustments,
} from "../web/src/image-processing.js";

const makeMask = () => ({
  enabled: true,
  invert: false,
  opacity: 1,
  components: [createMaskComponent()],
  refinement: "none",
  adjustments: createDefaultEditSettings(),
});
test("radial feather, outside selection, and opacity have bounded coverage", () => {
  const mask = makeMask();
  assert.equal(maskCoverage(mask, 0.5, 0.5, [128, 128, 128]), 1);
  assert.equal(maskCoverage(mask, 0.01, 0.01, [128, 128, 128]), 0);
  const edge = maskCoverage(mask, 0.725, 0.5, [128, 128, 128]);
  assert.ok(edge > 0 && edge < 1);
  mask.invert = true;
  assert.equal(maskCoverage(mask, 0.5, 0.5, [128, 128, 128]), 0);
  mask.opacity = 0.5;
  assert.equal(maskCoverage(mask, 0.01, 0.01, [128, 128, 128]), 0.5);
});
test("shapes support add, subtract, intersection, and linear gradients", () => {
  const mask = makeMask();
  mask.components.push({
    ...createMaskComponent(),
    rx: 0.1,
    ry: 0.1,
    operation: "subtract",
  });
  assert.equal(maskCoverage(mask, 0.5, 0.5, [0, 0, 0]), 0);
  assert.equal(maskCoverage(mask, 0.65, 0.5, [0, 0, 0]), 1);
  mask.components[1].operation = "intersect";
  assert.equal(maskCoverage(mask, 0.65, 0.5, [0, 0, 0]), 0);
  const shape = createMaskComponent("linear");
  mask.components = [shape];
  assert.equal(maskCoverage(mask, shape.x, shape.y, [0, 0, 0]), 1);
  assert.equal(maskCoverage(mask, shape.x2, shape.y2, [0, 0, 0]), 0);
});
test("range refinements intersect the geometric mask", () => {
  const mask = {
    ...makeMask(),
    refinement: "luminance",
    lumaMin: 0.4,
    lumaMax: 0.6,
    rangeSoftness: 0.05,
  };
  assert.equal(maskCoverage(mask, 0.5, 0.5, [0, 0, 0]), 0);
  assert.equal(maskCoverage(mask, 0.5, 0.5, [128, 128, 128]), 1);
  Object.assign(mask, {
    refinement: "color",
    color: [255, 0, 0],
    colorTolerance: 0.1,
  });
  assert.equal(maskCoverage(mask, 0.5, 0.5, [255, 0, 0]), 1);
  assert.equal(maskCoverage(mask, 0.5, 0.5, [0, 255, 0]), 0);
});
test("masked corrections preserve outside pixels and original alpha", () => {
  const edits = createDefaultEditSettings(),
    mask = makeMask();
  mask.adjustments.exposure = 1;
  edits.masks = [mask];
  const pixels = new Uint8ClampedArray(100 * 100 * 4);
  for (let i = 0; i < pixels.length; i += 4) pixels.set([80, 80, 80, 111], i);
  const result = applyPhotoAdjustments(pixels, 100, 100, edits).data;
  assert.deepEqual([...result.slice(0, 4)], [80, 80, 80, 111]);
  assert.deepEqual(
    [...result.slice((50 * 100 + 50) * 4, (50 * 100 + 50) * 4 + 4)],
    [160, 160, 160, 111],
  );
  mask.enabled = false;
  assert.deepEqual(applyPhotoAdjustments(pixels, 100, 100, edits).data, pixels);
});
test("mask boundaries stay normalized across preview and export resolutions", () => {
  const mask = makeMask();
  for (const size of [100, 1000, 4000])
    assert.equal(
      maskCoverage(mask, (0.5 * size) / size, (0.5 * size) / size, [0, 0, 0]),
      1,
    );
  const settings = createDefaultEditSettings();
  settings.rotation = 90;
  const p = sourcePoint(0.25, 0.75, 800, 600, settings);
  assert.ok(Math.abs(p.x - 0.75) < 1e-9 && Math.abs(p.y - 0.75) < 1e-9);
  settings.flip = true;
  assert.ok(
    Math.abs(sourcePoint(0.25, 0.75, 800, 600, settings).x - 0.25) < 1e-9,
  );
});
