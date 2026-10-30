const { chromium } = require("playwright");
const { spawn } = require("node:child_process");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { join } = require("node:path");
const { tmpdir } = require("node:os");

(async () => {
  const artifacts = fs.mkdtempSync(join(tmpdir(), "colorcheck-match-"));
  const server = spawn(process.execPath, ["tools/serve.mjs"], {
    env: { ...process.env, PORT: "0" },
    stdio: ["ignore", "pipe", "inherit"],
  });
  let browser;
  try {
    const url = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(Error("Server timeout")), 10000);
      server.stdout.on("data", (data) => {
        const match = String(data).match(/http:\/\/127\.0\.0\.1:\d+\//);
        if (match) {
          clearTimeout(timer);
          resolve(match[0]);
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
    page.on("request", (request) => requests.push(request.method()));
    await page.addInitScript(() => {
      const NativeWorker = window.Worker;
      window.Worker = class extends NativeWorker {
        constructor(...args) {
          super(...args);
          this.addEventListener("message", (event) => {
            if (event.data.match) window.__matched = event.data.match;
          });
        }
      };
    });
    await page.goto(url);
    const fixtures = await page.evaluate(() => {
      function image(reference) {
        const canvas = document.createElement("canvas");
        canvas.width = 192;
        canvas.height = 128;
        const ctx = canvas.getContext("2d"),
          image = ctx.createImageData(192, 128);
        for (let y = 0; y < 128; y++)
          for (let x = 0; x < 192; x++) {
            const i = (y * 192 + x) * 4;
            const rgb = y < 24 ? [x, x, x] : [30 + x, 30 + y, 180 - x / 2];
            image.data[i] = Math.min(255, rgb[0] + (reference ? 45 : 0));
            image.data[i + 1] = Math.max(0, rgb[1] - (reference ? 10 : 0));
            image.data[i + 2] = Math.max(0, rgb[2] - (reference ? 40 : 0));
            image.data[i + 3] = 255;
          }
        ctx.putImageData(image, 0, 0);
        return {
          png: canvas.toDataURL().split(",")[1],
          pixels: Array.from(image.data),
        };
      }
      return { source: image(false), reference: image(true) };
    });
    await page.locator("#target").setInputFiles({
      name: "source.png",
      mimeType: "image/png",
      buffer: Buffer.from(fixtures.source.png, "base64"),
    });
    await page.waitForFunction(
      () => document.querySelector("#preview").width === 192,
    );
    await page.locator("#reference").setInputFiles({
      name: "reference.png",
      mimeType: "image/png",
      buffer: Buffer.from(fixtures.reference.png, "base64"),
    });
    await page.locator("#match").click();
    await page.waitForFunction(
      () => window.__matched?.perceptual?.version === 1,
    );
    await page.waitForFunction(
      () =>
        document.querySelector("#match").getAttribute("aria-busy") === "false",
    );
    const setStrength = async (id, value) =>
      page.locator(`#slider-${id}`).evaluate((node, value) => {
        node.value = String(value);
        node.dispatchEvent(new Event("input", { bubbles: true }));
        node.dispatchEvent(new Event("change", { bubbles: true }));
      }, value);
    const comparisons = [];
    for (const width of [1440, 320, 390]) {
      await page.setViewportSize({ width, height: 960 });
      await setStrength("matchTone", 0);
      await setStrength("matchColor", 100);
      await setStrength("matchDistributionStrength", 30);
      const expected = await page.evaluate(async ({ source, reference }) => {
        const {
          calculatePerceptualReferenceMatch,
          applyPhotoAdjustments,
          createDefaultEditSettings,
        } = await import("./src/image-processing.js");
        const edits = createDefaultEditSettings();
        Object.assign(edits, {
          match: calculatePerceptualReferenceMatch(
            new Uint8ClampedArray(source.pixels),
            new Uint8ClampedArray(reference.pixels),
          ),
          matchColor: 100,
          matchTone: 0,
          matchDistributionStrength: 30,
        });
        return Array.from(
          applyPhotoAdjustments(
            new Uint8ClampedArray(source.pixels),
            192,
            128,
            edits,
          ).data,
        );
      }, fixtures);
      await page.waitForFunction(
        (expected) => {
          const c = document.querySelector("#preview"),
            actual = c.getContext("2d").getImageData(0, 0, 192, 128).data;
          return actual.every((v, i) => Math.abs(v - expected[i]) <= 1);
        },
        expected,
        { timeout: 15000 },
      );
      comparisons.push(
        await page.evaluate((expected) => {
          const c = document.querySelector("#preview"),
            actual = c.getContext("2d").getImageData(0, 0, 192, 128).data;
          return {
            width: innerWidth,
            maximumPixelError: Math.max(
              ...actual.map((v, i) => Math.abs(v - expected[i])),
            ),
            noOverflow: document.documentElement.scrollWidth <= innerWidth,
          };
        }, expected),
      );
      const before = await page
        .locator("#preview")
        .evaluate((c) => c.toDataURL());
      await setStrength("matchColor", 50);
      await page.waitForFunction(
        (before) => document.querySelector("#preview").toDataURL() !== before,
        before,
      );
      await page.locator("#undo").click();
      await page.waitForFunction(
        (before) => document.querySelector("#preview").toDataURL() === before,
        before,
      );
      await page.locator("#redo").click();
      assert.equal(await page.locator("#slider-matchColor").inputValue(), "50");
      await page.screenshot({
        path: join(artifacts, `matcher-${width}.png`),
        fullPage: true,
      });
    }
    assert.ok(comparisons.every((result) => result.noOverflow));
    assert.deepEqual(errors, []);
    assert.ok(requests.every((method) => method === "GET"));
    console.log(
      JSON.stringify({ passed: true, comparisons, artifacts }, null, 2),
    );
  } finally {
    await browser?.close();
    server.kill();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
