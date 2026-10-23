import assert from "node:assert/strict";
import test from "node:test";
import { classifyPhoto } from "../web/src/photo-decoder.js";

test("classifies browser-native photo formats by MIME type", () => {
  assert.equal(classifyPhoto({ name: "photo", type: "image/jpeg" }), "browser");
  assert.equal(classifyPhoto({ name: "photo", type: "image/png" }), "browser");
  assert.equal(classifyPhoto({ name: "photo", type: "image/webp" }), "browser");
  assert.equal(classifyPhoto({ name: "photo.JPG", type: "" }), "browser");
});

test("classifies iPhone HEIC even when the browser omits its MIME type", () => {
  assert.equal(classifyPhoto({ name: "IMG_1001.HEIC", type: "" }), "heic");
  assert.equal(
    classifyPhoto({ name: "photo.heif", type: "image/heif" }),
    "heic",
  );
});

test("classifies representative camera RAW extensions", () => {
  for (const name of [
    "iphone-proraw.DNG",
    "canon.CR3",
    "nikon.nef",
    "sony.arw",
    "fuji.raf",
  ])
    assert.equal(classifyPhoto({ name, type: "" }), "raw");
});

test("does not infer support for unrelated files", () => {
  assert.equal(
    classifyPhoto({ name: "photo.bmp", type: "image/bmp" }),
    "unsupported",
  );
});
