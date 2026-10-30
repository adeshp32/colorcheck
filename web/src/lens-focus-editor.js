import {
  focusAtPoint,
  focusBounds,
  settingsForFocusBounds,
  sampleDepth,
} from "./depth-map.js";

export function createLensFocusEditor({
  getMap,
  getSettings,
  isLocalScope,
  render,
  commit,
}) {
  const $ = (selector) => document.querySelector(selector);
  const inspector = $("#depth-inspector"),
    stage = $("#depth-map-stage"),
    canvas = $("#depth-preview"),
    marker = $("#depth-focus-handle");
  const track = $("#depth-range-track"),
    band = $("#depth-focus-band"),
    lowHandle = $("#depth-range-low"),
    highHandle = $("#depth-range-high");
  const histogram = $("#depth-range-histogram");
  const fine = $("#depth-fine"),
    exactLow = $("#depth-exact-low"),
    exactHigh = $("#depth-exact-high");
  let drag = null,
    drawKey = "",
    previousMap = null;
  const current = () => getSettings().lensBlur;
  function pick(x, y) {
    Object.assign(current(), focusAtPoint(getMap(), x, y), { enabled: true });
    render(true);
  }
  function restoreSnapshot() {
    if (drag) {
      if (drag.settings === current() && drag.map === getMap())
        Object.assign(current(), drag.snapshot);
      drag = null;
      render();
    }
  }
  function start(event, kind, element) {
    if (
      !getMap() ||
      isLocalScope() ||
      (event.pointerType === "mouse" && event.button !== 0)
    )
      return;
    event.preventDefault();
    event.stopPropagation();
    drag = {
      id: event.pointerId,
      kind,
      settings: current(),
      map: getMap(),
      snapshot: structuredClone(current()),
      ...focusBounds(current()),
      startX: event.clientX,
      startY: event.clientY,
      point: current().focusPoint ?? { x: 0.5, y: 0.5 },
      sensitivity: fine.checked || event.altKey ? 0.2 : 1,
      relative: !!event.target.closest(".depth-range-handle"),
    };
    element.setPointerCapture(event.pointerId);
    if (kind === "map") {
      if (!event.target.closest("#depth-focus-handle")) {
        pickFromPointer(event);
        drag.point = { ...current().focusPoint };
      }
    } else if (kind !== "band" && !drag.relative) {
      updateRange(event);
      Object.assign(drag, focusBounds(current()), { relative: true });
    }
  }
  function pickFromPointer(event) {
    const bounds = canvas.getBoundingClientRect();
    pick(
      (event.clientX - bounds.left) / bounds.width,
      (event.clientY - bounds.top) / bounds.height,
    );
  }
  function updateMap(event) {
    const rect = canvas.getBoundingClientRect();
    pick(
      drag.point.x +
        ((event.clientX - drag.startX) / rect.width) * drag.sensitivity,
      drag.point.y +
        ((event.clientY - drag.startY) / rect.height) * drag.sensitivity,
    );
  }
  function updateRange(event) {
    const rect = track.getBoundingClientRect();
    const value = Math.max(
      0,
      Math.min(100, ((event.clientX - rect.left) / rect.width) * 100),
    );
    let { low, high } = drag;
    const movement =
      ((event.clientX - drag.startX) / rect.width) * 100 * drag.sensitivity;
    if (drag.kind === "low")
      low = Math.max(
        0,
        Math.min(high - 1, drag.relative ? low + movement : value),
      );
    else if (drag.kind === "high")
      high = Math.min(
        100,
        Math.max(low + 1, drag.relative ? high + movement : value),
      );
    else {
      const delta = Math.max(-low, Math.min(100 - high, movement));
      low += delta;
      high += delta;
    }
    Object.assign(current(), settingsForFocusBounds(low, high), {
      enabled: true,
    });
    render(true);
  }
  stage.addEventListener("pointerdown", (event) => start(event, "map", stage));
  track.addEventListener("pointerdown", (event) => {
    const rect = track.getBoundingClientRect(),
      { low, high } = focusBounds(current());
    const value = ((event.clientX - rect.left) / rect.width) * 100;
    const threshold = (16 / rect.width) * 100;
    const selected = event.target.closest("button")?.id;
    const kind =
      selected === "depth-range-low"
        ? "low"
        : selected === "depth-range-high"
          ? "high"
          : Math.min(Math.abs(value - low), Math.abs(value - high)) <
                threshold ||
              value < low ||
              value > high
            ? Math.abs(value - low) < Math.abs(value - high)
              ? "low"
              : "high"
            : "band";
    start(event, kind, track);
  });
  for (const [input, kind] of [
    [exactLow, "low"],
    [exactHigh, "high"],
  ]) {
    input.addEventListener("change", () => {
      if (
        !getMap() ||
        isLocalScope() ||
        !Number.isFinite(input.valueAsNumber)
      ) {
        sync();
        return;
      }
      let { low, high } = focusBounds(current());
      if (kind === "low")
        low = Math.max(0, Math.min(high - 1, input.valueAsNumber));
      else high = Math.min(100, Math.max(low + 1, input.valueAsNumber));
      Object.assign(current(), settingsForFocusBounds(low, high), {
        enabled: true,
      });
      input.value = focusBounds(current())[kind].toFixed(1);
      commit();
      render();
    });
  }
  for (const element of [stage, track]) {
    element.addEventListener("pointermove", (event) => {
      if (drag?.id !== event.pointerId) return;
      if (drag.settings !== current() || drag.map !== getMap()) {
        drag = null;
        return;
      }
      drag.kind === "map" ? updateMap(event) : updateRange(event);
    });
    element.addEventListener("pointerup", (event) => {
      if (drag?.id !== event.pointerId) return;
      const valid = drag.settings === current() && drag.map === getMap();
      drag = null;
      if (valid) commit();
      render();
    });
    element.addEventListener("pointercancel", restoreSnapshot);
    element.addEventListener("lostpointercapture", restoreSnapshot);
  }
  marker.addEventListener("keydown", (event) => {
    const delta = {
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
      ArrowUp: [0, -1],
      ArrowDown: [0, 1],
    }[event.key];
    if (!delta || !getMap() || isLocalScope()) return;
    event.preventDefault();
    const point = current().focusPoint ?? { x: 0.5, y: 0.5 },
      step = event.shiftKey ? 0.025 : 0.005;
    pick(point.x + delta[0] * step, point.y + delta[1] * step);
    commit();
    render();
  });
  for (const [element, kind] of [
    [lowHandle, "low"],
    [highHandle, "high"],
    [band, "band"],
  ])
    element.addEventListener("keydown", (event) => {
      if (
        !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key) ||
        !getMap() ||
        isLocalScope()
      )
        return;
      event.preventDefault();
      let { low, high } = focusBounds(current());
      const delta =
        (event.key === "ArrowLeft" ? -1 : 1) * (event.shiftKey ? 1 : 0.1);
      if (kind === "low")
        low =
          event.key === "Home"
            ? 0
            : event.key === "End"
              ? high - 1
              : Math.max(0, Math.min(high - 1, low + delta));
      else if (kind === "high")
        high =
          event.key === "End"
            ? 100
            : event.key === "Home"
              ? low + 1
              : Math.min(100, Math.max(low + 1, high + delta));
      else {
        const shift =
          event.key === "Home"
            ? -low
            : event.key === "End"
              ? 100 - high
              : Math.max(-low, Math.min(100 - high, delta));
        low += shift;
        high += shift;
      }
      Object.assign(current(), settingsForFocusBounds(low, high), {
        enabled: true,
      });
      commit();
      render();
    });
  function drawHistogram(map) {
    const ctx = histogram.getContext("2d"),
      bins = new Uint32Array(64);
    for (let i = 0; i < map.values.length; i += 3)
      bins[Math.min(63, Math.floor(map.values[i] * 64))]++;
    ctx.clearRect(0, 0, histogram.width, histogram.height);
    ctx.fillStyle = "#8c8c96";
    const max = Math.max(1, ...bins);
    for (let i = 0; i < 64; i++) {
      const h = (bins[i] / max) * 28;
      ctx.fillRect(i * 4, 32 - h, 3, h);
    }
  }
  function sync() {
    const map = getMap(),
      settings = current();
    inspector.hidden = !map || isLocalScope();
    $("#lens-pick-row").hidden = !map || isLocalScope();
    $("#lens-auto-focus").disabled = !map || isLocalScope();
    if (inspector.hidden) return;
    const { low, high } = focusBounds(settings);
    for (const [input, value, min, max] of [
      [exactLow, low, 0, high - 1],
      [exactHigh, high, low + 1, 100],
    ]) {
      if (document.activeElement !== input) input.value = value.toFixed(1);
      input.min = String(min);
      input.max = String(max);
    }
    lowHandle.style.left = low + "%";
    highHandle.style.left = high + "%";
    band.style.left = low + "%";
    band.style.width = high - low + "%";
    for (const [element, value, min, max] of [
      [lowHandle, low, 0, high - 1],
      [highHandle, high, low + 1, 100],
      [band, settings.focus, 0, 100],
    ]) {
      element.setAttribute("aria-valuenow", value.toFixed(1));
      element.setAttribute("aria-valuemin", String(min));
      element.setAttribute("aria-valuemax", String(max));
    }
    $("#depth-range-value").textContent =
      `${low.toFixed(1)} - ${high.toFixed(1)}`;
    marker.hidden = !settings.focusPoint;
    if (settings.focusPoint) {
      marker.style.left = `${settings.focusPoint.x * 100}%`;
      marker.style.top = `${settings.focusPoint.y * 100}%`;
    }
    const key = [settings.focus, settings.range, settings.mode].join(":");
    if (previousMap === map && drawKey === key) return;
    if (previousMap !== map) drawHistogram(map);
    previousMap = map;
    drawKey = key;
    const scale = Math.min(1, 256 / Math.max(map.width, map.height));
    canvas.width = Math.round(map.width * scale);
    canvas.height = Math.round(map.height * scale);
    canvas.hidden = false;
    stage.style.setProperty("--depth-aspect", canvas.width / canvas.height);
    const pixels = new Uint8ClampedArray(canvas.width * canvas.height * 4);
    for (let y = 0; y < canvas.height; y++)
      for (let x = 0; x < canvas.width; x++) {
        const z = sampleDepth(
            map,
            (x + 0.5) / canvas.width,
            (y + 0.5) / canvas.height,
          ),
          shade = 30 + z * 195;
        const sharp =
          settings.mode === "background"
            ? z * 100 >= low
            : settings.mode === "foreground"
              ? z * 100 <= high
              : z * 100 >= low && z * 100 <= high;
        const i = (y * canvas.width + x) * 4;
        pixels[i] = sharp ? shade * 0.4 + 50 : shade;
        pixels[i + 1] = sharp ? shade * 0.4 + 140 : shade;
        pixels[i + 2] = sharp ? shade * 0.4 + 145 : shade;
        pixels[i + 3] = 255;
      }
    canvas
      .getContext("2d")
      .putImageData(new ImageData(pixels, canvas.width, canvas.height), 0, 0);
  }
  return { sync };
}
