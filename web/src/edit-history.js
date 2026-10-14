/** Stores bounded settings snapshots, never full-resolution image buffers. */
export function createEditHistory(initialSettings, limit = 60) {
  let current = structuredClone(initialSettings);
  let previous = [];
  let next = [];
  return {
    get canUndo() {
      return previous.length > 0;
    },
    get canRedo() {
      return next.length > 0;
    },
    commit(settings) {
      if (JSON.stringify(settings) === JSON.stringify(current)) return false;
      previous.push(current);
      if (previous.length > limit) previous.shift();
      current = structuredClone(settings);
      next = [];
      return true;
    },
    undo() {
      if (!previous.length) return null;
      next.push(current);
      current = previous.pop();
      return structuredClone(current);
    },
    redo() {
      if (!next.length) return null;
      previous.push(current);
      current = next.pop();
      return structuredClone(current);
    },
    reset(settings) {
      current = structuredClone(settings);
      previous = [];
      next = [];
    },
  };
}
