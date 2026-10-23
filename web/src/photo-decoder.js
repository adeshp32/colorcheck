const BROWSER_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const BROWSER_IMAGE_EXTENSIONS = new Set(["jpeg", "jpg", "png", "webp"]);
const HEIC_TYPES = new Set([
  "image/heic",
  "image/heif",
  "image/heic-sequence",
  "image/heif-sequence",
]);
const RAW_EXTENSIONS = new Set([
  "3fr",
  "arw",
  "cr2",
  "cr3",
  "crw",
  "dcr",
  "dng",
  "erf",
  "iiq",
  "k25",
  "kdc",
  "mef",
  "mos",
  "mrw",
  "nef",
  "nrw",
  "orf",
  "pef",
  "raf",
  "raw",
  "rw2",
  "sr2",
  "srf",
  "srw",
  "x3f",
]);

const extensionOf = (file) => file?.name?.split(".").pop()?.toLowerCase() ?? "";

export function classifyPhoto(file) {
  const extension = extensionOf(file);
  if (
    BROWSER_IMAGE_TYPES.has(file?.type) ||
    BROWSER_IMAGE_EXTENSIONS.has(extension)
  )
    return "browser";
  if (
    HEIC_TYPES.has(file?.type) ||
    extension === "heic" ||
    extension === "heif"
  )
    return "heic";
  if (RAW_EXTENSIONS.has(extension)) return "raw";
  return "unsupported";
}

async function decodeHeic(file) {
  try {
    return await createImageBitmap(file, { colorSpaceConversion: "default" });
  } catch {
    const { heicTo, isHeic } = await import("../vendor/heic/heic-to.js");
    if (!(await isHeic(file))) throw new Error("This HEIC file is not valid.");
    return heicTo({
      blob: file,
      type: "bitmap",
      options: { colorSpaceConversion: "default" },
    });
  }
}

function decodeRaw(file) {
  return new Promise((resolve, reject) => {
    const worker = new Worker(
      new URL("./raw-decoder-worker.js", import.meta.url),
      {
        type: "module",
      },
    );
    const finish = (callback, value) => {
      worker.terminate();
      callback(value);
    };
    worker.onerror = () =>
      finish(
        reject,
        new Error("RAW decoding could not start in this browser."),
      );
    worker.onmessage = async ({ data }) => {
      if (data.error) {
        finish(reject, new Error(data.error));
        return;
      }
      try {
        const pixels = new ImageData(
          new Uint8ClampedArray(data.pixels),
          data.width,
          data.height,
        );
        finish(resolve, await createImageBitmap(pixels));
      } catch {
        finish(
          reject,
          new Error("The developed RAW image could not be opened."),
        );
      }
    };
    file
      .arrayBuffer()
      .then((buffer) => worker.postMessage({ buffer }, [buffer]))
      .catch(() =>
        finish(reject, new Error("The RAW file could not be read.")),
      );
  });
}

export async function decodePhotoFile(file) {
  if (!file) throw new Error("Choose a photo to continue.");
  const format = classifyPhoto(file);
  if (format === "unsupported")
    throw new Error(
      "Choose a JPEG, PNG, WebP, HEIC, HEIF, or supported camera RAW photo.",
    );
  const fileLimit = format === "raw" ? 120_000_000 : 50_000_000;
  if (file.size > fileLimit)
    throw new Error(
      `Choose a ${format === "raw" ? "RAW photo below 120 MB" : "photo below 50 MB"}.`,
    );

  let bitmap;
  try {
    if (format === "browser") {
      bitmap = await createImageBitmap(file, {
        colorSpaceConversion: "default",
      });
    } else if (format === "heic") {
      bitmap = await decodeHeic(file);
    } else {
      bitmap = await decodeRaw(file);
    }
  } catch (error) {
    if (error instanceof Error && error.message) throw error;
    throw new Error(`This ${format.toUpperCase()} photo could not be decoded.`);
  }

  if (bitmap.width * bitmap.height > 50_000_000) {
    bitmap.close();
    throw new Error("This version supports photos up to 50 megapixels.");
  }
  return bitmap;
}
