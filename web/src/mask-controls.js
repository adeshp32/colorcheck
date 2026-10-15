import {
  createMaskComponent,
  maskCoverage,
  sourcePoint,
  prepareMask,
} from "./masking.js";
import { createDefaultEditSettings } from "./image-processing.js";

/** Owns mask selection and gestures; masks themselves belong to the edit history. */
export function createMaskControls({
  getEdits,
  getSource,
  getPixels,
  getDisplayPixels,
  getPanel,
  isOriginal,
  render,
  commit,
  synchronize,
  drawPhoto,
  status,
}) {
  const $ = (selector) => document.querySelector(selector);
  const overlay = $("#mask-overlay"),
    scope = $("#adjustment-scope");
  let overlayKey = "",
    overlayPixels = null;
  let selectedId = "",
    componentIndex = 0,
    showOverlay = true,
    drag = null,
    optionKey = "";
  const geometry = [],
    refinements = [];
  const selected = () =>
    (getEdits().masks ?? []).find((mask) => mask.id === selectedId);
  const component = () => selected()?.components[componentIndex];
  const changed = (final = false) => {
    if (final) commit();
    render(!final);
  };
  function slider(parent, label, min, max, step, get, set, list = geometry) {
    const row = document.createElement("div");
    row.className = "control";
    const top = document.createElement("div");
    top.className = "control-top";
    const text = document.createElement("label"),
      input = document.createElement("input"),
      number = document.createElement("input");
    input.type = "range";
    number.type = "number";
    input.id = `mask-${list.length}-${label.toLowerCase().replaceAll(" ", "-")}`;
    text.htmlFor = input.id;
    text.textContent = label;
    number.setAttribute("aria-label", `Mask ${label} value`);
    for (const field of [input, number]) {
      field.min = min;
      field.max = max;
      field.step = step;
      field.addEventListener("input", () => {
        if (
          !selected() ||
          field.value === "" ||
          !Number.isFinite(Number(field.value))
        )
          return;
        set(Math.max(min, Math.min(max, Number(field.value))));
        input.value = number.value = get();
        changed();
      });
      field.addEventListener("change", () => changed(true));
    }
    top.append(text, number);
    row.append(top, input);
    $(parent).append(row);
    list.push({ input, number, get, row, label });
  }
  const shapeSlider = (label, key, min, max, step = 0.01, scale = 100) =>
    slider(
      "#mask-geometry",
      label,
      min,
      max,
      step,
      () => (component()?.[key] ?? 0) * scale,
      (value) => {
        component()[key] = value / scale;
      },
    );
  shapeSlider("Center X", "x", 0, 100);
  shapeSlider("Center Y", "y", 0, 100);
  shapeSlider("Radius X", "rx", 0.05, 150);
  shapeSlider("Radius Y", "ry", 0.05, 150);
  shapeSlider("Angle", "angle", -180, 180, 0.5, 1);
  shapeSlider("End X", "x2", 0, 100);
  shapeSlider("End Y", "y2", 0, 100);
  shapeSlider("Feather", "feather", 0, 100, 1);
  slider(
    "#mask-geometry",
    "Opacity",
    0,
    100,
    1,
    () => (selected()?.opacity ?? 1) * 100,
    (value) => {
      selected().opacity = value / 100;
    },
  );
  slider(
    "#mask-luminance",
    "Minimum luminance",
    0,
    100,
    1,
    () => (selected()?.lumaMin ?? 0) * 100,
    (value) => {
      selected().lumaMin = Math.min(value / 100, selected().lumaMax);
    },
    refinements,
  );
  slider(
    "#mask-luminance",
    "Maximum luminance",
    0,
    100,
    1,
    () => (selected()?.lumaMax ?? 1) * 100,
    (value) => {
      selected().lumaMax = Math.max(value / 100, selected().lumaMin);
    },
    refinements,
  );
  slider(
    "#mask-luminance",
    "Range softness",
    1,
    100,
    1,
    () => (selected()?.rangeSoftness ?? 0.1) * 100,
    (value) => {
      selected().rangeSoftness = value / 100;
    },
    refinements,
  );
  slider(
    "#mask-color-controls",
    "Color tolerance",
    1,
    100,
    1,
    () => (selected()?.colorTolerance ?? 0.25) * 100,
    (value) => {
      selected().colorTolerance = value / 100;
    },
    refinements,
  );

  function newMask(type) {
    if (!getSource()) return status("Choose a photo first.");
    const masks = (getEdits().masks ??= []);
    if (masks.length >= 8)
      return status("Up to eight local masks are available per photo.");
    const mask = {
      id: crypto.randomUUID(),
      name: `Mask ${masks.length + 1}`,
      enabled: true,
      invert: false,
      opacity: 1,
      components: [createMaskComponent(type)],
      refinement: "none",
      lumaMin: 0,
      lumaMax: 1,
      rangeSoftness: 0.1,
      color: [128, 128, 128],
      colorTolerance: 0.25,
      adjustments: createDefaultEditSettings(),
    };
    masks.push(mask);
    selectedId = mask.id;
    componentIndex = 0;
    changed(true);
  }
  for (const type of ["radial", "linear"]) {
    $(`#add-${type}`).onclick = () => newMask(type);
    $(`#append-${type}`).onclick = () => {
      const mask = selected();
      if (!mask) return;
      if (mask.components.length >= 8)
        return status("Up to eight shapes can be combined in a mask.");
      mask.components.push(
        createMaskComponent(type, $("#mask-operation").value),
      );
      componentIndex = mask.components.length - 1;
      changed(true);
    };
  }
  scope.onchange = () => {
    selectedId = scope.value;
    componentIndex = 0;
    synchronize();
    render();
  };
  $("#mask-component").onchange = (event) => {
    componentIndex = Number(event.target.value);
    sync();
    drawOverlay();
  };
  $("#mask-name").onchange = (event) => {
    if (selected()) {
      selected().name = event.target.value.trim() || "Mask";
      changed(true);
    }
  };
  for (const [id, key] of [
    ["mask-invert", "invert"],
    ["mask-enabled", "enabled"],
  ])
    $(`#${id}`).onchange = (event) => {
      if (selected()) {
        selected()[key] = event.target.checked;
        changed(true);
      }
    };
  $("#mask-show").onchange = (event) => {
    showOverlay = event.target.checked;
    drawOverlay();
  };
  $("#mask-refinement").onchange = (event) => {
    if (selected()) {
      selected().refinement = event.target.value;
      changed(true);
    }
  };
  $("#mask-color-value").oninput = (event) => {
    if (selected()) {
      selected().color = [1, 3, 5].map((i) =>
        parseInt(event.target.value.slice(i, i + 2), 16),
      );
      changed();
    }
  };
  $("#mask-color-value").onchange = () => changed(true);
  $("#remove-component").onclick = () => {
    if (selected()?.components.length > 1) {
      selected().components.splice(componentIndex, 1);
      componentIndex = 0;
      changed(true);
    }
  };
  $("#delete-mask").onclick = () => {
    getEdits().masks = (getEdits().masks ?? []).filter(
      (mask) => mask.id !== selectedId,
    );
    selectedId = "";
    changed(true);
  };
  $("#duplicate-mask").onclick = () => {
    if (!selected()) return;
    if (getEdits().masks.length >= 8)
      return status("Up to eight local masks are available per photo.");
    const copy = structuredClone(selected());
    copy.id = crypto.randomUUID();
    copy.name += " copy";
    getEdits().masks.push(copy);
    selectedId = copy.id;
    changed(true);
  };

  function sync() {
    const masks = getEdits().masks ?? [];
    if (!selected()) selectedId = "";
    const key = JSON.stringify(
      masks.map((mask) => [mask.id, mask.name, mask.components.length]),
    );
    if (key !== optionKey) {
      scope.replaceChildren(
        new Option("Whole photo", ""),
        ...masks.map((mask) => new Option(mask.name, mask.id)),
      );
      optionKey = key;
    }
    scope.value = selectedId;
    for (const type of ["radial", "linear"])
      $(`#add-${type}`).disabled = !getSource();
    const mask = selected();
    $("#mask-settings").hidden = !mask;
    if (!mask) {
      drawOverlay();
      return;
    }
    componentIndex = Math.min(componentIndex, mask.components.length - 1);
    $("#mask-component").replaceChildren(
      ...mask.components.map(
        (shape, i) =>
          new Option(`${i + 1}. ${shape.operation} ${shape.type}`, i),
      ),
    );
    $("#mask-component").value = componentIndex;
    $("#mask-name").value = mask.name;
    $("#mask-enabled").checked = mask.enabled;
    $("#mask-invert").checked = mask.invert;
    $("#mask-refinement").value = mask.refinement;
    $("#mask-luminance").hidden = mask.refinement !== "luminance";
    $("#mask-color").hidden = mask.refinement !== "color";
    $("#mask-color-value").value =
      "#" + mask.color.map((v) => v.toString(16).padStart(2, "0")).join("");
    $("#remove-component").disabled = mask.components.length === 1;
    for (const control of [...geometry, ...refinements]) {
      control.input.value = control.number.value =
        Math.round(control.get() * 100) / 100;
      if (["Radius X", "Radius Y", "Angle", "Feather"].includes(control.label))
        control.row.hidden = component().type !== "radial";
      if (["End X", "End Y"].includes(control.label))
        control.row.hidden = component().type !== "linear";
    }
    drawOverlay();
  }
  function drawOverlay() {
    const mask = selected(),
      pixels = getPixels();
    overlay.hidden = !mask || !pixels || getPanel() !== "mask" || isOriginal();
    if (overlay.hidden) {
      if (!mask || !pixels) {
        overlayPixels = null;
        overlayKey = "";
        overlay.width = overlay.height = 1;
      }
      return;
    }
    const preview = $("#preview");
    overlay.style.width = preview.style.width;
    overlay.style.height = preview.style.height;
    const key = JSON.stringify([
      mask.id,
      mask.components,
      componentIndex,
      mask.invert,
      mask.opacity,
      mask.refinement,
      mask.lumaMin,
      mask.lumaMax,
      mask.rangeSoftness,
      mask.color,
      mask.colorTolerance,
      showOverlay,
      getEdits().rotation,
      getEdits().flip,
    ]);
    if (key === overlayKey && pixels === overlayPixels) return;
    overlayKey = key;
    overlayPixels = pixels;
    const canvas = document.createElement("canvas");
    canvas.width = pixels.width;
    canvas.height = pixels.height;
    const context = canvas.getContext("2d"),
      image = context.createImageData(canvas.width, canvas.height),
      rgb = [0, 0, 0],
      preparedMask = prepareMask(mask);
    for (let y = 0; y < canvas.height; y++)
      for (let x = 0; x < canvas.width; x++) {
        const i = (y * canvas.width + x) * 4;
        rgb[0] = pixels.data[i];
        rgb[1] = pixels.data[i + 1];
        rgb[2] = pixels.data[i + 2];
        image.data[i] = 245;
        image.data[i + 1] = 60;
        image.data[i + 2] = 130;
        image.data[i + 3] = showOverlay
          ? maskCoverage(
              preparedMask,
              (x + 0.5) / canvas.width,
              (y + 0.5) / canvas.height,
              rgb,
            ) * 90
          : 0;
      }
    context.putImageData(image, 0, 0);
    const shape = component();
    context.strokeStyle = "white";
    context.lineWidth = Math.max(1.5, canvas.width / 350);
    context.beginPath();
    if (shape.type === "radial") {
      // Rotate in normalized coordinates so the outline matches the mask on any aspect ratio.
      for (let i = 0; i <= 96; i++) {
        const a = (i / 96) * Math.PI * 2,
          rotation = (shape.angle * Math.PI) / 180;
        const x =
          shape.x +
          Math.cos(a) * shape.rx * Math.cos(rotation) -
          Math.sin(a) * shape.ry * Math.sin(rotation);
        const y =
          shape.y +
          Math.cos(a) * shape.rx * Math.sin(rotation) +
          Math.sin(a) * shape.ry * Math.cos(rotation);
        i
          ? context.lineTo(x * canvas.width, y * canvas.height)
          : context.moveTo(x * canvas.width, y * canvas.height);
      }
    } else {
      context.moveTo(shape.x * canvas.width, shape.y * canvas.height);
      context.lineTo(shape.x2 * canvas.width, shape.y2 * canvas.height);
    }
    context.stroke();
    context.beginPath();
    context.arc(
      shape.x * canvas.width,
      shape.y * canvas.height,
      Math.max(4, canvas.width / 100),
      0,
      Math.PI * 2,
    );
    context.stroke();
    const display = getDisplayPixels();
    drawPhoto(
      overlay,
      canvas,
      display.width,
      display.height,
      getEdits(),
      false,
    );
    overlay.style.width = preview.style.width;
    overlay.style.height = preview.style.height;
  }
  const gesture = document.createElement("select");
  gesture.id = "mask-gesture";
  gesture.setAttribute("aria-label", "Mask gesture");
  for (const [value, label] of [
    ["move", "Move shape"],
    ["draw", "Draw shape"],
    ["resize", "Resize shape"],
    ["rotate", "Rotate shape"],
  ])
    gesture.add(new Option(label, value));
  $("#mask-geometry").before(gesture);
  function point(event) {
    const rect = overlay.getBoundingClientRect(),
      source = getSource();
    return sourcePoint(
      (event.clientX - rect.left) / rect.width,
      (event.clientY - rect.top) / rect.height,
      source.width,
      source.height,
      getEdits(),
    );
  }
  overlay.onpointerdown = (event) => {
    if (!component()) return;
    event.preventDefault();
    drag = { start: point(event), shape: structuredClone(component()) };
    overlay.setPointerCapture(event.pointerId);
  };
  overlay.onpointermove = (event) => {
    if (!drag) return;
    const p = point(event),
      shape = component(),
      old = drag.shape,
      dx = p.x - drag.start.x,
      dy = p.y - drag.start.y;
    if (gesture.value === "draw") {
      if (shape.type === "linear")
        Object.assign(shape, {
          x: drag.start.x,
          y: drag.start.y,
          x2: p.x,
          y2: p.y,
        });
      else
        Object.assign(shape, {
          x: (drag.start.x + p.x) / 2,
          y: (drag.start.y + p.y) / 2,
          rx: Math.max(0.005, Math.abs(dx) / 2),
          ry: Math.max(0.005, Math.abs(dy) / 2),
        });
    } else if (gesture.value === "resize") {
      if (shape.type === "linear") Object.assign(shape, { x2: p.x, y2: p.y });
      else
        Object.assign(shape, {
          rx: Math.max(0.005, Math.min(1.5, old.rx + dx)),
          ry: Math.max(0.005, Math.min(1.5, old.ry + dy)),
        });
    } else if (gesture.value === "rotate")
      shape.angle = (Math.atan2(p.y - shape.y, p.x - shape.x) * 180) / Math.PI;
    else {
      const mx = Math.max(-old.x, Math.min(1 - old.x, dx)),
        my = Math.max(-old.y, Math.min(1 - old.y, dy));
      shape.x = old.x + mx;
      shape.y = old.y + my;
      if (shape.type === "linear") {
        shape.x2 = Math.max(0, Math.min(1, old.x2 + mx));
        shape.y2 = Math.max(0, Math.min(1, old.y2 + my));
      }
    }
    changed();
  };
  for (const name of ["pointerup", "pointercancel", "lostpointercapture"])
    overlay.addEventListener(name, () => {
      if (drag) {
        drag = null;
        changed(true);
      }
    });
  overlay.onkeydown = (event) => {
    const delta = {
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
      ArrowUp: [0, -1],
      ArrowDown: [0, 1],
    }[event.key];
    if (!delta || !component()) return;
    event.preventDefault();
    const shape = component(),
      x = event.shiftKey ? (shape.type === "linear" ? "x2" : "rx") : "x",
      y = event.shiftKey ? (shape.type === "linear" ? "y2" : "ry") : "y";
    const step = event.altKey ? 0.0001 : 0.001;
    shape[x] = Math.max(0.0005, Math.min(1, shape[x] + delta[0] * step));
    shape[y] = Math.max(0.0005, Math.min(1, shape[y] + delta[1] * step));
    changed(true);
  };
  return {
    sync,
    drawOverlay,
    currentAdjustments: () => selected()?.adjustments ?? getEdits(),
  };
}
