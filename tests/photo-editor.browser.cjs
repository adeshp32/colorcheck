const { chromium } = require("playwright");
const fs = require("fs");
const assert = require("assert");
const { spawn } = require("node:child_process");
const { tmpdir } = require("node:os");
const { join } = require("node:path");
(async () => {
  const artifacts = fs.mkdtempSync(join(tmpdir(), "colorcheck-photos-"));
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
      server.once("error", (error) => {
        clearTimeout(timeout);
        reject(error);
      });
      server.stdout.on("data", (chunk) => {
        const match = chunk.toString().match(/http:\/\/127\.0\.0\.1:\d+\//);
        if (match) {
          clearTimeout(timeout);
          resolve(match[0]);
        }
      });
    });
    browser = await chromium.launch({
      channel: process.env.PHOTO_BROWSER_CHANNEL || undefined,
      headless: true,
    });
    const page = await browser.newPage({
      viewport: { width: 1440, height: 960 },
    });
    if (process.env.ML_TEST_ARTIFACT_DIR) {
      for (const name of ["manifest.json", "enhancement.onnx"]) {
        await page.route(`**/assets/models/adaptive-lut/${name}`, (route) =>
          route.fulfill({
            path: join(process.env.ML_TEST_ARTIFACT_DIR, name),
            contentType: name.endsWith(".json")
              ? "application/json"
              : "application/octet-stream",
          }),
        );
      }
    }
    const errors = [],
      requests = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("request", (r) =>
      requests.push({ method: r.method(), url: r.url() }),
    );
    await page.goto(url);
    const bytes = await page.evaluate(() => {
      const c = document.createElement("canvas");
      c.width = 800;
      c.height = 600;
      const x = c.getContext("2d");
      x.fillStyle = "#91b8cd";
      x.fillRect(0, 0, 800, 600);
      x.fillStyle = "#26765f";
      x.fillRect(0, 380, 800, 220);
      x.fillStyle = "#ddad78";
      x.fillRect(280, 180, 200, 320);
      x.fillStyle = "#cf5f67";
      x.beginPath();
      x.arc(385, 150, 90, 0, Math.PI * 2);
      x.fill();
      return c.toDataURL("image/png").split(",")[1];
    });
    await page.locator("#target").setInputFiles({
      name: "test-photo.png",
      mimeType: "image/png",
      buffer: Buffer.from(bytes, "base64"),
    });
    await page.waitForFunction(
      () => document.querySelector("#preview").width === 800,
    );
    const original = await page
      .locator("#preview")
      .evaluate((c) => c.toDataURL());
    await page.locator("#reference").setInputFiles({
      name: "reference.png",
      mimeType: "image/png",
      buffer: Buffer.from(bytes, "base64"),
    });
    await page.locator("#match").click();
    await page.waitForTimeout(200);
    assert.equal(await page.locator("#slider-matchColor").inputValue(), "65");
    await page.locator("[data-panel=light]").click();
    await page.locator("#slider-exposure").evaluate((el) => {
      el.value = "1";
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await page
      .waitForFunction(
        (before) => document.querySelector("#preview").toDataURL() !== before,
        original,
        { timeout: 15000 },
      )
      .catch(async (error) => {
        console.error({
          errors,
          status: await page.locator("#status").innerText(),
          exposure: await page.locator("#slider-exposure").inputValue(),
        });
        throw error;
      });
    await page.locator("#undo").click();
    await page.waitForTimeout(250);
    assert.equal(await page.locator("#slider-exposure").inputValue(), "0");
    await page.locator("#redo").click();
    assert.equal(await page.locator("#slider-exposure").inputValue(), "1");
    await page.locator("[data-panel=color]").click();
    await page.locator("[data-range=shadows]").click();
    await page.locator("#wheel").focus();
    await page.keyboard.press("ArrowUp");
    assert.equal(
      await page.locator("#slider-grade-saturation").inputValue(),
      "2",
    );
    await page.locator("[data-panel=match]").click();
    const beforeEnhancement = await page
      .locator("#preview")
      .evaluate((canvas) => canvas.toDataURL());
    await page.locator("#enhance").click();
    await page
      .waitForFunction(
        () =>
          document
            .querySelector("#enhancement-status")
            .textContent.includes("Suggested strength"),
        null,
        { timeout: 60000 },
      )
      .catch(async (error) => {
        console.error(await page.locator("#enhancement-status").innerText());
        throw error;
      });
    assert.ok(
      Number(await page.locator("#slider-enhanceStrength").inputValue()) > 0,
    );
    await page.waitForFunction(
      (before) => document.querySelector("#preview").toDataURL() !== before,
      beforeEnhancement,
    );
    const browserParity = await page.evaluate(async () => {
      const ort = await import("./vendor/onnxruntime/ort.wasm.min.mjs");
      ort.env.wasm.numThreads = 1;
      ort.env.wasm.proxy = false;
      ort.env.wasm.wasmPaths = new URL(
        "./vendor/onnxruntime/",
        location.href,
      ).href;
      const manifest = await (
        await fetch("./assets/models/adaptive-lut/manifest.json")
      ).json();
      const session = await ort.InferenceSession.create(
        "./assets/models/adaptive-lut/enhancement.onnx",
        { executionProviders: ["wasm"], graphOptimizationLevel: "disabled" },
      );
      const input = new Float32Array(3 * 256 * 256);
      for (let y = 0; y < 256; y++)
        for (let x = 0; x < 256; x++) {
          const i = y * 256 + x;
          input[i] = x / 255;
          input[256 * 256 + i] = y / 255;
          input[2 * 256 * 256 + i] = 0.5;
        }
      const start = performance.now(),
        outputs = await session.run({
          image: new ort.Tensor("float32", input, [1, 3, 256, 256]),
        });
      const error = Math.max(
        ...manifest.browserProbe.lutSamples.map((v, i) =>
          Math.abs(v - outputs.lut.data[i * 2000]),
        ),
      );
      await session.release();
      return {
        modelHash: manifest.sha256,
        maximumSampledLutError: error,
        sampleCount: manifest.browserProbe.lutSamples.length,
        gradientInferenceMs: performance.now() - start,
        browser: navigator.userAgent,
      };
    });
    assert.ok(
      browserParity.maximumSampledLutError < 1e-4,
      "Browser ONNX output must match PyTorch gradient fixture",
    );
    fs.writeFileSync(
      join(artifacts, "ml-evaluation.json"),
      JSON.stringify(browserParity, null, 2),
    );
    console.log("Browser ML evaluation:", browserParity);
    await page.locator("[data-panel=color]").click();
    await page.screenshot({
      path: join(artifacts, "desktop.png"),
      fullPage: true,
    });
    await page.locator("[data-panel=crop]").click();
    await page.locator("#ratio").selectOption("1");
    await page.waitForTimeout(200);
    await page.locator("[data-panel=output]").click();
    await page.locator("#format").selectOption("image/png");
    const download = page.waitForEvent("download");
    await page.locator("#export").click();
    const d = await download;
    await d.saveAs(join(artifacts, "export.png"));
    const png = fs.readFileSync(join(artifacts, "export.png"));
    assert.equal(png.readUInt32BE(16), 600);
    assert.equal(png.readUInt32BE(20), 600);
    await page.waitForFunction(
      () => !document.querySelector("#export-dialog").open,
    );
    await page.locator("#target").setInputFiles({
      name: "unsupported.heic",
      mimeType: "image/heic",
      buffer: Buffer.from("invalid"),
    });
    await page.waitForTimeout(200);
    assert.match(await page.locator("#status").innerText(), /HEIC/);
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      await page.locator("[data-panel=color]").click();
      await page.screenshot({
        path: join(artifacts, `mobile-${width}.png`),
        fullPage: true,
      });
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `Overflow at ${width}`,
      );
    }
    assert.deepEqual(errors, []);
    const layoutPage = await browser.newPage({
      viewport: { width: 1280, height: 720 },
    });
    layoutPage.on("pageerror", (error) => errors.push(error.message));
    await layoutPage.goto(url);
    assert.equal(await layoutPage.locator(".social-footer a svg").count(), 1);
    async function assertPreviewFits() {
      await layoutPage.waitForFunction(() => {
        const image = document
          .querySelector("#preview")
          .getBoundingClientRect();
        const viewer = document
          .querySelector("#viewer")
          .getBoundingClientRect();
        return (
          image.width > 0 &&
          image.height > 0 &&
          image.left >= viewer.left &&
          image.top >= viewer.top &&
          image.right <= viewer.right &&
          image.bottom <= viewer.bottom
        );
      });
    }
    for (const [width, height] of [
      [600, 2400],
      [2400, 600],
    ]) {
      const fixture = await layoutPage.evaluate(
        ({ width, height }) => {
          const canvas = document.createElement("canvas");
          canvas.width = width;
          canvas.height = height;
          canvas.getContext("2d").fillRect(0, 0, width, height);
          return canvas.toDataURL("image/png").split(",")[1];
        },
        { width, height },
      );
      await layoutPage.locator("#target").setInputFiles({
        name: "large-photo.png",
        mimeType: "image/png",
        buffer: Buffer.from(fixture, "base64"),
      });
      await layoutPage.waitForFunction(
        ({ width, height }) => {
          const canvas = document.querySelector("#preview");
          return canvas.width / canvas.height === width / height;
        },
        { width, height },
      );
      for (const mode of ["right", "bottom", "floating"]) {
        await layoutPage.locator(`[data-dock-mode=${mode}]`).click();
        await assertPreviewFits();
      }
    }
    const beforeDrag = await layoutPage.locator("#editing-tools").boundingBox();
    await layoutPage.locator("#panel-grip").focus();
    await layoutPage.keyboard.press("ArrowLeft");
    const afterKey = await layoutPage.locator("#editing-tools").boundingBox();
    assert.equal(Math.round(beforeDrag.x - afterKey.x), 10);
    const grip = await layoutPage.locator("#panel-grip").boundingBox();
    await layoutPage.mouse.move(grip.x + 18, grip.y + 18);
    await layoutPage.mouse.down();
    await layoutPage.mouse.move(grip.x - 82, grip.y + 58, { steps: 5 });
    await layoutPage.mouse.up();
    const afterDrag = await layoutPage.locator("#editing-tools").boundingBox();
    assert.ok(
      afterDrag.x < afterKey.x - 80,
      "Floating tools must be draggable",
    );
    await layoutPage.screenshot({
      path: join(artifacts, "floating-tools.png"),
    });
    await layoutPage.locator("[data-dock-mode=right]").click();
    await layoutPage.evaluate(() => scrollTo(0, 150));
    await layoutPage.waitForFunction(
      () =>
        document.querySelector("#editing-tools").getBoundingClientRect().top >=
          0 &&
        document.querySelector("#editing-tools").getBoundingClientRect().top <=
          64,
    );
    await layoutPage.evaluate(() => scrollTo(0, 0));
    await layoutPage.locator("[data-dock-mode=bottom]").click();
    await layoutPage.screenshot({ path: join(artifacts, "bottom-tools.png") });
    await layoutPage.setViewportSize({ width: 390, height: 844 });
    await assertPreviewFits();
    await layoutPage.locator("[data-panel=mask]").click();
    await layoutPage.locator("[data-dock-mode=floating]").click();
    await layoutPage.setViewportSize({ width: 320, height: 568 });
    await assertPreviewFits();
    assert.ok(
      await layoutPage.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    const mobilePanel = await layoutPage
      .locator("#editing-tools")
      .boundingBox();
    assert.ok(
      mobilePanel.x >= 0 &&
        mobilePanel.y >= 0 &&
        mobilePanel.x + mobilePanel.width <= 320 &&
        mobilePanel.y + mobilePanel.height <= 568,
    );
    await layoutPage.locator("[data-dock-mode=bottom]").click();
    await layoutPage.screenshot({
      path: join(artifacts, "mobile-tools.png"),
      fullPage: true,
    });
    await layoutPage.close();
    assert.deepEqual(errors, []);
    const maskPage = await browser.newPage({
      viewport: { width: 390, height: 844 },
    });
    maskPage.on("pageerror", (error) => errors.push(error.message));
    await maskPage.goto(url);
    await maskPage.locator("#target").setInputFiles({
      name: "masked-photo.png",
      mimeType: "image/png",
      buffer: Buffer.from(bytes, "base64"),
    });
    await maskPage.waitForFunction(
      () => document.querySelector("#preview").width === 800,
    );
    assert.equal(
      await maskPage.locator("#editor-layout").getAttribute("data-tray"),
      "closed",
    );
    const viewerBefore = await maskPage.locator("#viewer").boundingBox();
    assert.ok(
      viewerBefore.height > 450,
      "Image should dominate the closed mobile workspace",
    );
    const samples = () =>
      maskPage.locator("#preview").evaluate((canvas) => {
        const context = canvas.getContext("2d");
        return {
          center: [...context.getImageData(400, 300, 1, 1).data],
          outside: [...context.getImageData(10, 10, 1, 1).data],
        };
      });
    const beforeMask = await samples();
    await maskPage.locator("[data-panel=mask]").click();
    await maskPage.locator("#add-radial").click();
    assert.equal(await maskPage.locator("#adjustment-scope option").count(), 2);
    await maskPage.locator("[data-panel=light]").click();
    await maskPage
      .getByRole("button", { name: "Exposure (EV)", exact: true })
      .click();
    assert.equal(await maskPage.locator("#slider-exposure").isVisible(), true);
    await maskPage.locator("#slider-exposure").evaluate((input) => {
      input.value = "1";
      input.dispatchEvent(new Event("input"));
      input.dispatchEvent(new Event("change"));
    });
    await maskPage.waitForFunction(
      () =>
        document
          .querySelector("#preview")
          .getContext("2d")
          .getImageData(400, 300, 1, 1).data[0] > 240,
    );
    const afterMask = await samples();
    assert.deepEqual(afterMask.outside, beforeMask.outside);
    assert.notDeepEqual(afterMask.center, beforeMask.center);
    await maskPage.locator("#undo").click();
    await maskPage.waitForTimeout(250);
    assert.deepEqual((await samples()).center, beforeMask.center);
    await maskPage.locator("#redo").click();
    await maskPage.waitForTimeout(250);
    assert.deepEqual((await samples()).center, afterMask.center);
    await maskPage.locator("[data-panel=mask]").click();
    await maskPage.locator("#mask-invert").check();
    await maskPage.waitForTimeout(250);
    assert.deepEqual((await samples()).center, beforeMask.center);
    await maskPage.locator("#mask-invert").uncheck();
    await maskPage.locator("#mask-operation").selectOption("subtract");
    await maskPage.locator("#append-linear").click();
    assert.equal(await maskPage.locator("#mask-component option").count(), 2);
    await maskPage.locator("#remove-component").click();
    const overlayBounds = await maskPage.locator("#mask-overlay").boundingBox();
    await maskPage.locator("#mask-overlay").focus();
    await maskPage.keyboard.press("ArrowRight");
    await maskPage.screenshot({ path: join(artifacts, "mobile-masking.png") });
    assert.ok(overlayBounds.height > 100);
    await maskPage.locator("[data-panel=output]").click();
    await maskPage.locator("#format").selectOption("image/png");
    const maskedDownload = maskPage.waitForEvent("download");
    await maskPage.locator("#export").click();
    await (await maskedDownload).saveAs(join(artifacts, "masked-export.png"));
    const exportedMask = await maskPage.evaluate(
      async (data) => {
        const binary = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
        const image = await createImageBitmap(
          new Blob([binary], { type: "image/png" }),
        );
        const canvas = document.createElement("canvas");
        canvas.width = image.width;
        canvas.height = image.height;
        const context = canvas.getContext("2d");
        context.drawImage(image, 0, 0);
        const result = {
          width: image.width,
          height: image.height,
          center: [...context.getImageData(400, 300, 1, 1).data],
          outside: [...context.getImageData(10, 10, 1, 1).data],
        };
        image.close();
        return result;
      },
      fs.readFileSync(join(artifacts, "masked-export.png")).toString("base64"),
    );
    assert.equal(exportedMask.width, 800);
    assert.equal(exportedMask.height, 600);
    assert.deepEqual(exportedMask.outside, beforeMask.outside);
    assert.deepEqual(exportedMask.center, afterMask.center);
    await maskPage.locator("#close-tools").click();
    await maskPage.screenshot({
      path: join(artifacts, "mobile-image-first.png"),
    });
    assert.equal(
      await maskPage.evaluate(() => scrollY),
      0,
      "Tools should not require page scrolling",
    );
    await maskPage.close();
    assert.deepEqual(errors, []);
    const fallback = await browser.newPage();
    await fallback.route("**/assets/models/**", (route) =>
      route.fulfill({ status: 503, body: "Unavailable" }),
    );
    await fallback.goto(url);
    await fallback.locator("#target").setInputFiles({
      name: "fallback.png",
      mimeType: "image/png",
      buffer: Buffer.from(bytes, "base64"),
    });
    await fallback.locator("#enhance").click();
    await fallback.waitForFunction(() =>
      document
        .querySelector("#enhancement-status")
        .textContent.includes("unavailable"),
    );
    assert.equal(
      await fallback.locator("#export").isEnabled(),
      true,
      "Manual export must survive model failure",
    );
    await fallback.close();
    assert.ok(
      requests.every((r) => r.method === "GET"),
      "Photos must not be uploaded",
    );
    console.log(
      "Desktop/mobile layouts, local input, match, edit, undo/redo, wheel keyboard, crop, full-resolution PNG export, unsupported formats, no uploads: passed.",
    );
    console.log(`Screenshots and export: ${artifacts}`);
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
