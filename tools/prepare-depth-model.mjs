/** Pin, verify and split the ONNX artifact below the static host's per-file limit. */
import { mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
const root = new URL(
  "../web/assets/models/depth-anything-v2-small/",
  import.meta.url,
);
const revision = "64fe43eba7f8a384b02fe3fadaa26cbba35548d8";
const expected =
  "fcf51f1b230362b28690bb9d1809bf0431f29cad20534e3f589bd7285547f20d";
const digest = (data) => createHash("sha256").update(data).digest("hex");
const base = `https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/${revision}/`;
await mkdir(root, { recursive: true });
const response = await fetch(base + "onnx/model_quantized.onnx");
if (!response.ok) throw new Error(`Model download failed: ${response.status}`);
const bytes = Buffer.from(await response.arrayBuffer());
if (bytes.length !== 27258801 || digest(bytes) !== expected)
  throw new Error("Pinned depth model integrity mismatch");
const chunks = [];
for (let start = 0; start < bytes.length; start += 14_000_000) {
  const data = bytes.subarray(start, start + 14_000_000);
  const file = `model.part${chunks.length + 1}.bin`;
  await writeFile(new URL(file, root), data);
  chunks.push({ file, bytes: data.length, sha256: digest(data) });
}
const license = await fetch("https://www.apache.org/licenses/LICENSE-2.0.txt");
if (!license.ok) throw new Error("Depth model license download failed");
await writeFile(new URL("LICENSE.txt", root), await license.text());
await writeFile(
  new URL("manifest.json", root),
  JSON.stringify(
    {
      id: "depth-anything-v2-small-uint8",
      revision,
      bytes: bytes.length,
      sha256: expected,
      upstream: "https://github.com/DepthAnything/Depth-Anything-V2",
      export: "https://huggingface.co/onnx-community/depth-anything-v2-small",
      license: "Apache-2.0",
      input: "pixel_values",
      output: "predicted_depth",
      chunks,
    },
    null,
    2,
  ) + "\n",
);
console.log(
  `Prepared verified depth model: ${bytes.length} bytes, ${chunks.length} same-origin chunks.`,
);
