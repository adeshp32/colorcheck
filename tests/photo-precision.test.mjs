import test from "node:test";
import assert from "node:assert/strict";
import { precisionFromHeader } from "../web/src/photo-precision.js";
test("precision reads explicit PNG/JPEG headers without guessing RAW or HEIC precision", () => {
  const png = new Uint8Array(29);
  png.set([137, 80, 78, 71, 13, 10, 26, 10]);
  png.set([73, 72, 68, 82], 12);
  png[24] = 16;
  png[25] = 2;
  assert.equal(precisionFromHeader(png).bits, 16);
  png[24] = 8;
  png[25] = 3;
  assert.equal(precisionFromHeader(png).kind, "palette-index");
  assert.equal(
    precisionFromHeader(
      new Uint8Array([255, 216, 255, 192, 0, 8, 12, 0, 1, 0, 1, 0]),
    ).bits,
    12,
  );
  assert.equal(precisionFromHeader(new Uint8Array([73, 73, 42, 0])).bits, null);
  assert.equal(precisionFromHeader(new Uint8Array(4)).bits, null);
});
