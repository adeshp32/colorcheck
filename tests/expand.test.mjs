import test from "node:test";
import assert from "node:assert/strict";
import { expandedGeometry, assertOutputSize } from "../web/src/expand.js";

test("expand is neutral by default and derives independent borders from cropped geometry", () => {
  assert.equal(expandedGeometry(800, 600, null).width, 800);
  assert.deepEqual(expandedGeometry(800, 600), {
    left: 0,
    right: 0,
    top: 0,
    bottom: 0,
    width: 800,
    height: 600,
  });
  assert.deepEqual(
    expandedGeometry(400, 600, { left: 10, right: 20, top: 5, bottom: 10 }),
    { left: 40, right: 80, top: 30, bottom: 60, width: 520, height: 690 },
  );
});
test("expand bounds invalid settings and rejects unsafe allocations", () => {
  assert.equal(
    expandedGeometry(100, 100, { left: Infinity, right: -5, top: NaN }).width,
    100,
  );
  assert.equal(expandedGeometry(100, 100, { left: 500 }).width, 200);
  assert.throws(() => assertOutputSize(10000, 10000), /safe canvas/);
  assert.throws(() => assertOutputSize(0, 100), /safe canvas/);
  assert.doesNotThrow(() => assertOutputSize(2400, 3600));
});
