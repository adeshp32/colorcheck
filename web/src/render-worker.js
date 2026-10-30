import {
  applyPhotoAdjustments,
  calculatePerceptualReferenceMatch,
} from "./image-processing.js";
import { applyLensBlur } from "./lens-blur.js";
// Transfer ownership of large buffers rather than structured-cloning image data.
self.onmessage = ({ data: m }) => {
  try {
    if (m.type === "reference-match") {
      const match = calculatePerceptualReferenceMatch(
        new Uint8ClampedArray(m.pixels),
        new Uint8ClampedArray(m.reference),
      );
      self.postMessage({ id: m.id, match });
      return;
    }
    const result = applyPhotoAdjustments(
      new Uint8ClampedArray(m.pixels),
      m.width,
      m.height,
      m.edits,
      m.enhancementLut,
      false,
    );
    result.data = applyLensBlur(
      result.data,
      m.width,
      m.height,
      m.edits,
      m.depthMap,
      m.blurPixelLimit,
    );
    self.postMessage({ id: m.id, ...result }, [
      result.data.buffer,
      result.histogram.buffer,
    ]);
  } catch (error) {
    self.postMessage({ id: m.id, error: error.message });
  }
};
