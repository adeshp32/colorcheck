import { applyPhotoAdjustments } from "./image-processing.js";
// Transfer ownership of large buffers rather than structured-cloning image data.
self.onmessage = ({ data: m }) => {
  try {
    const result = applyPhotoAdjustments(
      new Uint8ClampedArray(m.pixels),
      m.width,
      m.height,
      m.edits,
      m.enhancementLut,
      false,
    );
    self.postMessage({ id: m.id, ...result }, [
      result.data.buffer,
      result.histogram.buffer,
    ]);
  } catch (error) {
    self.postMessage({ id: m.id, error: error.message });
  }
};
