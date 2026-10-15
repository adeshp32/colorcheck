import { sampleCurve } from "./tone-curves.js";
import { applyToneCurve } from "./image-processing.js";

export function createCurveEditor({ getSettings, render, commit }) {
  const canvas = document.querySelector("#curve-preview"),
    context = canvas.getContext("2d");
  const channels = document.querySelector("#curve-channels"),
    input = document.querySelector("#curve-input"),
    output = document.querySelector("#curve-output");
  let channel = "master",
    selected = 0,
    dragging = false;
  const points = () =>
    getSettings().curves?.[channel] ??
    (channel === "master"
      ? [0, 0.25, 0.5, 0.75, 1].map((x) => ({
          x,
          y: applyToneCurve(x, getSettings().curve),
        }))
      : [
          { x: 0, y: 0 },
          { x: 1, y: 1 },
        ]);
  function editable() {
    const settings = getSettings();
    settings.curves ??= {};
    if (!settings.curves[channel])
      settings.curves[channel] = structuredClone(points());
    if (channel === "master") settings.curve = "linear";
    return settings.curves[channel];
  }
  function draw() {
    const p = points();
    selected = Math.min(selected, p.length - 1);
    context.clearRect(0, 0, 320, 240);
    context.strokeStyle = "#9196a455";
    context.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const x = 16 + i * 72,
        y = 16 + i * 52;
      context.beginPath();
      context.moveTo(x, 16);
      context.lineTo(x, 224);
      context.moveTo(16, y);
      context.lineTo(304, y);
      context.stroke();
    }
    context.strokeStyle = {
      master: "#7878ed",
      red: "#e95967",
      green: "#41b58d",
      blue: "#548ef1",
    }[channel];
    context.lineWidth = 2;
    context.beginPath();
    for (let x = 0; x <= 288; x++) {
      const y = 224 - sampleCurve(p, x / 288) * 208;
      x ? context.lineTo(x + 16, y) : context.moveTo(x + 16, y);
    }
    context.stroke();
    p.forEach((point, i) => {
      context.beginPath();
      context.arc(
        16 + point.x * 288,
        224 - point.y * 208,
        i === selected ? 7 : 5,
        0,
        Math.PI * 2,
      );
      context.fillStyle = i === selected ? "#5454e8" : "#fff";
      context.fill();
      context.stroke();
    });
    input.value = Math.round(p[selected].x * 255);
    output.value = Math.round(p[selected].y * 255);
    input.disabled = selected === 0 || selected === p.length - 1;
    document.querySelector("#delete-curve-point").disabled = input.disabled;
    canvas.setAttribute(
      "aria-valuetext",
      `${channel}, point ${selected + 1}, input ${input.value}, output ${output.value}`,
    );
  }
  function position(event) {
    const box = canvas.getBoundingClientRect();
    return {
      x: Math.max(
        0,
        Math.min(
          1,
          (((event.clientX - box.left) / box.width) * 320 - 16) / 288,
        ),
      ),
      y: Math.max(
        0,
        Math.min(
          1,
          (224 - ((event.clientY - box.top) / box.height) * 240) / 208,
        ),
      ),
    };
  }
  canvas.onpointerdown = (event) => {
    event.preventDefault();
    const p = editable(),
      at = position(event);
    let closest = -1,
      distance = 24;
    p.forEach((point, i) => {
      const d = Math.hypot((point.x - at.x) * 288, (point.y - at.y) * 208);
      if (d < distance) {
        distance = d;
        closest = i;
      }
    });
    if (closest < 0) {
      if (p.length >= 16) return;
      const existing = p.findIndex(
        (point) => Math.abs(point.x - at.x) < 1 / 255,
      );
      if (existing >= 0) closest = existing;
      else {
        p.push(at);
        p.sort((a, b) => a.x - b.x);
        closest = p.indexOf(at);
      }
    }
    selected = closest;
    dragging = true;
    canvas.setPointerCapture(event.pointerId);
    draw();
    render(true);
  };
  function move(x, y) {
    const p = editable(),
      point = p[selected];
    if (selected > 0 && selected < p.length - 1)
      point.x = Math.max(
        p[selected - 1].x + 1 / 255,
        Math.min(p[selected + 1].x - 1 / 255, x),
      );
    point.y = Math.max(0, Math.min(1, y));
    draw();
    render(true);
  }
  canvas.onpointermove = (event) => {
    if (dragging) {
      const at = position(event);
      move(at.x, at.y);
    }
  };
  for (const event of ["pointerup", "pointercancel", "lostpointercapture"])
    canvas.addEventListener(event, () => {
      if (dragging) {
        dragging = false;
        commit();
        render();
      }
    });
  canvas.onkeydown = (event) => {
    const direction = {
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
      ArrowUp: [0, 1],
      ArrowDown: [0, -1],
    }[event.key];
    if (!direction) return;
    event.preventDefault();
    const point = points()[selected];
    move(point.x + direction[0] / 255, point.y + direction[1] / 255);
    commit();
  };
  for (const button of channels.querySelectorAll("button"))
    button.onclick = () => {
      channel = button.dataset.channel;
      selected = 0;
      channels
        .querySelectorAll("button")
        .forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
      draw();
    };
  for (const field of [input, output])
    field.onchange = () => {
      if (!Number.isFinite(field.valueAsNumber)) return;
      move(Number(input.value) / 255, Number(output.value) / 255);
      commit();
      render();
    };
  document.querySelector("#delete-curve-point").onclick = () => {
    const p = editable();
    if (selected > 0 && selected < p.length - 1) {
      p.splice(selected, 1);
      selected = 0;
      commit();
      render();
    }
  };
  document.querySelector("#reset-curve-channel").onclick = () => {
    const settings = getSettings();
    if (settings.curves) delete settings.curves[channel];
    if (channel === "master") settings.curve = "linear";
    selected = 0;
    commit();
    render();
  };
  return { draw };
}
