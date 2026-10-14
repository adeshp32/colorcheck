/** Copy only the single-thread WASM browser runtime, not every installed backend. */
import { copyFile, mkdir } from "node:fs/promises";
const destination = new URL("../web/vendor/onnxruntime/", import.meta.url);
await mkdir(destination, { recursive: true });
for (const file of [
  "ort.wasm.min.mjs",
  "ort-wasm-simd-threaded.mjs",
  "ort-wasm-simd-threaded.wasm",
]) {
  await copyFile(
    new URL(`../node_modules/onnxruntime-web/dist/${file}`, import.meta.url),
    new URL(file, destination),
  );
}
console.log("Local ONNX Runtime Web WASM files prepared.");
