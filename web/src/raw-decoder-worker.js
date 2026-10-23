import { LibRaw } from "../vendor/libraw/libraw.js";

function rgbaPixels(image) {
  if (image.type_ !== "LIBRAW_IMAGE_BITMAP" || image.bits !== 8)
    throw new Error("LibRaw returned an unsupported processed image.");
  if (image.colors !== 3 && image.colors !== 4)
    throw new Error("LibRaw returned an unsupported channel layout.");

  const pixels = new Uint8ClampedArray(image.width * image.height * 4);
  for (let source = 0, target = 0; target < pixels.length; target += 4) {
    pixels[target] = image.data[source++];
    pixels[target + 1] = image.data[source++];
    pixels[target + 2] = image.data[source++];
    pixels[target + 3] = image.colors === 4 ? image.data[source++] : 255;
  }
  return pixels;
}

self.onmessage = async ({ data }) => {
  let decoder;
  try {
    await LibRaw.initialize();
    decoder = new LibRaw();
    await decoder.waitUntilReady();
    decoder.open(data.buffer);

    // Produce a neutral, camera-aware sRGB starting point for the editor.
    decoder.setUseCameraWb(1);
    decoder.setOutputColor(1);
    decoder.setOutputBps(8);
    decoder.setDemosaic(3);
    decoder.setHighlight(1);
    decoder.unpack();
    decoder.dcrawProcess();

    const image = decoder.dcrawMakeMemImage();
    const pixels = rgbaPixels(image);
    self.postMessage(
      { width: image.width, height: image.height, pixels: pixels.buffer },
      [pixels.buffer],
    );
  } catch (error) {
    self.postMessage({
      error:
        error instanceof Error
          ? `RAW decoding failed: ${error.message}`
          : "RAW decoding failed for this camera file.",
    });
  } finally {
    decoder?.dispose();
  }
};
