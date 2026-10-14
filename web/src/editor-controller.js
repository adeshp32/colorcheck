import {
  createDefaultEditSettings,
  calculateChannelStatistics,
  calculateReferenceMatch,
  applyToneCurve,
  clamp,
} from "./image-processing.js";
import { createEditHistory } from "./edit-history.js";
/** UI orchestration: original bitmaps stay separate from non-destructive settings. */
const $ = (s) => document.querySelector(s),
  clone = (v) => structuredClone(v);
let edits = createDefaultEditSettings(),
  source = null,
  reference = null,
  previewPixels = null,
  referenceStats = null,
  range = "global",
  panel = "match",
  original = false,
  revision = 0,
  requestId = 0,
  exporting = false;
const editHistory = createEditHistory(edits);
let worker,
  requests = new Map(),
  rendering = false,
  rerender = false;
const preview = $("#preview"),
  controls = new Map();
function showStatus(message) {
  $("#status").textContent = message;
}
function createProcessingWorker() {
  worker = new Worker(new URL("./render-worker.js", import.meta.url), {
    type: "module",
  });
  worker.onmessage = ({ data: m }) => {
    const p = requests.get(m.id);
    if (!p) return;
    requests.delete(m.id);
    m.error ? p.reject(new Error(m.error)) : p.resolve(m);
  };
  worker.onerror = () => {
    for (const p of requests.values())
      p.reject(
        new Error("Photo processing could not finish. Try a smaller image."),
      );
    requests.clear();
  };
}
createProcessingWorker();
function renderInWorker(pixels, width, height, settings) {
  return new Promise((resolve, reject) => {
    const id = ++requestId;
    requests.set(id, { resolve, reject });
    worker.postMessage(
      { id, pixels: pixels.buffer, width, height, edits: settings },
      [pixels.buffer],
    );
  });
}
function commitEditHistory() {
  if (editHistory.commit(edits)) synchronizeControls();
}
function applyEdit(fn) {
  fn();
  commitEditHistory();
  renderPreview();
}
function createAdjustmentControl(
  container,
  key,
  label,
  min,
  max,
  step = 1,
  value = 0,
  tip = "",
) {
  const row = document.createElement("div");
  row.className = "control";
  const top = document.createElement("div");
  top.className = "control-top";
  const name = document.createElement("label");
  name.textContent = label;
  name.htmlFor = `slider-${key}`;
  if (tip) name.title = tip;
  const number = document.createElement("input");
  number.type = "number";
  number.min = min;
  number.max = max;
  number.step = step;
  number.value = value;
  number.setAttribute("aria-label", `${label} value`);
  const reset = document.createElement("button");
  reset.textContent = "↺";
  reset.title = `Reset ${label}`;
  reset.setAttribute("aria-label", reset.title);
  const slider = document.createElement("input");
  slider.id = `slider-${key}`;
  slider.type = "range";
  slider.min = min;
  slider.max = max;
  slider.step = step;
  slider.value = value;
  top.append(name, number, reset);
  row.append(top, slider);
  $(container).append(row);
  const get = () =>
    key.startsWith("grade-")
      ? edits.grades[range][key.slice(6)]
      : key.startsWith("crop-")
        ? edits.crop[key.slice(5)]
        : key === "quality"
          ? quality
          : edits[key];
  const set = (v) => {
    v = clamp(v, min, max);
    if (key.startsWith("grade-")) edits.grades[range][key.slice(6)] = v;
    else if (key.startsWith("crop-")) {
      edits.crop[key.slice(5)] = v;
      boundCrop();
    } else if (key === "quality") quality = v;
    else edits[key] = v;
    slider.value = get();
    number.value = get();
    renderPreview();
  };
  slider.addEventListener("input", () => set(Number(slider.value)));
  number.addEventListener("input", () => {
    if (number.value !== "" && Number.isFinite(number.valueAsNumber))
      set(number.valueAsNumber);
  });
  for (const input of [slider, number])
    input.addEventListener("change", () => {
      set(Number(input.value) || 0);
      commitEditHistory();
    });
  reset.onclick = () => {
    set(value);
    commitEditHistory();
  };
  controls.set(key, { slider, number, get });
}
let quality = 95;
createAdjustmentControl(
  "#match-controls",
  "matchColor",
  "Palette strength",
  0,
  100,
);
createAdjustmentControl(
  "#match-controls",
  "matchTone",
  "Tone strength",
  0,
  100,
);
for (const [key, label, min, max, step, tip] of [
  [
    "exposure",
    "Exposure (EV)",
    -3,
    3,
    0.05,
    "One EV doubles or halves brightness.",
  ],
  ["contrast", "Contrast", -100, 100, 1],
  ["highlights", "Highlights", -100, 100, 1],
  ["shadows", "Shadows", -100, 100, 1],
  ["whites", "Whites", -100, 100, 1],
  ["blacks", "Blacks", -100, 100, 1],
])
  createAdjustmentControl(
    "#light-controls",
    key,
    label,
    min,
    max,
    step,
    0,
    tip,
  );
for (const [key, label] of [
  ["temperature", "Warmth"],
  ["tint", "Tint"],
  ["saturation", "Saturation"],
  ["vibrance", "Vibrance"],
])
  createAdjustmentControl("#color-controls", key, label, -100, 100);
createAdjustmentControl(
  "#grade-controls",
  "grade-hue",
  "Hue (degrees)",
  0,
  359,
  1,
);
createAdjustmentControl(
  "#grade-controls",
  "grade-saturation",
  "Color saturation",
  0,
  100,
);
createAdjustmentControl(
  "#grade-controls",
  "grade-amount",
  "Range strength",
  0,
  100,
  1,
  20,
);
createAdjustmentControl("#detail-controls", "sharpen", "Sharpen", 0, 100);
createAdjustmentControl("#detail-controls", "vignette", "Vignette", 0, 100);
for (const [key, label, def] of [
  ["x", "Left (%)", 0],
  ["y", "Top (%)", 0],
  ["w", "Width (%)", 100],
  ["h", "Height (%)", 100],
])
  createAdjustmentControl(
    "#crop-controls",
    `crop-${key}`,
    label,
    key === "w" || key === "h" ? 1 : 0,
    100,
    0.1,
    def,
  );
createAdjustmentControl(
  "#output-controls",
  "quality",
  "Quality (%)",
  60,
  100,
  1,
  95,
);
function boundCrop() {
  const c = edits.crop;
  c.w = clamp(c.w, 1, 100);
  c.h = clamp(c.h, 1, 100);
  c.x = clamp(c.x, 0, 100 - c.w);
  c.y = clamp(c.y, 0, 100 - c.h);
}
function synchronizeControls() {
  for (const control of controls.values()) {
    control.slider.value = control.get();
    control.number.value = Number(control.get()).toFixed(
      Number(control.slider.step) < 1 ? 2 : 0,
    );
  }
  $("#bw").checked = edits.bw;
  $("#curve").value = edits.curve;
  $("#undo").disabled = !editHistory.canUndo;
  $("#redo").disabled = !editHistory.canRedo;
  $("#match").disabled = !source || !referenceStats;
  for (const id of ["export", "compare", "reset"])
    $(`#${id}`).disabled = !source;
  $("#output-size").textContent = source
    ? `${outputDimensions().join(" × ")} pixels · original resolution`
    : "No photo selected";
  drawWheel();
  drawCurve();
  positionCrop();
}
async function decodePhoto(file) {
  if (!file || !["image/jpeg", "image/png", "image/webp"].includes(file.type))
    throw new Error(
      "Choose a JPEG, PNG, or WebP photo. HEIC and RAW are not supported yet.",
    );
  if (file.size > 50_000_000) throw new Error("Choose a photo below 50 MB.");
  const bitmap = await createImageBitmap(file, {
    colorSpaceConversion: "default",
  });
  if (bitmap.width * bitmap.height > 24_000_000) {
    bitmap.close();
    throw new Error("This first version supports photos up to 24 megapixels.");
  }
  return bitmap;
}
function createPreviewPixels(bitmap, max = 1200) {
  const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height)),
    canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return context.getImageData(0, 0, canvas.width, canvas.height);
}
let sourceLoad = 0,
  referenceLoad = 0;
async function openTargetPhoto(file) {
  const ticket = ++sourceLoad;
  try {
    showStatus("Opening photo…");
    const bitmap = await decodePhoto(file);
    if (ticket !== sourceLoad) {
      bitmap.close();
      return;
    }
    const pixels = createPreviewPixels(bitmap);
    source?.bitmap.close();
    source = {
      bitmap,
      name: file.name,
      width: bitmap.width,
      height: bitmap.height,
      stats: calculateChannelStatistics(pixels.data),
    };
    previewPixels = pixels;
    edits = createDefaultEditSettings();
    editHistory.reset(edits);
    $("#empty").hidden = true;
    preview.hidden = false;
    $("#file-info").textContent =
      `${file.name} · ${bitmap.width} × ${bitmap.height}`;
    $("#file-info").title = file.name;
    original = false;
    $("#compare").textContent = "Original";
    synchronizeControls();
    renderPreview();
    showStatus("Ready. Photos stay on this device.");
  } catch (error) {
    showStatus(error.message);
  }
}
for (const id of ["target", "start-file"])
  $(`#${id}`).onchange = (e) => {
    openTargetPhoto(e.target.files[0]);
    e.target.value = "";
  };
$("#reference").onchange = async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  const ticket = ++referenceLoad;
  try {
    const bitmap = await decodePhoto(file);
    if (ticket !== referenceLoad) {
      bitmap.close();
      return;
    }
    const pixels = createPreviewPixels(bitmap, 500);
    referenceStats = calculateChannelStatistics(pixels.data);
    reference?.close();
    reference = bitmap;
    const canvas = document.createElement("canvas");
    canvas.width = pixels.width;
    canvas.height = pixels.height;
    canvas.getContext("2d").putImageData(pixels, 0, 0);
    const image = document.createElement("img");
    image.src = canvas.toDataURL();
    image.alt = `Reference: ${file.name}`;
    $("#reference-preview").replaceChildren(image);
    if (edits.match)
      applyEdit(() => {
        edits.match = null;
        edits.matchColor = 0;
        edits.matchTone = 0;
      });
    synchronizeControls();
    showStatus("Reference ready.");
  } catch (error) {
    showStatus(error.message);
  }
};
$("#match").onclick = () => {
  if (!source || !referenceStats) return;
  applyEdit(() => {
    edits.match = calculateReferenceMatch(source.stats, referenceStats);
    edits.matchColor = 65;
    edits.matchTone = 45;
  });
  showStatus("Reference applied. Adjust palette and tone independently.");
};
function getRotatedDimensions(width, height, settings = edits) {
  const rotated = settings.rotation % 180 !== 0;
  return { width: rotated ? height : width, height: rotated ? width : height };
}
function outputDimensions() {
  const g = getRotatedDimensions(source.width, source.height);
  return [
    Math.max(1, Math.round((g.width * edits.crop.w) / 100)),
    Math.max(1, Math.round((g.height * edits.crop.h) / 100)),
  ];
}
function drawTransformedPhoto(
  destination,
  image,
  width,
  height,
  settings,
  crop = true,
) {
  const g = getRotatedDimensions(width, height, settings),
    c = crop ? settings.crop : { x: 0, y: 0, w: 100, h: 100 };
  destination.width = Math.max(1, Math.round((g.width * c.w) / 100));
  destination.height = Math.max(1, Math.round((g.height * c.h) / 100));
  const context = destination.getContext("2d");
  context.save();
  context.translate((-g.width * c.x) / 100, (-g.height * c.y) / 100);
  context.translate(g.width / 2, g.height / 2);
  context.rotate((settings.rotation * Math.PI) / 180);
  context.scale(settings.flip ? -1 : 1, 1);
  context.drawImage(image, -width / 2, -height / 2, width, height);
  context.restore();
}
function drawHistogram(bins) {
  const canvas = $("#histogram"),
    c = canvas.getContext("2d");
  c.clearRect(0, 0, canvas.width, canvas.height);
  const max = Math.max(...bins, 1);
  c.fillStyle = "#7777dc";
  for (let i = 0; i < 64; i++)
    c.fillRect(i * 4, 72 - (68 * bins[i]) / max, 3, (68 * bins[i]) / max);
}
function drawCurve() {
  const canvas = $("#curve-preview"),
    c = canvas.getContext("2d");
  c.clearRect(0, 0, 256, 100);
  c.strokeStyle = "#c4c6d3";
  c.lineWidth = 1;
  c.beginPath();
  c.moveTo(0, 100);
  c.lineTo(256, 0);
  c.stroke();
  c.strokeStyle = "#7474ed";
  c.lineWidth = 2;
  c.beginPath();
  for (let x = 0; x <= 256; x++) {
    const y = 100 - 100 * applyToneCurve(x / 256, edits.curve);
    x ? c.lineTo(x, y) : c.moveTo(x, y);
  }
  c.stroke();
}
async function renderPreview() {
  revision++;
  synchronizeControls();
  if (!source) return;
  if (rendering) {
    rerender = true;
    return;
  }
  rendering = true;
  const version = revision,
    settings = clone(edits),
    base = previewPixels;
  try {
    const result = original
      ? { data: base.data }
      : await renderInWorker(
          base.data.slice(),
          base.width,
          base.height,
          settings,
        );
    if (version !== revision) {
      rerender = true;
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = base.width;
    canvas.height = base.height;
    canvas
      .getContext("2d")
      .putImageData(new ImageData(result.data, base.width, base.height), 0, 0);
    drawTransformedPhoto(
      preview,
      canvas,
      base.width,
      base.height,
      settings,
      panel !== "crop",
    );
    if (result.histogram) drawHistogram(result.histogram);
    positionCrop();
  } catch (error) {
    showStatus(error.message);
  } finally {
    rendering = false;
    if (rerender) {
      rerender = false;
      renderPreview();
    }
  }
}
$("#undo").onclick = () => {
  const settings = editHistory.undo();
  if (settings) {
    edits = settings;
    renderPreview();
  }
};
$("#redo").onclick = () => {
  const settings = editHistory.redo();
  if (settings) {
    edits = settings;
    renderPreview();
  }
};
$("#reset").onclick = () =>
  applyEdit(() => {
    edits = createDefaultEditSettings();
    $("#ratio").value = "free";
  });
$("#compare").onclick = () => {
  original = !original;
  $("#compare").textContent = original ? "Edited" : "Original";
  $("#compare").setAttribute("aria-pressed", String(original));
  renderPreview();
};
$("#bw").onchange = (e) =>
  applyEdit(() => {
    edits.bw = e.target.checked;
  });
$("#curve").onchange = (e) =>
  applyEdit(() => {
    edits.curve = e.target.value;
  });
for (const button of document.querySelectorAll("[data-panel]"))
  button.onclick = () => {
    panel = button.dataset.panel;
    for (const b of document.querySelectorAll("[data-panel]"))
      b.setAttribute("aria-selected", String(b === button));
    for (const section of document.querySelectorAll("[data-section]"))
      section.hidden = section.dataset.section !== panel;
    renderPreview();
  };
for (const button of document.querySelectorAll("[data-range]"))
  button.onclick = () => {
    range = button.dataset.range;
    for (const b of document.querySelectorAll("[data-range]"))
      b.setAttribute("aria-pressed", String(b === button));
    synchronizeControls();
  };
$("#reset-grade").onclick = () =>
  applyEdit(() => {
    edits.grades[range] = { hue: 0, saturation: 0, amount: 20 };
  });
function drawWheel() {
  const canvas = $("#wheel"),
    c = canvas.getContext("2d"),
    size = 220,
    radius = 96;
  c.clearRect(0, 0, size, size);
  for (let a = 0; a < 360; a++) {
    c.beginPath();
    c.moveTo(110, 110);
    c.arc(110, 110, radius, (a * Math.PI) / 180, ((a + 1.5) * Math.PI) / 180);
    c.closePath();
    c.fillStyle = `hsl(${a} 75% 55%)`;
    c.fill();
  }
  const gradient = c.createRadialGradient(110, 110, 0, 110, 110, radius);
  gradient.addColorStop(0, "#fff");
  gradient.addColorStop(1, "#fff0");
  c.fillStyle = gradient;
  c.beginPath();
  c.arc(110, 110, radius, 0, Math.PI * 2);
  c.fill();
  const g = edits.grades[range],
    a = (g.hue * Math.PI) / 180,
    x = 110 + (Math.cos(a) * radius * g.saturation) / 100,
    y = 110 + (Math.sin(a) * radius * g.saturation) / 100;
  c.beginPath();
  c.arc(x, y, 7, 0, Math.PI * 2);
  c.strokeStyle = "#222";
  c.lineWidth = 3;
  c.stroke();
  c.strokeStyle = "#fff";
  c.lineWidth = 1;
  c.stroke();
  canvas.setAttribute("aria-valuenow", String(g.hue));
  canvas.setAttribute(
    "aria-valuetext",
    `${range}, hue ${Math.round(g.hue)} degrees, saturation ${Math.round(g.saturation)} percent`,
  );
}
let wheelDragging = false;
function updateGradingFromPointer(e) {
  const rect = $("#wheel").getBoundingClientRect(),
    x = ((e.clientX - rect.left) / rect.width) * 220 - 110,
    y = ((e.clientY - rect.top) / rect.height) * 220 - 110;
  edits.grades[range].hue = ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
  edits.grades[range].saturation = clamp((Math.hypot(x, y) / 96) * 100, 0, 100);
  renderPreview();
}
$("#wheel").onpointerdown = (e) => {
  wheelDragging = true;
  e.currentTarget.setPointerCapture(e.pointerId);
  updateGradingFromPointer(e);
};
$("#wheel").onpointermove = (e) => {
  if (wheelDragging) updateGradingFromPointer(e);
};
for (const event of ["pointerup", "pointercancel"])
  $("#wheel").addEventListener(event, () => {
    if (wheelDragging) {
      wheelDragging = false;
      commitEditHistory();
    }
  });
$("#wheel").onkeydown = (e) => {
  if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key))
    return;
  e.preventDefault();
  applyEdit(() => {
    const g = edits.grades[range];
    if (e.key === "ArrowLeft" || e.key === "ArrowRight")
      g.hue = (g.hue + (e.key === "ArrowRight" ? 2 : 358)) % 360;
    else
      g.saturation = clamp(
        g.saturation + (e.key === "ArrowUp" ? 2 : -2),
        0,
        100,
      );
  });
};
$("#ratio").onchange = (e) =>
  applyEdit(() => {
    if (!source) return;
    const ratio = Number(e.target.value);
    if (!ratio) return;
    const g = getRotatedDimensions(source.width, source.height),
      c = edits.crop;
    const desiredH = (c.w * g.width) / ratio / g.height;
    if (desiredH <= 100) c.h = desiredH;
    else {
      c.h = 100;
      c.w = (100 * g.height * ratio) / g.width;
    }
    c.x = (100 - c.w) / 2;
    c.y = (100 - c.h) / 2;
    boundCrop();
  });
for (const [id, delta] of [
  ["rotate-left", 270],
  ["rotate-right", 90],
])
  $(`#${id}`).onclick = () =>
    applyEdit(() => {
      edits.rotation = (edits.rotation + delta) % 360;
      edits.crop = { x: 0, y: 0, w: 100, h: 100 };
      $("#ratio").value = "free";
    });
$("#flip").onclick = () =>
  applyEdit(() => {
    edits.flip = !edits.flip;
  });
$("#reset-crop").onclick = () =>
  applyEdit(() => {
    edits.crop = { x: 0, y: 0, w: 100, h: 100 };
    edits.rotation = 0;
    edits.flip = false;
    $("#ratio").value = "free";
  });
function positionCrop() {
  const box = $("#crop-box");
  box.hidden = panel !== "crop" || !source;
  if (box.hidden) return;
  const image = preview.getBoundingClientRect(),
    viewer = $("#viewer").getBoundingClientRect(),
    c = edits.crop;
  box.style.left = `${image.left - viewer.left + (c.x / 100) * image.width}px`;
  box.style.top = `${image.top - viewer.top + (c.y / 100) * image.height}px`;
  box.style.width = `${(c.w / 100) * image.width}px`;
  box.style.height = `${(c.h / 100) * image.height}px`;
}
let cropDrag = null;
$("#crop-box").onpointerdown = (e) => {
  cropDrag = {
    x: e.clientX,
    y: e.clientY,
    c: clone(edits.crop),
    rect: preview.getBoundingClientRect(),
  };
  e.currentTarget.setPointerCapture(e.pointerId);
};
$("#crop-box").onpointermove = (e) => {
  if (!cropDrag) return;
  edits.crop.x =
    cropDrag.c.x + ((e.clientX - cropDrag.x) / cropDrag.rect.width) * 100;
  edits.crop.y =
    cropDrag.c.y + ((e.clientY - cropDrag.y) / cropDrag.rect.height) * 100;
  boundCrop();
  synchronizeControls();
};
for (const event of ["pointerup", "pointercancel"])
  $("#crop-box").addEventListener(event, () => {
    if (cropDrag) {
      cropDrag = null;
      commitEditHistory();
      renderPreview();
    }
  });
$("#crop-box").onkeydown = (e) => {
  const move = {
    ArrowLeft: [-1, 0],
    ArrowRight: [1, 0],
    ArrowUp: [0, -1],
    ArrowDown: [0, 1],
  }[e.key];
  if (!move) return;
  e.preventDefault();
  applyEdit(() => {
    edits.crop.x += move[0] * (e.shiftKey ? 5 : 1);
    edits.crop.y += move[1] * (e.shiftKey ? 5 : 1);
    boundCrop();
  });
};
new ResizeObserver(positionCrop).observe($("#viewer"));
function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob),
    a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
let exportCancelled = false;
$("#cancel-export").onclick = () => {
  exportCancelled = true;
  worker.terminate();
  for (const p of requests.values()) p.reject(new Error("Export cancelled."));
  requests.clear();
  createProcessingWorker();
  $("#export-dialog").close();
  showStatus("Export cancelled.");
};
$("#export-dialog").addEventListener("cancel", (e) => {
  e.preventDefault();
  $("#cancel-export").click();
});
$("#export").onclick = async () => {
  if (!source || exporting) return;
  exporting = true;
  exportCancelled = false;
  $("#export-dialog").showModal();
  $("#export").disabled = true;
  let canvas;
  try {
    const settings = clone(edits),
      bitmap = source.bitmap,
      name = source.name;
    canvas = document.createElement("canvas");
    canvas.width = source.width;
    canvas.height = source.height;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    context.drawImage(bitmap, 0, 0);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
    const result = await renderInWorker(
      pixels.data,
      canvas.width,
      canvas.height,
      settings,
    );
    if (exportCancelled) return;
    context.putImageData(
      new ImageData(result.data, canvas.width, canvas.height),
      0,
      0,
    );
    const output = document.createElement("canvas");
    drawTransformedPhoto(
      output,
      canvas,
      canvas.width,
      canvas.height,
      settings,
      true,
    );
    const format = $("#format").value;
    if (format === "image/jpeg") {
      const c = output.getContext("2d");
      c.globalCompositeOperation = "destination-over";
      c.fillStyle = "#fff";
      c.fillRect(0, 0, output.width, output.height);
      c.globalCompositeOperation = "source-over";
    }
    $("#export-progress").textContent = "Encoding photo…";
    const blob = await new Promise((resolve) =>
      output.toBlob(resolve, format, quality / 100),
    );
    if (exportCancelled) return;
    if (!blob)
      throw new Error("Export encoding failed. Try JPEG or a smaller photo.");
    if (blob.type !== format)
      throw new Error(
        "This browser does not support that export format. Choose JPEG or PNG.",
      );
    const base = name.replace(/\.[^.]+$/, "") + "-colorcheck";
    downloadBlob(
      blob,
      `${base}.${format === "image/jpeg" ? "jpg" : format === "image/png" ? "png" : "webp"}`,
    );
    if ($("#report").checked)
      downloadBlob(
        new Blob(
          [
            JSON.stringify(
              {
                version: 1,
                product: "ColorCheck Photos",
                output: {
                  width: output.width,
                  height: output.height,
                  colorSpace: "sRGB",
                  format,
                  quality,
                },
                edits: settings,
              },
              null,
              2,
            ),
          ],
          { type: "application/json" },
        ),
        `${base}.json`,
      );
    output.width = output.height = 1;
    showStatus("Export ready. No photo was uploaded.");
  } catch (error) {
    showStatus(error.message);
  } finally {
    if (canvas) canvas.width = canvas.height = 1;
    exporting = false;
    $("#export-dialog").close();
    $("#export-progress").textContent = "Rendering original resolution…";
    synchronizeControls();
    renderPreview();
  }
};
document.addEventListener("keydown", (e) => {
  if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName) || exporting)
    return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
    e.preventDefault();
    $(e.shiftKey ? "#redo" : "#undo").click();
  }
});
synchronizeControls();
