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
    await maskPage.evaluate(() => document.fonts.ready);
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
    const toolStripBefore = await maskPage.locator(".tools").boundingBox();
    assert.equal(await maskPage.locator(".social-footer a").isVisible(), true);
    await maskPage.locator("[data-panel=mask]").click();
    await maskPage.locator("#add-radial").click();
    assert.equal(await maskPage.locator("#adjustment-scope option").count(), 2);
    await maskPage.locator("#close-tools").click();
    const touch = await maskPage.context().newCDPSession(maskPage);
    await touch.send("Emulation.setTouchEmulationEnabled", {
      enabled: true,
      maxTouchPoints: 2,
    });
    async function pinchMask() {
      const bounds = await maskPage.locator("#mask-overlay").boundingBox();
      const points = (spread) =>
        [0, 1].map((id) => ({
          id,
          x: bounds.x + bounds.width * (id ? 0.5 + spread : 0.5 - spread),
          y: bounds.y + bounds.height * 0.5,
        }));
      await touch.send("Input.dispatchTouchEvent", {
        type: "touchStart",
        touchPoints: points(0.1),
      });
      await touch.send("Input.dispatchTouchEvent", {
        type: "touchMove",
        touchPoints: points(0.15),
      });
      await touch.send("Input.dispatchTouchEvent", {
        type: "touchEnd",
        touchPoints: [],
      });
    }
    const radius = Number(
      await maskPage.locator("#mask-2-radius-x").inputValue(),
    );
    await pinchMask();
    assert.ok(
      Number(await maskPage.locator("#mask-2-radius-x").inputValue()) >
        radius * 1.3,
      "Native two-finger touch must resize the radial mask",
    );
    assert.equal(
      await maskPage
        .locator("#viewer")
        .evaluate((node) => node.style.getPropertyValue("--view-zoom")),
      "1",
      "Mask pinch must not zoom the photo",
    );
    await maskPage.locator("#undo").click();
    assert.equal(
      Number(await maskPage.locator("#mask-2-radius-x").inputValue()),
      radius,
      "One undo restores the complete mask pinch",
    );
    const edge = await maskPage.locator("#mask-overlay").boundingBox();
    await maskPage.mouse.move(
      edge.x + edge.width * 0.8,
      edge.y + edge.height * 0.5,
    );
    await maskPage.mouse.down();
    await maskPage.mouse.move(
      edge.x + edge.width * 0.87,
      edge.y + edge.height * 0.5,
    );
    await maskPage.mouse.up();
    assert.ok(
      Number(await maskPage.locator("#mask-2-radius-x").inputValue()) >
        radius + 5,
      "Dragging the radial edge resizes it without selecting a separate gesture mode",
    );
    await maskPage.locator("#undo").click();
    await maskPage.locator("[data-panel=light]").click();
    const menuViewer = await maskPage.locator("#viewer").boundingBox();
    assert.equal(
      (await maskPage.locator(".tools").boundingBox()).y,
      toolStripBefore.y,
      "Tool strip must stay at the bottom while menus open upward",
    );
    const menuBounds = await maskPage.locator("#editing-tools").boundingBox();
    assert.ok(
      menuBounds.height <= 844 * 0.41,
      "Tool browsing must leave most of the image workspace visible",
    );
    await maskPage.locator("#inspector").evaluate((node) => {
      node.scrollTop = node.scrollHeight;
    });
    assert.equal(await maskPage.evaluate(() => scrollY), 0);
    await maskPage.screenshot({
      path: join(artifacts, "mobile-upward-tools.png"),
    });
    assert.deepEqual(
      menuViewer,
      viewerBefore,
      "Opening tools must never resize the photo canvas",
    );
    await maskPage
      .getByRole("button", { name: "Exposure (EV)", exact: true })
      .click();
    assert.equal(await maskPage.locator("#slider-exposure").isVisible(), true);
    assert.equal(
      await maskPage.locator(".single-adjustment").isVisible(),
      true,
    );
    assert.equal(await maskPage.locator("#slider-contrast").isVisible(), false);
    assert.deepEqual(
      await maskPage.locator("#viewer").boundingBox(),
      viewerBefore,
    );
    await maskPage.screenshot({
      path: join(artifacts, "mobile-single-adjustment.png"),
    });
    const overlayColors = await maskPage
      .locator("#mask-overlay")
      .evaluate((canvas) => {
        const c = canvas.getContext("2d");
        return {
          inside: [...c.getImageData(420, 320, 1, 1).data],
          outside: [...c.getImageData(10, 10, 1, 1).data],
        };
      });
    assert.ok(
      overlayColors.inside[1] > overlayColors.inside[0] + 100 &&
        overlayColors.inside[2] > overlayColors.inside[0] + 100,
      "Selected mask should be cyan",
    );
    assert.equal(
      overlayColors.outside[0],
      overlayColors.outside[1],
      "Excluded mask should be gray",
    );
    assert.equal(overlayColors.outside[1], overlayColors.outside[2]);
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
    const waitForCenter = (expected) =>
      maskPage.waitForFunction((expected) => {
        const pixels = document
          .querySelector("#preview")
          .getContext("2d")
          .getImageData(400, 300, 1, 1).data;
        return expected.every((value, index) => pixels[index] === value);
      }, expected);
    await maskPage.locator("#undo").click();
    await waitForCenter(beforeMask.center);
    assert.deepEqual((await samples()).center, beforeMask.center);
    await maskPage.locator("#redo").click();
    await waitForCenter(afterMask.center);
    assert.deepEqual((await samples()).center, afterMask.center);
    await maskPage.locator("[data-panel=mask]").click();
    await maskPage.locator("#mask-invert").check();
    await waitForCenter(beforeMask.center);
    assert.deepEqual((await samples()).center, beforeMask.center);
    await maskPage.locator("#mask-invert").uncheck();
    await waitForCenter(afterMask.center);
    await maskPage.locator("#mask-operation").selectOption("subtract");
    await maskPage.locator("#append-linear").click();
    assert.equal(await maskPage.locator("#mask-component option").count(), 2);
    const endX = Number(await maskPage.locator("#mask-5-end-x").inputValue());
    await maskPage.locator("#close-tools").click();
    await pinchMask();
    assert.ok(
      Number(await maskPage.locator("#mask-5-end-x").inputValue()) > endX,
      "Linear mask endpoints must respond to native pinch",
    );
    await maskPage.locator("[data-panel=mask]").click();
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
    await maskPage
      .getByRole("button", { name: "Zoom in", exact: true })
      .click();
    assert.ok(
      Number(
        await maskPage
          .locator("#viewer")
          .evaluate((node) => node.style.getPropertyValue("--view-zoom")),
      ) > 1,
    );
    await maskPage
      .getByRole("button", { name: "Fit image", exact: true })
      .click();
    assert.deepEqual(
      await maskPage.locator("#viewer").boundingBox(),
      viewerBefore,
    );
    await maskPage.locator("[data-panel=light]").click();
    await maskPage.locator("#open-curves").click();
    await maskPage.locator("[data-channel=red]").click();
    const curve = await maskPage.locator("#curve-preview").boundingBox();
    await maskPage.mouse.click(
      curve.x + curve.width * 0.5,
      curve.y + curve.height * 0.3,
    );
    await maskPage.screenshot({
      path: join(artifacts, "mobile-compact-curves.png"),
    });
    await maskPage.locator("#curve-point-options summary").click();
    await maskPage.locator("#curve-output").fill("190");
    await maskPage.locator("#curve-output").dispatchEvent("change");
    assert.equal(await maskPage.locator("#curve-output").inputValue(), "190");
    await maskPage.screenshot({ path: join(artifacts, "mobile-curves.png") });
    await maskPage.getByRole("button", { name: "Done", exact: true }).click();
    await maskPage.locator("[data-panel=color]").click();
    await maskPage.locator("#open-color-mixer").click();
    await maskPage
      .getByRole("button", { name: "Adjust red colors", exact: true })
      .click();
    await maskPage.locator("#slider-mix-hue").evaluate((input) => {
      input.value = "25";
      input.dispatchEvent(new Event("input"));
      input.dispatchEvent(new Event("change"));
    });
    assert.equal(await maskPage.locator("#slider-mix-hue").inputValue(), "25");
    await maskPage
      .getByRole("button", { name: "Adjust blue colors", exact: true })
      .click();
    assert.equal(await maskPage.locator("#slider-mix-hue").inputValue(), "0");
    await maskPage
      .getByRole("button", { name: "Adjust red colors", exact: true })
      .click();
    assert.equal(await maskPage.locator("#slider-mix-hue").inputValue(), "25");
    await maskPage.screenshot({
      path: join(artifacts, "mobile-color-mixer.png"),
    });
    await maskPage.getByRole("button", { name: "Done", exact: true }).click();
    await maskPage.locator("[data-panel=light]").click();
    await maskPage
      .getByRole("button", { name: "Exposure (EV)", exact: true })
      .click();
    await maskPage
      .getByRole("button", {
        name: "Apply Exposure (EV) to region",
        exact: true,
      })
      .click();
    await maskPage
      .getByRole("button", { name: "New radial mask", exact: true })
      .click();
    await maskPage.locator("#close-tools").click();
    await maskPage.locator(".return-adjustment").click();
    assert.equal(
      await maskPage.locator(".single-adjustment").isVisible(),
      true,
    );
    await maskPage.getByRole("button", { name: "Done", exact: true }).click();
    await maskPage
      .getByRole("button", { name: "Fullscreen image", exact: true })
      .click();
    assert.equal(
      await maskPage
        .locator("body")
        .evaluate((node) => node.classList.contains("image-fullscreen")),
      true,
    );
    await maskPage
      .getByRole("button", { name: "Fullscreen image", exact: true })
      .click();
    await maskPage.close();
    assert.deepEqual(errors, []);
    const grainPage = await browser.newPage({
      viewport: { width: 390, height: 844 },
    });
    grainPage.on("pageerror", (error) => errors.push(error.message));
    await grainPage.goto(url);
    await grainPage.locator("#target").setInputFiles({
      name: "grain-photo.png",
      mimeType: "image/png",
      buffer: Buffer.from(bytes, "base64"),
    });
    await grainPage.waitForFunction(
      () => document.querySelector("#preview").width === 800,
    );
    await grainPage.locator("[data-panel=output]").click();
    await grainPage.locator("#format").selectOption("image/png");
    await grainPage.locator("[data-panel=detail]").click();
    await grainPage
      .getByRole("button", { name: "Film grain", exact: true })
      .click();
    await grainPage.locator("#slider-grain").evaluate((input) => {
      input.value = "80";
      input.dispatchEvent(new Event("change"));
    });
    await grainPage
      .getByRole("button", { name: "Back to tools", exact: true })
      .click();
    await grainPage
      .getByRole("button", { name: "Grain size", exact: true })
      .click();
    await grainPage.locator("#slider-grainSize").evaluate((input) => {
      input.value = "2";
      input.dispatchEvent(new Event("change"));
    });
    const expectedGrain = await grainPage.evaluate(async (base64) => {
      const { applyPhotoAdjustments, createDefaultEditSettings } =
        await import("./src/image-processing.js");
      const bitmap = await createImageBitmap(
        new Blob([Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))], {
          type: "image/png",
        }),
      );
      const canvas = document.createElement("canvas");
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const context = canvas.getContext("2d");
      context.drawImage(bitmap, 0, 0);
      bitmap.close();
      const settings = {
        ...createDefaultEditSettings(),
        grain: 80,
        grainSize: 2,
      };
      const result = applyPhotoAdjustments(
        context.getImageData(0, 0, 800, 600).data,
        800,
        600,
        settings,
      ).data;
      return [
        ...new Uint8Array(await crypto.subtle.digest("SHA-256", result)),
      ].join(",");
    }, bytes);
    await grainPage.waitForFunction(async (expected) => {
      const canvas = document.querySelector("#preview");
      const data = canvas
        .getContext("2d")
        .getImageData(0, 0, canvas.width, canvas.height).data;
      return (
        [...new Uint8Array(await crypto.subtle.digest("SHA-256", data))].join(
          ",",
        ) === expected
      );
    }, expectedGrain);
    await grainPage.screenshot({
      path: join(artifacts, "mobile-film-grain.png"),
    });
    const grainDownload = grainPage.waitForEvent("download");
    await grainPage.locator("#export").click();
    const grainPath = join(artifacts, "grain-export.png");
    await (await grainDownload).saveAs(grainPath);
    const grainExport = await grainPage.evaluate(async (base64) => {
      const bitmap = await createImageBitmap(
        new Blob([Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))], {
          type: "image/png",
        }),
      );
      const canvas = document.createElement("canvas");
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const context = canvas.getContext("2d");
      context.drawImage(bitmap, 0, 0);
      bitmap.close();
      return {
        width: canvas.width,
        height: canvas.height,
        hash: [
          ...new Uint8Array(
            await crypto.subtle.digest(
              "SHA-256",
              context.getImageData(0, 0, canvas.width, canvas.height).data,
            ),
          ),
        ].join(","),
      };
    }, fs.readFileSync(grainPath).toString("base64"));
    assert.equal(grainExport.width, 800);
    assert.equal(grainExport.height, 600);
    assert.equal(
      grainExport.hash,
      expectedGrain,
      "Grain PNG export must exactly match full-resolution processing",
    );
    await grainPage.close();
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
