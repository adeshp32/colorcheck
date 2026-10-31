import test from "node:test";
import assert from "node:assert/strict";
import { fitPreviewDimensions } from "../web/src/workspace-layout.js";

test("portrait and landscape previews fit both available dimensions", () => {
  assert.deepEqual(fitPreviewDimensions(1000, 4000, 800, 600), {
    width: 150,
    height: 600,
  });
  assert.deepEqual(fitPreviewDimensions(4000, 1000, 800, 600), {
    width: 800,
    height: 200,
  });
});
test("fit preserves small previews and tolerates temporarily hidden viewers", () => {
  assert.deepEqual(fitPreviewDimensions(100, 200, 800, 600), {
    width: 100,
    height: 200,
  });
  assert.deepEqual(fitPreviewDimensions(100, 200, 0, 600), {
    width: 0,
    height: 0,
  });
  assert.deepEqual(fitPreviewDimensions(NaN, 200, 800, 600), {
    width: 0,
    height: 0,
  });
});
