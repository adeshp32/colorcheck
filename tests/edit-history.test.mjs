import assert from "node:assert/strict";
import test from "node:test";
import { createEditHistory } from "../web/src/edit-history.js";

test("undo and redo restore isolated settings snapshots", () => {
  const history = createEditHistory({ exposure: 0, crop: { x: 0 } });
  const edits = { exposure: 1, crop: { x: 10 } };
  history.commit(edits);
  edits.crop.x = 99;
  assert.deepEqual(history.undo(), { exposure: 0, crop: { x: 0 } });
  assert.deepEqual(history.redo(), { exposure: 1, crop: { x: 10 } });
});
test("new edits invalidate redo and unchanged edits do not add history", () => {
  const history = createEditHistory({ value: 0 });
  assert.equal(history.commit({ value: 0 }), false);
  assert.equal(history.canUndo, false);
  history.commit({ value: 1 });
  history.undo();
  history.commit({ value: 2 });
  assert.equal(history.canRedo, false);
});
test("history is bounded and selecting a new photo clears it", () => {
  const history = createEditHistory({ value: 0 }, 2);
  for (let value = 1; value <= 3; value++) history.commit({ value });
  assert.equal(history.undo().value, 2);
  assert.equal(history.undo().value, 1);
  assert.equal(history.undo(), null);
  history.reset({ value: 5 });
  assert.equal(history.canUndo, false);
  assert.equal(history.canRedo, false);
});
