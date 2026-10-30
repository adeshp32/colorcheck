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
  const graph = {
    left: 20,
    top: 20,
    width: canvas.width - 40,
    height: canvas.height - 40,
  };
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
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.strokeStyle = "#9196a42f";
    context.lineWidth = 1;
    for (let i = 1; i < 4; i++) {
      const x = graph.left + (i * graph.width) / 4,
        y = graph.top + (i * graph.height) / 4;
      context.beginPath();
      context.moveTo(x, graph.top);
      context.lineTo(x, graph.top + graph.height);
      context.moveTo(graph.left, y);
      context.lineTo(graph.left + graph.width, y);
      context.stroke();
    }

    context.setLineDash([5, 6]);
    context.strokeStyle = "#9196a45c";
    context.beginPath();
    context.moveTo(graph.left, graph.top + graph.height);
    context.lineTo(graph.left + graph.width, graph.top);
    context.stroke();
    context.setLineDash([]);

    const color = {
      master: "#7878ed",
      red: "#e95967",
      green: "#41b58d",
      blue: "#548ef1",
    }[channel];
    const curve = new Path2D();
    for (let x = 0; x <= graph.width; x++) {
      const y =
        graph.top +
        graph.height -
        sampleCurve(p, x / graph.width) * graph.height;
      x ? curve.lineTo(x + graph.left, y) : curve.moveTo(x + graph.left, y);
    }
    const fill = new Path2D(curve);
    fill.lineTo(graph.left + graph.width, graph.top + graph.height);
    fill.lineTo(graph.left, graph.top + graph.height);
    fill.closePath();
    const gradient = context.createLinearGradient(
      0,
      graph.top,
      0,
      graph.top + graph.height,
    );
    gradient.addColorStop(0, `${color}24`);
    gradient.addColorStop(1, `${color}03`);
    context.fillStyle = gradient;
    context.fill(fill);
    context.strokeStyle = color;
    context.lineWidth = 3;
    context.lineCap = "round";
    context.lineJoin = "round";
    context.stroke(curve);
    context.lineCap = "butt";
    p.forEach((point, i) => {
      const x = graph.left + point.x * graph.width,
        y = graph.top + graph.height - point.y * graph.height;
      context.beginPath();
      context.arc(x, y, i === selected ? 9 : 6, 0, Math.PI * 2);
      context.fillStyle = i === selected ? color : "#fff";
      context.fill();
      context.strokeStyle = i === selected ? "#fff" : color;
      context.lineWidth = i === selected ? 3 : 2;
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
    const canvasX = ((event.clientX - box.left) / box.width) * canvas.width,
      canvasY = ((event.clientY - box.top) / box.height) * canvas.height;
    return {
      x: Math.max(0, Math.min(1, (canvasX - graph.left) / graph.width)),
      y: Math.max(
        0,
        Math.min(1, (graph.top + graph.height - canvasY) / graph.height),
      ),
    };
  }
  canvas.onpointerdown = (event) => {
    event.preventDefault();
    const p = editable(),
      at = position(event);
    let closest = -1,
      distance = 32;
    p.forEach((point, i) => {
      const d = Math.hypot(
        (point.x - at.x) * graph.width,
        (point.y - at.y) * graph.height,
      );
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
        const onCurve = sampleCurve(p, at.x);
        const added = {
          x: at.x,
          y: Math.abs(at.y - onCurve) * graph.height < 28 ? onCurve : at.y,
        };
        p.push(added);
        p.sort((a, b) => a.x - b.x);
        closest = p.indexOf(added);
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
