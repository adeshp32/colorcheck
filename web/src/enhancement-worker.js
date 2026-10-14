import * as ort from "../vendor/onnxruntime/ort.wasm.min.mjs";
import {
  assessEnhancement,
  validateEnhancementLut,
} from "./enhancement-lut.js";
const MODEL_ROOT = new URL("../assets/models/adaptive-lut/", import.meta.url);
let sessionPromise;
ort.env.wasm.numThreads = 1;
ort.env.wasm.proxy = false;
ort.env.wasm.wasmPaths = new URL(
  "../vendor/onnxruntime/",
  import.meta.url,
).href;

async function loadModel() {
  self.postMessage({ stage: "Loading enhancement model…" });
  const response = await fetch(new URL("manifest.json", MODEL_ROOT));
  if (!response.ok)
    throw new Error("Enhancement model metadata is unavailable.");
  const manifest = await response.json(),
    url = new URL("enhancement.onnx", MODEL_ROOT);
  let cache;
  try {
    cache = await caches.open("colorcheck-enhancement-v1");
  } catch {}
  let modelResponse = await cache?.match(url.href);
  if (!modelResponse) {
    modelResponse = await fetch(url);
    if (!modelResponse.ok)
      throw new Error("The enhancement model could not be downloaded.");
  }
  const bytes = await modelResponse.arrayBuffer();
  const hash = Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (v) => v.toString(16).padStart(2, "0"),
  ).join("");
  if (bytes.byteLength !== manifest.bytes || hash !== manifest.sha256) {
    await cache?.delete(url.href);
    throw new Error(
      "Enhancement model integrity check failed. Try loading it again.",
    );
  }
  try {
    await cache?.put(url.href, new Response(bytes));
  } catch {}
  const session = await ort.InferenceSession.create(bytes, {
    executionProviders: ["wasm"],
    graphOptimizationLevel: "disabled",
  });
  return { session, manifest };
}

self.onmessage = async ({ data: m }) => {
  try {
    const pixels = new Uint8ClampedArray(m.pixels);
    if (pixels.length !== 256 * 256 * 4)
      throw new Error("Invalid enhancement preview.");
    sessionPromise ??= loadModel().catch((error) => {
      sessionPromise = null;
      throw error;
    });
    const { session, manifest } = await sessionPromise;
    self.postMessage({ stage: "Analyzing photo on this device…" });
    const input = new Float32Array(3 * 256 * 256),
      start = performance.now();
    for (let i = 0; i < 256 * 256; i++)
      for (let c = 0; c < 3; c++)
        input[c * 256 * 256 + i] = pixels[i * 4 + c] / 255;
    const result = await session.run({
      image: new ort.Tensor("float32", input, [1, 3, 256, 256]),
    });
    const lut = new Float32Array(result.lut.data);
    validateEnhancementLut(lut);
    const assessment = assessEnhancement(pixels, lut);
    self.postMessage(
      {
        lut,
        assessment,
        modelId: manifest.id,
        modelHash: manifest.sha256,
        coefficients: Array.from(result.coefficients.data),
        inferenceMs: performance.now() - start,
      },
      [lut.buffer],
    );
  } catch (error) {
    self.postMessage({ error: error.message });
  }
};
