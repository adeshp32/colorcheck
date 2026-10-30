const { chromium } = require("playwright");
const { spawn } = require("node:child_process");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { join } = require("node:path");
const { tmpdir } = require("node:os");
(async () => {
  const artifacts = fs.mkdtempSync(join(tmpdir(), "colorcheck-lens-"));
  const server = spawn(process.execPath, ["tools/serve.mjs"], {
    env: { ...process.env, PORT: "0" },
    stdio: ["ignore", "pipe", "inherit"],
  });
  let browser;
  try {
    const url = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(Error("Server timeout")), 10000);
      server.stdout.on("data", (data) => {
        const m = String(data).match(/http:\/\/127\.0\.0\.1:\d+\//);
        if (m) {
          clearTimeout(timer);
          resolve(m[0]);
        }
      });
      server.on("error", reject);
    });
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({
      viewport: { width: 1440, height: 960 },
      hasTouch: true,
    });
    const errors = [],
      requests = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("request", (request) =>
      requests.push({ method: request.method(), url: request.url() }),
    );
    await page.goto(url);
    const renderer = await page.evaluate(async () => {
      const { applyLensBlur } = await import("./src/lens-blur.js");
      const { createDefaultEditSettings } =
        await import("./src/image-processing.js");
      const width = 900,
        height = 200,
        data = new Uint8ClampedArray(width * height * 4),
        depth = new Float32Array(width * height);
      for (let y = 0; y < height; y++)
        for (let x = 0; x < width; x++) {
          const i = (y * width + x) * 4;
          data[i] = data[i + 1] = data[i + 2] = x % 4 < 2 ? 255 : 0;
          data[i + 3] = 255;
          depth[y * width + x] = x < 450 ? 0.9 : 0.1;
        }
      const settings = createDefaultEditSettings();
      settings.lensBlur = {
        ...settings.lensBlur,
        enabled: true,
        amount: 100,
        focus: 90,
        range: 5,
        mode: "background",
      };
      const result = applyLensBlur(data, width, height, settings, {
        values: depth,
        width,
        height,
      });
      let sharpError = 0,
        blurChange = 0;
      for (let y = 10; y < height - 10; y++)
        for (let x = 10; x < width - 10; x++) {
          const i = (y * width + x) * 4;
          if (x < 430)
            sharpError = Math.max(sharpError, Math.abs(result[i] - data[i]));
          if (x > 470) blurChange += Math.abs(result[i] - data[i]);
          if (result[i + 3] !== data[i + 3]) throw Error("Blur changed alpha");
        }
      const linearMid = result[(100 * width + 700) * 4];
      const circular = result.slice();
      settings.lensBlur.blades = 5;
      const polygon = applyLensBlur(data, width, height, settings, {
        values: depth,
        width,
        height,
      });
      let shapeDifference = 0;
      for (let i = 0; i < data.length; i += 4)
        shapeDifference += Math.abs(circular[i] - polygon[i]);
      return { sharpError, blurChange, linearMid, shapeDifference };
    });
    assert.equal(renderer.sharpError, 0);
    assert.ok(renderer.blurChange > 10000);
    assert.ok(
      renderer.linearMid > 145 && renderer.linearMid < 230,
      "Blur averages in linear light",
    );
    assert.ok(
      renderer.shapeDifference > 100,
      "Aperture shape changes the blur",
    );
    const photo = await page.evaluate(() => {
      const canvas = document.createElement("canvas");
      canvas.width = 800;
      canvas.height = 600;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#86c2e0";
      ctx.fillRect(0, 0, 800, 600);
      ctx.fillStyle = "#45633b";
      ctx.fillRect(0, 350, 800, 250);
      for (let y = 0; y < 600; y += 20)
        for (let x = 0; x < 800; x += 20) {
          ctx.fillStyle = (x + y) % 40 ? "#eeeeee" : "#273244";
          ctx.fillRect(x, y, 9, 9);
        }
      ctx.fillStyle = "#e6a36f";
      ctx.fillRect(300, 180, 180, 300);
      ctx.fillStyle = "#a95551";
      ctx.beginPath();
      ctx.arc(390, 150, 80, 0, Math.PI * 2);
      ctx.fill();
      return canvas.toDataURL().split(",")[1];
    });
    await page.locator("#target").setInputFiles({
      name: "lens-photo.png",
      mimeType: "image/png",
      buffer: Buffer.from(photo, "base64"),
    });
    await page.waitForFunction(
      () => document.querySelector("#preview").width === 800,
    );
    const baseline = await page
      .locator("#preview")
      .evaluate((c) => c.toDataURL());
    await page.locator("[data-panel=detail]").click();
    await page.locator("#lens-radial").click();
    await page.waitForFunction(
      () => document.querySelector("#mask-overlay").width === 800,
    );
    assert.equal(
      await page.locator("#mask-rotate").getAttribute("aria-pressed"),
      "false",
    );
    await page.locator("[data-panel=detail]").click();
    assert.equal(await page.locator("#lens-enabled").isChecked(), true);
    await page.waitForFunction(
      (before) => document.querySelector("#preview").toDataURL() !== before,
      baseline,
    );
    assert.equal(
      await page.locator("#lens-advanced").getAttribute("open"),
      null,
    );
    await page.locator("#lens-advanced summary").click();
    await page.locator("#lens-blades").selectOption("6");
    await page.locator("#lens-advanced summary").click();
    await page.waitForTimeout(250);
    const blurredPreview = await page
      .locator("#preview")
      .evaluate((c) =>
        Array.from(
          c.getContext("2d").getImageData(0, 0, c.width, c.height).data,
        ),
      );
    await page.locator("[data-panel=output]").click();
    await page.locator("#format").selectOption("image/png");
    const blurDownload = page.waitForEvent("download");
    await page.locator("#export").click();
    const savedBlur = await blurDownload;
    await savedBlur.saveAs(join(artifacts, "lens-export.png"));
    const exportedPixels = await page.evaluate(
      async (encoded) => {
        const bytes = Uint8Array.from(atob(encoded), (value) =>
          value.charCodeAt(0),
        );
        const image = await createImageBitmap(
          new Blob([bytes], { type: "image/png" }),
        );
        const canvas = document.createElement("canvas");
        canvas.width = image.width;
        canvas.height = image.height;
        const context = canvas.getContext("2d");
        context.drawImage(image, 0, 0);
        image.close();
        return Array.from(
          context.getImageData(0, 0, canvas.width, canvas.height).data,
        );
      },
      fs.readFileSync(join(artifacts, "lens-export.png")).toString("base64"),
    );
    assert.deepEqual(
      exportedPixels,
      blurredPreview,
      "Lens blur preview and same-resolution PNG export are identical",
    );
    await page.waitForFunction(
      () => !document.querySelector("#export-dialog").open,
    );
    await page.locator("[data-panel=detail]").click();
    await page.screenshot({
      path: join(artifacts, "desktop-radial-blur.png"),
      fullPage: true,
    });
    await page.locator("#lens-enabled").uncheck();
    await page.waitForFunction(
      (before) => document.querySelector("#preview").toDataURL() === before,
      baseline,
    );
    await page.locator("#adjustment-scope").selectOption("");
    await page.locator("[data-panel=crop]").click();
    await page.locator("#edit-expand").click();
    const cropBeforeExpand = await page.locator("#slider-crop-w").inputValue();
    await page.locator('[data-edge="e"]').focus();
    await page.keyboard.press("ArrowRight");
    await page.waitForFunction(
      () => document.querySelector("#preview").width === 816,
    );
    assert.equal(
      await page.locator("#slider-crop-w").inputValue(),
      cropBeforeExpand,
      "Expand handles do not mutate crop",
    );
    await page.locator("#reset-expand").click();
    const borderHandle = await page.locator('[data-edge="e"]').boundingBox();
    await page.mouse.move(
      borderHandle.x + borderHandle.width / 2,
      borderHandle.y + borderHandle.height / 2,
    );
    await page.mouse.down();
    await page.mouse.move(
      borderHandle.x + borderHandle.width / 2 + 25,
      borderHandle.y + borderHandle.height / 2,
      { steps: 4 },
    );
    await page.mouse.up();
    assert.ok(
      Number(await page.locator("#slider-expand-right").inputValue()) > 0,
      "Expand frame drags add borders",
    );
    assert.equal(
      await page.locator("#slider-crop-w").inputValue(),
      cropBeforeExpand,
    );
    await page.screenshot({
      path: join(artifacts, "expand-frame.png"),
      fullPage: true,
    });
    await page.locator("#reset-expand").click();
    await page.locator("#slider-expand-left").evaluate((input) => {
      input.value = "10";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await page.locator("[data-panel=output]").click();
    await page.waitForFunction(
      () =>
        document.querySelector("#preview").width === 960 &&
        document.querySelector("#preview").height === 720,
    );
    const borders = await page
      .locator("#preview")
      .evaluate((c) => [...c.getContext("2d").getImageData(0, 0, 1, 1).data]);
    assert.deepEqual(borders, [0, 0, 0, 255]);
    await page.locator("#format").selectOption("image/png");
    const downloaded = page.waitForEvent("download");
    await page.locator("#export").click();
    const download = await downloaded;
    await download.saveAs(join(artifacts, "expanded.png"));
    const png = fs.readFileSync(join(artifacts, "expanded.png"));
    assert.equal(png.readUInt32BE(16), 960);
    assert.equal(png.readUInt32BE(20), 720);
    await page.waitForFunction(
      () => !document.querySelector("#export-dialog").open,
    );
    await page.locator("#undo").click();
    await page.waitForFunction(
      () => document.querySelector("#preview").width === 800,
    );
    await page.locator("#redo").click();
    await page.waitForFunction(
      () => document.querySelector("#preview").width === 960,
    );
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 844 });
      await page.locator("[data-panel=detail]").click();
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      );
      await page.screenshot({
        path: join(artifacts, `mobile-lens-${width}.png`),
        fullPage: true,
      });
    }
    await page.setViewportSize({ width: 1440, height: 960 });
    if (process.env.LENS_TEST_PHOTO) {
      await page.locator("#target").setInputFiles(process.env.LENS_TEST_PHOTO);
      await page.waitForFunction(
        (name) =>
          document.querySelector("#file-info").textContent.includes(name),
        require("node:path").basename(process.env.LENS_TEST_PHOTO),
      );
    }
    await page.locator("[data-panel=detail]").click();
    await page.locator("#analyze-depth").click();
    await page
      .waitForFunction(
        () =>
          document
            .querySelector("#lens-status")
            .textContent.startsWith("Relative depth ready"),
        null,
        { timeout: 120000 },
      )
      .catch(async (error) => {
        console.error(
          "Depth status",
          await page.locator("#lens-status").innerText(),
        );
        throw error;
      });
    await page
      .locator("#depth-inspector")
      .evaluate((node) => (node.open = true));
    assert.equal(await page.locator("#lens-enabled").isChecked(), true);
    assert.equal(await page.locator("#slider-lens-focus").count(), 0);
    assert.equal(await page.locator("#slider-lens-range").count(), 0);
    const rangeBefore = await page.locator("#depth-range-value").innerText();
    await page.locator("#depth-preview").scrollIntoViewIfNeeded();
    const mapBounds = await page.locator("#depth-preview").boundingBox();
    await page.mouse.move(
      mapBounds.x + mapBounds.width * 0.5,
      mapBounds.y + mapBounds.height * 0.5,
    );
    await page.mouse.down();
    await page.mouse.move(
      mapBounds.x + mapBounds.width * 0.5,
      mapBounds.y + mapBounds.height * 0.9,
      { steps: 5 },
    );
    await page.mouse.up();
    assert.notEqual(
      await page.locator("#depth-range-value").innerText(),
      rangeBefore,
      "Dragging on the depth map changes the focus range",
    );
    const afterMapDrag = await page.locator("#depth-range-value").innerText();
    await page.locator("#depth-range-low").focus();
    await page.keyboard.press("ArrowLeft");
    assert.notEqual(
      await page.locator("#depth-range-value").innerText(),
      afterMapDrag,
    );
    await page.locator("#undo").click();
    assert.equal(
      await page.locator("#depth-range-value").innerText(),
      afterMapDrag,
      "Focus handle edits are undoable",
    );
    await page.locator("#lens-auto-focus").click();
    assert.equal(await page.locator("#depth-focus-handle").isVisible(), true);
    await page.locator("#depth-exact summary").click();
    const setRange = async () => {
      await page.locator("#depth-exact-low").fill("30.1");
      await page.locator("#depth-exact-low").press("Tab");
      await page.locator("#depth-exact-high").fill("70.2");
      await page.locator("#depth-exact-high").press("Tab");
    };
    await setRange();
    const exactRows = await page
      .locator(".depth-exact-values input")
      .evaluateAll((nodes) =>
        nodes.map((node) => node.getBoundingClientRect().top),
      );
    assert.equal(exactRows[0], exactRows[1], "Exact focus fields stay aligned");
    assert.equal(
      await page.locator("#depth-range-value").innerText(),
      "30.1 - 70.2",
    );
    const dragBoundary = async () => {
      await page.locator("#depth-range-low").scrollIntoViewIfNeeded();
      const box = await page.locator("#depth-range-low").boundingBox();
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.down();
      await page.mouse.move(
        box.x + box.width / 2 + 30,
        box.y + box.height / 2,
        { steps: 6 },
      );
      await page.mouse.up();
      return Number(await page.locator("#depth-exact-low").inputValue()) - 30.1;
    };
    const normalDelta = await dragBoundary();
    await setRange();
    await page.locator("#depth-fine").check();
    const fineDelta = await dragBoundary();
    assert.ok(
      normalDelta > 1 && Math.abs(fineDelta / normalDelta - 0.2) < 0.02,
      "Fine mode makes an equal drag five times more precise",
    );
    await page.screenshot({
      path: join(artifacts, "real-model-depth-blur.png"),
      fullPage: true,
    });
    const status = await page.locator("#lens-status").innerText();
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 844 });
      await page.evaluate(
        () =>
          new Promise((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(resolve)),
          ),
      );
      if (
        (await page.locator("#editor-layout").getAttribute("data-tray")) !==
        "open"
      )
        await page.locator("[data-panel=detail]").click();
      await page.locator("#depth-preview").scrollIntoViewIfNeeded();
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      );
      const point = await page.locator("#depth-preview").boundingBox();
      await page.touchscreen.tap(
        point.x + point.width * 0.5,
        point.y + point.height * 0.5,
      );
      const hitArea = await page
        .locator("#depth-focus-handle")
        .evaluate((node) => ({
          width: node.getBoundingClientRect().width,
          height: node.getBoundingClientRect().height,
        }));
      assert.ok(hitArea.width >= 44 && hitArea.height >= 44);
      assert.equal(await page.locator("#depth-focus-handle").isVisible(), true);
      await setRange();
      await page.locator("#depth-range-low").scrollIntoViewIfNeeded();
      const boundary = await page.locator("#depth-range-low").boundingBox();
      const touch = await page.context().newCDPSession(page);
      const x = boundary.x + boundary.width / 2,
        y = boundary.y + boundary.height / 2;
      await touch.send("Input.dispatchTouchEvent", {
        type: "touchStart",
        touchPoints: [{ x, y }],
      });
      await touch.send("Input.dispatchTouchEvent", {
        type: "touchMove",
        touchPoints: [{ x: x + 30, y }],
      });
      await touch.send("Input.dispatchTouchEvent", {
        type: "touchEnd",
        touchPoints: [],
      });
      const touchedLow = Number(
        await page.locator("#depth-exact-low").inputValue(),
      );
      assert.ok(
        touchedLow > 30.1 && touchedLow < 35,
        "Phone touch drags use fine sensitivity without page scrolling",
      );
      await touch.detach();
      await page.locator("#undo").click();
      assert.equal(
        await page.locator("#depth-range-value").innerText(),
        "30.1 - 70.2",
      );
      await page.locator("#depth-range-track").scrollIntoViewIfNeeded();
      await page.screenshot({
        path: join(artifacts, `mobile-focus-map-${width}.png`),
        fullPage: true,
      });
    }
    await page.locator("#lens-enabled").uncheck();
    assert.deepEqual(errors, []);
    assert.ok(requests.every((request) => request.method === "GET"));
    const failed = await browser.newPage();
    await failed.route("**/assets/models/depth-anything-v2-small/**", (route) =>
      route.fulfill({ status: 503, body: "Unavailable" }),
    );
    await failed.goto(url);
    await failed.locator("#target").setInputFiles({
      name: "fallback.png",
      mimeType: "image/png",
      buffer: Buffer.from(photo, "base64"),
    });
    await failed.locator("[data-panel=detail]").click();
    await failed.locator("#analyze-depth").click();
    await failed.waitForFunction(() =>
      document
        .querySelector("#lens-status")
        .textContent.includes("unavailable"),
    );
    assert.equal(await failed.locator("#lens-enabled").isChecked(), false);
    assert.equal(await failed.locator("#export").isEnabled(), true);
    await failed.close();
    console.log(
      JSON.stringify({ renderer, status, artifacts, passed: true }, null, 2),
    );
  } finally {
    await browser?.close();
    server.kill();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
