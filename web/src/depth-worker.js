import * as ort from "../vendor/onnxruntime/ort.wasm.min.mjs";
import { normalizeDepth } from "./depth-map.js";
const root = new URL(
  "../assets/models/depth-anything-v2-small/",
  import.meta.url,
);
ort.env.wasm.numThreads = 1;
ort.env.wasm.proxy = false;
ort.env.wasm.wasmPaths = new URL(
  "../vendor/onnxruntime/",
  import.meta.url,
).href;
let loaded;
const hash = async (bytes) =>
  Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (v) => v.toString(16).padStart(2, "0"),
  ).join("");
async function load() {
  self.postMessage({ stage: "Loading depth model (27.3 MB), on this device…" });
  const response = await fetch(new URL("manifest.json", root));
  if (!response.ok)
    throw new Error(
      "Depth model is unavailable. Radial and linear blur still work.",
    );
  const manifest = await response.json();
  let cache;
  try {
    cache = await caches.open("colorcheck-depth-v1");
  } catch {}
  const bytes = new Uint8Array(manifest.bytes);
  let offset = 0;
  for (const chunk of manifest.chunks) {
    const url = new URL(chunk.file, root);
    const result = (await cache?.match(url.href)) || (await fetch(url));
    if (!result.ok) throw new Error("Depth model download failed.");
    const buffer = await result.arrayBuffer();
    if (
      buffer.byteLength !== chunk.bytes ||
      (await hash(buffer)) !== chunk.sha256
    ) {
      await cache?.delete(url.href);
      throw new Error("Depth model integrity check failed.");
    }
    bytes.set(new Uint8Array(buffer), offset);
    offset += buffer.byteLength;
    try {
      await cache?.put(url.href, new Response(buffer));
    } catch {}
  }
  if (offset !== manifest.bytes || (await hash(bytes)) !== manifest.sha256)
    throw new Error("Depth model integrity check failed.");
  const session = await ort.InferenceSession.create(bytes, {
    executionProviders: ["wasm"],
    graphOptimizationLevel: "disabled",
  });
  return { session, manifest };
}
self.onmessage = async ({ data: m }) => {
  try {
    const pixels = new Uint8ClampedArray(m.pixels),
      n = m.width * m.height;
    if (
      pixels.length !== n * 4 ||
      n > 518 * 518 ||
      m.width % 14 ||
      m.height % 14
    )
      throw new Error("Invalid depth analysis input.");
    loaded ??= load().catch((error) => {
      loaded = null;
      throw error;
    });
    const { session, manifest } = await loaded;
    self.postMessage({ stage: "Estimating relative scene depth locally…" });
    const input = new Float32Array(n * 3),
      mean = [0.485, 0.456, 0.406],
      std = [0.229, 0.224, 0.225];
    for (let i = 0; i < n; i++)
      for (let c = 0; c < 3; c++)
        input[c * n + i] = (pixels[i * 4 + c] / 255 - mean[c]) / std[c];
    const start = performance.now();
    const result = await session.run({
      [manifest.input]: new ort.Tensor("float32", input, [
        1,
        3,
        m.height,
        m.width,
      ]),
    });
    const tensor = result[manifest.output];
    if (!tensor || tensor.dims.length !== 3)
      throw new Error("Unexpected depth model output.");
    const [batch, height, width] = tensor.dims;
    if (batch !== 1) throw new Error("Unexpected depth model batch.");
    const values = normalizeDepth(tensor.data, width, height);
    self.postMessage(
      {
        values,
        width,
        height,
        inferenceMs: performance.now() - start,
        modelHash: manifest.sha256,
      },
      [values.buffer],
    );
    for (const output of Object.values(result)) output.dispose?.();
  } catch (error) {
    self.postMessage({ error: error.message });
  }
};
