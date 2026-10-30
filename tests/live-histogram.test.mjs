import test from "node:test";
import assert from "node:assert/strict";
import { histogramFromRgba } from "../web/src/live-histogram.js";

test("display histogram follows edited RGB values and skips transparent pixels", () => {
  const original = histogramFromRgba(
    new Uint8ClampedArray([16, 32, 48, 255, 255, 255, 255, 0]),
  );
  const edited = histogramFromRgba(
    new Uint8ClampedArray([240, 32, 48, 255, 255, 255, 255, 0]),
  );
  assert.equal(original.red[4], 1);
  assert.equal(edited.red[60], 1);
  assert.equal(edited.red[63], 0);
  assert.equal(
    original.luminance.reduce((sum, count) => sum + count),
    1,
  );
  assert.notDeepEqual(original.luminance, edited.luminance);
});
