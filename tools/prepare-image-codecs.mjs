import { copyFile, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const vendor = join(root, "web", "vendor");
const heicSource = join(root, "node_modules", "heic-to");
const rawSource = join(root, "node_modules", "@colorhythm", "libraw-wasm");
const heicOutput = join(vendor, "heic");
const rawOutput = join(vendor, "libraw");

await Promise.all([
  mkdir(heicOutput, { recursive: true }),
  mkdir(rawOutput, { recursive: true }),
]);

await Promise.all([
  copyFile(
    join(heicSource, "dist", "csp", "heic-to.js"),
    join(heicOutput, "heic-to.js"),
  ),
  copyFile(join(heicSource, "LICENSE"), join(heicOutput, "LICENSE.txt")),
  copyFile(
    join(rawSource, "dist", "libraw.wasm"),
    join(rawOutput, "libraw.wasm"),
  ),
  copyFile(join(rawSource, "LICENSE"), join(rawOutput, "LICENSE-wrapper.txt")),
  copyFile(
    join(rawSource, "LibRaw", "LICENSE.LGPL"),
    join(rawOutput, "LICENSE-libraw-lgpl.txt"),
  ),
  copyFile(
    join(rawSource, "LibRaw", "LICENSE.CDDL"),
    join(rawOutput, "LICENSE-libraw-cddl.txt"),
  ),
  copyFile(
    join(rawSource, "LibRaw", "COPYRIGHT"),
    join(rawOutput, "COPYRIGHT-libraw.txt"),
  ),
]);

await build({
  entryPoints: [join(rawSource, "dist", "index.js")],
  bundle: true,
  format: "esm",
  platform: "browser",
  external: ["module", "node:module", "fs", "path", "url"],
  target: ["es2022"],
  outfile: join(rawOutput, "libraw.js"),
});

console.log("Prepared lazy, on-device HEIC and RAW codecs in web/vendor.");
