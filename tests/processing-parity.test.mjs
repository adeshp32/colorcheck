import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  applyPhotoAdjustments,
  createDefaultEditSettings,
} from "../web/src/image-processing.js";

// Captured from the pre-optimization renderer, including alpha and histogram bins.
const fixtures = {
  neutral: "26bb90c8efe0998e10ccb5ec8774a100001ec4e586b59852f8f1d588b0751c3a",
  tone: "c7a5a32d29abe68eae5ff83dcb41b04b7d606ec07acc0fe9cbc16b7c5dda5ffd",
  grade: "c4f72a071d53c479e77345f09dd6a13f6aa8f7638820fa9f51708eb8f1594e20",
  match: "8505744bb192c639566ad8a9ee8742832aff213493d1555c3c0591c18833dd2c",
  detail: "75f0d1efec6ba00f85c5c817f92dd1617bc2b1d65c9f64623ce7b74453dfb334",
};
for (const [mode, expected] of Object.entries(fixtures))
  test(`optimized processing preserves ${mode} pixels and histogram`, () => {
    const data = Uint8ClampedArray.from(
      { length: 64 * 48 * 4 },
      (_, i) => (i * 37 + (i % 11)) % 256,
    );
    const edits = createDefaultEditSettings();
    if (mode === "tone")
      Object.assign(edits, {
        exposure: 0.7,
        contrast: 22,
        highlights: -15,
        shadows: 21,
        whites: 8,
        blacks: -5,
        temperature: 17,
        tint: -12,
        saturation: 22,
        vibrance: 30,
        vignette: 14,
        curve: "soft",
      });
    if (mode === "grade")
      for (const grade of Object.values(edits.grades))
        Object.assign(grade, { hue: 217, saturation: 70, amount: 29 });
    if (mode === "match")
      Object.assign(edits, {
        match: {
          source: [0.3, 0.4, 0.5],
          reference: [0.4, 0.3, 0.6],
          gain: [1.2, 0.8, 1.1],
        },
        matchColor: 65,
        matchTone: 40,
      });
    if (mode === "detail")
      Object.assign(edits, { sharpen: 40, bw: true, exposure: -0.2 });
    const result = applyPhotoAdjustments(data, 64, 48, edits);
    assert.equal(
      createHash("sha256")
        .update(result.data)
        .update(result.histogram)
        .digest("hex"),
      expected,
    );
  });
