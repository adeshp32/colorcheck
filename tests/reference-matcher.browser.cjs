const assert = require("node:assert");
const fs = require("node:fs");
const { basename, join } = require("node:path");
const { spawn } = require("node:child_process");
const { chromium } = require("playwright");

(async () => {
  const artifactDirectory = process.env.REFERENCE_MODEL_ARTIFACT_DIR;
  if (!artifactDirectory)
    throw new Error(
      "Set REFERENCE_MODEL_ARTIFACT_DIR to an exported model directory.",
    );

  const manifest = JSON.parse(
    fs.readFileSync(join(artifactDirectory, "manifest.json"), "utf8"),
  );
  const server = spawn(process.execPath, ["tools/serve.mjs"], {
    env: { ...process.env, PORT: "0" },
    stdio: ["ignore", "pipe", "inherit"],
  });
  let browser;
  try {
    const url = await new Promise((resolve, reject) => {
      const timeout = setTimeout(
        () => reject(new Error("Static server startup timed out")),
        10000,
      );
      server.stdout.on("data", (chunk) => {
        const match = chunk.toString().match(/http:\/\/127\.0\.0\.1:\d+\//);
        if (match) {
          clearTimeout(timeout);
          resolve(match[0]);
        }
      });
      server.once("error", reject);
    });
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    await page.route("**/reference-model/*", (route) => {
      const name = basename(new URL(route.request().url()).pathname);
      route.fulfill({
        path: join(artifactDirectory, name),
        contentType: name.endsWith(".json")
          ? "application/json"
          : "application/octet-stream",
      });
    });
    await page.goto(url);
    const result = await page.evaluate(async () => {
      const metadata = await fetch("/reference-model/manifest.json").then((r) =>
        r.json(),
      );
      const probe = metadata.browserProbe;
      if (probe.inputGeneration !== "colorcheck-modulo-v1")
        throw new Error("Unknown browser probe input generator.");

      const ort = await import("/vendor/onnxruntime/ort.wasm.min.mjs");
      ort.env.wasm.numThreads = 1;
      ort.env.wasm.proxy = false;
      ort.env.wasm.wasmPaths = new URL(
        "/vendor/onnxruntime/",
        location.href,
      ).href;
      const model = await fetch("/reference-model/" + probe.artifact).then(
        (r) => r.arrayBuffer(),
      );
      const session = await ort.InferenceSession.create(model, {
        executionProviders: ["wasm"],
        graphOptimizationLevel: "disabled",
      });
      const size = probe.inputSize;
      const makeInput = (reference) => {
        const values = new Float32Array(3 * size * size);
        for (let channel = 0; channel < 3; channel++)
          for (let pixel = 0; pixel < size * size; pixel++)
            values[channel * size * size + pixel] =
              ((pixel * (channel * 2 + (reference ? 5 : 3)) +
                channel * (reference ? 53 : 37) +
                (reference ? 19 : 0)) %
                251) /
              250;
        return new ort.Tensor("float32", values, [1, 3, size, size]);
      };
      const started = performance.now();
      const output = await session.run({
        source: makeInput(false),
        reference: makeInput(true),
      });
      const inferenceMs = performance.now() - started;
      let maximumAbsoluteError = 0;
      for (let index = 0; index < probe.sampleIndices.length; index++)
        maximumAbsoluteError = Math.max(
          maximumAbsoluteError,
          Math.abs(
            output.lut.data[probe.sampleIndices[index]] -
              probe.expectedLutValues[index],
          ),
        );
      return {
        maximumAbsoluteError,
        inferenceMs,
        userAgent: navigator.userAgent,
      };
    });
    assert(
      result.maximumAbsoluteError <=
        manifest.browserProbe.maximumAllowedAbsoluteError,
      "Browser LUT error " +
        result.maximumAbsoluteError +
        " exceeded tolerance",
    );
    console.log("Reference matcher browser probe:", result);
  } finally {
    await browser?.close();
    server.kill();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
