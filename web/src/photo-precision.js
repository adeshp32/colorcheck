/** Report encoded sample precision only when a supported header states it explicitly. */
export function precisionFromHeader(bytes) {
  const b = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  if (
    b.length >= 29 &&
    [137, 80, 78, 71, 13, 10, 26, 10].every((v, i) => b[i] === v) &&
    String.fromCharCode(...b.subarray(12, 16)) === "IHDR"
  ) {
    const bits = b[24],
      color = b[25];
    const allowed = {
      0: [1, 2, 4, 8, 16],
      2: [8, 16],
      3: [1, 2, 4, 8],
      4: [8, 16],
      6: [8, 16],
    };
    if (allowed[color]?.includes(bits))
      return {
        bits,
        kind: color === 3 ? "palette-index" : "sample",
        format: "PNG",
      };
  }
  if (b[0] === 255 && b[1] === 216) {
    let i = 2;
    while (i + 4 < b.length) {
      if (b[i++] !== 255) break;
      while (b[i] === 255) i++;
      const marker = b[i++];
      if (marker === 218 || marker === 217) break;
      if (marker === 1 || (marker >= 208 && marker <= 215)) continue;
      const length = b[i] * 256 + b[i + 1];
      if (length < 2 || i + length > b.length) break;
      if (
        [
          192, 193, 194, 195, 197, 198, 199, 201, 202, 203, 205, 206, 207,
        ].includes(marker)
      )
        return { bits: b[i + 2], kind: "sample", format: "JPEG" };
      i += length;
    }
  }
  return { bits: null, kind: "unknown", format: null };
}
export async function inspectPhotoPrecision(file) {
  return precisionFromHeader(await file.slice(0, 262144).arrayBuffer());
}
