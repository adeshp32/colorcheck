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
