import * as ort from "../vendor/onnxruntime/ort.wasm.min.mjs";
import {
  assessEnhancement,
  validateEnhancementLut,
} from "./enhancement-lut.js";

const MODEL_ROOT = new URL("../assets/models/colorcheck-v11/", import.meta.url);
let sessionPromise;
ort.env.wasm.numThreads = 1;
ort.env.wasm.proxy = false;
ort.env.wasm.wasmPaths = new URL(
  "../vendor/onnxruntime/",
  import.meta.url,
).href;

async function loadModel() {
  self.postMessage({ stage: "Loading ColorCheck V11 (3.8 MB)…" });
  const metadataResponse = await fetch(new URL("manifest.json", MODEL_ROOT));
  if (!metadataResponse.ok) throw new Error("V11 metadata is unavailable.");
  const manifest = await metadataResponse.json(),
    url = new URL(manifest.artifact, MODEL_ROOT);
  let cache;
  try {
    cache = await caches.open("colorcheck-v11-reference-research");
  } catch {}
  let modelResponse = await cache?.match(url.href);
  if (!modelResponse) modelResponse = await fetch(url);
  if (!modelResponse?.ok) throw new Error("V11 could not be downloaded.");
  const bytes = await modelResponse.arrayBuffer(),
    hash = Array.from(
      new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
      (value) => value.toString(16).padStart(2, "0"),
    ).join("");
  if (bytes.byteLength !== manifest.bytes || hash !== manifest.sha256) {
    await cache?.delete(url.href);
    throw new Error("V11 model integrity check failed.");
  }
  try {
    await cache?.put(url.href, new Response(bytes));
  } catch {}
  const session = await ort.InferenceSession.create(bytes, {
    executionProviders: ["wasm"],
    graphOptimizationLevel: "all",
  });
  return { session, manifest };
}

function toTensor(pixels) {
  if (pixels.length !== 128 * 128 * 4)
    throw new Error("Invalid V11 analysis image.");
  const values = new Float32Array(3 * 128 * 128);
  for (let pixel = 0; pixel < 128 * 128; pixel++)
    for (let channel = 0; channel < 3; channel++)
      values[channel * 128 * 128 + pixel] = pixels[pixel * 4 + channel] / 255;
  return new ort.Tensor("float32", values, [1, 3, 128, 128]);
}

self.onmessage = async ({ data: message }) => {
  try {
    sessionPromise ??= loadModel().catch((error) => {
      sessionPromise = null;
      throw error;
    });
    const { session, manifest } = await sessionPromise,
      sourcePixels = new Uint8ClampedArray(message.sourcePixels),
      referencePixels = new Uint8ClampedArray(message.referencePixels),
      start = performance.now();
    self.postMessage({ stage: "Comparing target and reference with V11…" });
    const output = await session.run({
      source: toTensor(sourcePixels),
      reference: toTensor(referencePixels),
    });
    const lut = new Float32Array(output.lut.data);
    validateEnhancementLut(lut);
    const assessment = assessEnhancement(
      sourcePixels,
      lut,
      [65, 50, 35, 20, 0],
    );
    self.postMessage(
      {
        lut,
        assessment,
        modelId: manifest.id,
        modelHash: manifest.sha256,
        evaluation: manifest.evaluation,
        checkpointEpoch: manifest.checkpointEpoch,
        research: true,
        inferenceMs: performance.now() - start,
      },
      [lut.buffer],
    );
  } catch (error) {
    self.postMessage({ error: error.message });
  }
};
