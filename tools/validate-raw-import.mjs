import { resolve } from "node:path";
import { chromium } from "playwright";

const file = process.argv[2];
const shouldExport = process.argv.includes("--export");
const editorUrl = process.env.COLORCHECK_URL ?? "http://127.0.0.1:8012/";
if (!file) {
  throw new Error(
    "Usage: node tools/validate-raw-import.mjs /path/to/photo.raw",
  );
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error") errors.push(message.text());
});

try {
  await page.goto(editorUrl);
  await page.locator("#target").setInputFiles(resolve(file));

  const deadline = Date.now() + 120_000;
  let status = "";
  while (Date.now() < deadline) {
    status = await page.locator("#status").innerText();
    console.log(status);
    if (
      status.startsWith("Ready") ||
      /failed|could not|supports photos/.test(status)
    )
      break;
    await page.waitForTimeout(2_000);
  }

  const previewSample = () =>
    page.locator("#preview").evaluate((canvas) => {
      const data = canvas
        .getContext("2d")
        .getImageData(0, 0, canvas.width, canvas.height).data;
      let total = 0;
      for (let index = 0; index < data.length; index += 1600)
        total += data[index];
      return total;
    });
  const beforeAdjustment = await previewSample();
  await page.locator("[data-panel=light]").click();
  await page.locator("#slider-exposure").fill("0.5");
  await page.waitForTimeout(1_000);
  const afterAdjustment = await previewSample();
  await page.screenshot({ path: "/tmp/colorcheck-raw-import.png" });

  let exportedFile = null;
  if (shouldExport && status.startsWith("Ready")) {
    const download = page.waitForEvent("download", { timeout: 120_000 });
    await page.locator("#export").click();
    const result = await download;
    exportedFile = `/tmp/${result.suggestedFilename()}`;
    await result.saveAs(exportedFile);
  }

  console.log(
    JSON.stringify(
      {
        status,
        file: await page.locator("#file-info").innerText(),
        preview: await page.locator("#preview").evaluate((canvas) => ({
          width: canvas.width,
          height: canvas.height,
          hidden: canvas.hidden,
        })),
        exposureChangedPreview: beforeAdjustment !== afterAdjustment,
        exportedFile,
        errors,
      },
      null,
      2,
    ),
  );
} finally {
  await browser.close();
}
