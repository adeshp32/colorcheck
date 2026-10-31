/** Display-only histogram of the pixels the editor is currently showing. */
export function histogramFromRgba(pixels) {
  const bins = {
    luminance: new Uint32Array(64),
    red: new Uint32Array(64),
    green: new Uint32Array(64),
    blue: new Uint32Array(64),
  };
  for (let i = 0; i < pixels.length; i += 4) {
    if (pixels[i + 3] < 128) continue;
    const red = pixels[i],
      green = pixels[i + 1],
      blue = pixels[i + 2];
    const luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue;
    for (const [name, value] of [
      ["luminance", luminance],
      ["red", red],
      ["green", green],
      ["blue", blue],
    ])
      bins[name][Math.min(63, Math.floor(value / 4))]++;
  }
  return bins;
}
