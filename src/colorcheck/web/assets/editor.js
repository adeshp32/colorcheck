(function () {
  "use strict";

  const DEFAULT_PLAN = {
    version: 1,
    trims: [],
    crop: { x: 0, y: 0, width: 1, height: 1 },
    color: { mode: "neutral", tint: "#ffffff", intensity: 0, black_and_white: false },
    text_overlays: [],
  };

  const copy = (value) => JSON.parse(JSON.stringify(value));
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const number = (value, fallback) => Number.isFinite(Number(value)) ? Number(value) : fallback;

  function normalizedPlan(value) {
    const raw = value && typeof value === "object" ? value : {};
    return {
      version: 1,
      trims: Array.isArray(raw.trims) ? raw.trims.slice(0, 64).map((item) => ({
        start: number(item.start, 0),
        end: number(item.end, 0),
        mode: item.mode === "remove" ? "remove" : "keep",
      })) : [],
      crop: {
        x: clamp(number(raw.crop?.x, 0), 0, 1),
        y: clamp(number(raw.crop?.y, 0), 0, 1),
        width: clamp(number(raw.crop?.width, 1), 0.05, 1),
        height: clamp(number(raw.crop?.height, 1), 0.05, 1),
      },
      color: {
        mode: String(raw.color?.mode || "neutral"),
        tint: /^#[0-9a-f]{6}$/i.test(raw.color?.tint || "") ? raw.color.tint : "#ffffff",
        intensity: clamp(Math.round(number(raw.color?.intensity, 0)), 0, 100),
        black_and_white: Boolean(raw.color?.black_and_white),
      },
      text_overlays: Array.isArray(raw.text_overlays) ? raw.text_overlays.slice(0, 24).map((item) => ({
        text: String(item.text || "").slice(0, 200),
        start: number(item.start, 0),
        end: number(item.end, 5),
        x: clamp(number(item.x, 0.5), 0, 1),
        y: clamp(number(item.y, 0.85), 0, 1),
        size: clamp(number(item.size, 5), 1, 20),
        color: /^#[0-9a-f]{6}$/i.test(item.color || "") ? item.color : "#ffffff",
        background: Boolean(item.background),
      })) : [],
    };
  }

  function mergeSegments(items) {
    const result = [];
    items.slice().sort((a, b) => a[0] - b[0]).forEach(([start, end]) => {
      if (end - start < 0.04) return;
      const last = result[result.length - 1];
      if (last && start <= last[1] + 0.001) last[1] = Math.max(last[1], end);
      else result.push([start, end]);
    });
    return result;
  }

  function retainedSegments(plan, duration) {
    if (!duration || duration <= 0) return [];
    const keeps = plan.trims.filter((item) => item.mode === "keep")
      .map((item) => [clamp(item.start, 0, duration), clamp(item.end, 0, duration)]);
    let segments = keeps.length ? mergeSegments(keeps) : [[0, duration]];
    plan.trims.filter((item) => item.mode === "remove").forEach((item) => {
      const removeStart = clamp(item.start, 0, duration);
      const removeEnd = clamp(item.end, 0, duration);
      const next = [];
      segments.forEach(([start, end]) => {
        if (removeEnd <= start || removeStart >= end) next.push([start, end]);
        else {
          if (removeStart > start) next.push([start, Math.min(removeStart, end)]);
          if (removeEnd < end) next.push([Math.max(removeEnd, start), end]);
        }
      });
      segments = mergeSegments(next);
    });
    return segments;
  }

  function formatTime(seconds) {
    const safe = Math.max(0, number(seconds, 0));
    const minutes = Math.floor(safe / 60);
    return `${minutes}:${(safe % 60).toFixed(2).padStart(5, "0")}`;
  }

  function parseScript(root, selector, fallback) {
    const node = root.querySelector(selector);
    if (!node) return fallback;
    try { return JSON.parse(node.textContent); } catch (_error) { return fallback; }
  }

  class Editor {
    constructor(root, sourceInput, initialPlan, correction) {
      this.root = root;
      this.sourceInput = sourceInput;
      this.plan = normalizedPlan(initialPlan);
      this.correction = correction || {};
      this.history = [];
      this.duration = 0;
      this.width = 16;
      this.height = 9;
      this.objectUrl = null;
      this.video = root.querySelector("[data-preview-video]");
      this.stage = root.querySelector("[data-preview-stage]");
      this.strengthInput = root.querySelector("[data-correction-strength]");
      this.correctionStrength = clamp(number(this.strengthInput?.value, 50), 0, 100);
      this.bindSource();
      this.bindTrim();
      this.bindCrop();
      this.bindColor();
      this.bindText();
      this.bindPanels();
      this.render();
    }

    snapshot() {
      this.history.push(copy(this.plan));
      if (this.history.length > 50) this.history.shift();
    }

    getPlan() { return copy(this.plan); }
    getSegments() { return retainedSegments(this.plan, this.duration); }
    getSourceFile() { return this.sourceInput?.files?.[0] || null; }
    getCorrectionStrength() { return this.correctionStrength; }

    bindSource() {
      this.sourceInput?.addEventListener("change", () => {
        const file = this.getSourceFile();
        if (!file) return;
        if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
        this.objectUrl = URL.createObjectURL(file);
        const media = this.video || document.createElement("video");
        const previewStatus = this.root.querySelector("[data-preview-status]");
        if (previewStatus) previewStatus.textContent = "Loading local preview...";
        media.preload = "metadata";
        media.addEventListener("loadedmetadata", () => {
          this.duration = media.duration;
          this.width = media.videoWidth || 16;
          this.height = media.videoHeight || 9;
          if (this.stage) {
            this.stage.hidden = false;
            this.stage.style.setProperty("--source-ratio", `${this.width} / ${this.height}`);
          }
          this.root.querySelectorAll("[data-text-end]").forEach((input) => {
            if (number(input.value, 5) === 5) input.value = this.duration.toFixed(2);
          });
          this.render();
        }, { once: true });
        media.addEventListener("canplay", () => {
          if (previewStatus) previewStatus.textContent = "Preview ready. Press play and adjust the correction or edits below.";
        }, { once: true });
        media.addEventListener("error", () => {
          if (previewStatus) previewStatus.textContent = "This browser cannot play the selected codec. The final server export can still transcode it.";
        }, { once: true });
        if (this.video && !this.video.dataset.timelineBound) {
          this.video.dataset.timelineBound = "true";
          this.video.addEventListener("timeupdate", () => this.enforceTimeline());
          this.video.addEventListener("seeked", () => this.renderTextPreview());
        }
        media.src = this.objectUrl;
        media.load();
      });
    }

    bindTrim() {
      const start = this.root.querySelector("[data-trim-start]");
      const end = this.root.querySelector("[data-trim-end]");
      if (!start || !end) return;
      const sync = (changed) => {
        if (changed === start && number(start.value, 0) >= number(end.value, 1000)) {
          start.value = String(Math.max(0, number(end.value, 1000) - 1));
        }
        if (changed === end && number(end.value, 1000) <= number(start.value, 0)) {
          end.value = String(Math.min(1000, number(start.value, 0) + 1));
        }
        this.renderTrimSelection();
      };
      start.addEventListener("input", () => sync(start));
      end.addEventListener("input", () => sync(end));
      this.root.querySelector("[data-add-trim]")?.addEventListener("click", () => {
        if (!this.duration) return;
        const mode = this.root.querySelector("input[type=radio][name$=trim_mode]:checked")?.value || "keep";
        const selectedStart = number(start.value, 0) / 1000 * this.duration;
        const selectedEnd = number(end.value, 1000) / 1000 * this.duration;
        if (selectedEnd - selectedStart < 0.04) return;
        this.snapshot();
        this.plan.trims.push({ start: selectedStart, end: selectedEnd, mode });
        this.render();
      });
      this.root.querySelector("[data-undo]")?.addEventListener("click", () => {
        const previous = this.history.pop();
        if (previous) {
          this.plan = normalizedPlan(previous);
          this.render();
        }
      });
      this.root.querySelector("[data-clear]")?.addEventListener("click", () => {
        this.snapshot();
        this.plan = normalizedPlan(DEFAULT_PLAN);
        this.render();
      });
      this.renderTrimSelection();
    }

    renderTrimSelection() {
      const start = this.root.querySelector("[data-trim-start]");
      const end = this.root.querySelector("[data-trim-end]");
      const startLabel = this.root.querySelector("[data-trim-start-label]");
      const endLabel = this.root.querySelector("[data-trim-end-label]");
      if (startLabel) startLabel.textContent = formatTime(number(start?.value, 0) / 1000 * this.duration);
      if (endLabel) endLabel.textContent = formatTime(number(end?.value, 1000) / 1000 * this.duration);
    }

    bindCrop() {
      const fields = {
        x: this.root.querySelector("[data-crop-x]"),
        y: this.root.querySelector("[data-crop-y]"),
        width: this.root.querySelector("[data-crop-width]"),
        height: this.root.querySelector("[data-crop-height]"),
      };
      Object.entries(fields).forEach(([name, input]) => input?.addEventListener("change", () => {
        this.snapshot();
        this.plan.crop[name] = clamp(number(input.value, name === "width" || name === "height" ? 100 : 0) / 100, name === "width" || name === "height" ? 0.05 : 0, 1);
        this.plan.crop.x = Math.min(this.plan.crop.x, 1 - this.plan.crop.width);
        this.plan.crop.y = Math.min(this.plan.crop.y, 1 - this.plan.crop.height);
        this.render();
      }));
      this.root.querySelector("[data-reset-crop]")?.addEventListener("click", () => {
        this.snapshot();
        this.plan.crop = copy(DEFAULT_PLAN.crop);
        this.render();
      });
      this.root.querySelector("[data-crop-aspect]")?.addEventListener("change", (event) => {
        if (event.target.value === "free") return;
        this.snapshot();
        const desired = event.target.value === "source" ? this.width / this.height : number(event.target.value, this.width / this.height);
        const sourceRatio = this.width / this.height;
        let width = 1;
        let height = sourceRatio / desired;
        if (height > 1) { height = 1; width = desired / sourceRatio; }
        this.plan.crop = { x: (1 - width) / 2, y: (1 - height) / 2, width, height };
        this.render();
      });
      this.bindCropPointer();
    }

    bindCropPointer() {
      const box = this.root.querySelector("[data-crop-box]");
      if (!box || !this.stage) return;
      box.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        box.setPointerCapture(event.pointerId);
        const corner = event.target.dataset.corner || "move";
        const initial = copy(this.plan.crop);
        const bounds = this.stage.getBoundingClientRect();
        const startX = event.clientX;
        const startY = event.clientY;
        this.snapshot();
        const move = (pointer) => {
          const dx = (pointer.clientX - startX) / bounds.width;
          const dy = (pointer.clientY - startY) / bounds.height;
          const crop = copy(initial);
          if (corner === "move") {
            crop.x = clamp(initial.x + dx, 0, 1 - crop.width);
            crop.y = clamp(initial.y + dy, 0, 1 - crop.height);
          } else {
            if (corner.includes("e")) crop.width = clamp(initial.width + dx, 0.05, 1 - initial.x);
            if (corner.includes("s")) crop.height = clamp(initial.height + dy, 0.05, 1 - initial.y);
            if (corner.includes("w")) {
              crop.x = clamp(initial.x + dx, 0, initial.x + initial.width - 0.05);
              crop.width = initial.width + initial.x - crop.x;
            }
            if (corner.includes("n")) {
              crop.y = clamp(initial.y + dy, 0, initial.y + initial.height - 0.05);
              crop.height = initial.height + initial.y - crop.y;
            }
          }
          this.plan.crop = crop;
          this.render();
        };
        const up = () => {
          box.removeEventListener("pointermove", move);
          box.removeEventListener("pointerup", up);
          box.removeEventListener("pointercancel", up);
        };
        box.addEventListener("pointermove", move);
        box.addEventListener("pointerup", up);
        box.addEventListener("pointercancel", up);
      });
    }

    bindColor() {
      const mode = this.root.querySelector("[data-lighting-mode]");
      const tint = this.root.querySelector("[data-color-wheel]");
      const intensity = this.root.querySelector("[data-color-intensity]");
      const monochrome = this.root.querySelector("[data-black-white]");
      const update = () => {
        this.snapshot();
        this.plan.color = {
          mode: mode?.value || "neutral",
          tint: tint?.value || "#ffffff",
          intensity: number(intensity?.value, 0),
          black_and_white: Boolean(monochrome?.checked),
        };
        this.render();
      };
      mode?.addEventListener("change", () => {
        if (mode.value !== "neutral" && number(intensity?.value, 0) === 0) intensity.value = "45";
        update();
      });
      tint?.addEventListener("input", () => {
        if (tint.value.toLowerCase() !== "#ffffff" && number(intensity?.value, 0) === 0) intensity.value = "45";
        update();
      });
      intensity?.addEventListener("input", update);
      monochrome?.addEventListener("change", update);
      this.strengthInput?.addEventListener("input", () => {
        this.correctionStrength = clamp(number(this.strengthInput.value, 50), 0, 100);
        const output = this.root.querySelector("[data-correction-strength-output]");
        if (output) output.textContent = `${Math.round(this.correctionStrength)}%`;
        this.renderPreviewStyle();
      });
    }

    bindPanels() {
      this.root.querySelectorAll("[data-editor-panel]").forEach((panel) => {
        panel.addEventListener("toggle", () => {
          if (panel.open) {
            this.root.querySelectorAll("[data-editor-panel]").forEach((other) => {
              if (other !== panel) other.open = false;
            });
            this.root.dataset.activeTool = panel.dataset.editorPanel;
          } else if (this.root.dataset.activeTool === panel.dataset.editorPanel) {
            delete this.root.dataset.activeTool;
          }
        });
      });
    }

    bindText() {
      this.root.querySelector("[data-add-text]")?.addEventListener("click", () => {
        if (!this.duration) return;
        const text = this.root.querySelector("[data-text-value]")?.value.trim();
        const start = number(this.root.querySelector("[data-text-start]")?.value, 0);
        const end = number(this.root.querySelector("[data-text-end]")?.value, this.duration);
        if (!text || end - start < 0.04) return;
        const [x, y] = (this.root.querySelector("[data-text-position]")?.value || "0.5,0.85").split(",").map(Number);
        this.snapshot();
        this.plan.text_overlays.push({
          text: text.slice(0, 200), start: clamp(start, 0, this.duration), end: clamp(end, 0, this.duration),
          x, y, size: number(this.root.querySelector("[data-text-size]")?.value, 5),
          color: this.root.querySelector("[data-text-color]")?.value || "#ffffff",
          background: Boolean(this.root.querySelector("[data-text-background]")?.checked),
        });
        this.render();
      });
    }

    enforceTimeline() {
      if (!this.video || this.video.seeking) return;
      const segments = this.getSegments();
      const current = this.video.currentTime;
      if (segments.some(([start, end]) => current >= start && current < end)) {
        this.renderTextPreview();
        return;
      }
      const next = segments.find(([start]) => start > current);
      if (next) this.video.currentTime = next[0];
      else this.video.pause();
      this.renderTextPreview();
    }

    renderPreviewStyle() {
      if (!this.stage) return;
      const strength = this.correctionStrength / 100;
      const exposure = number(this.correction.exposure_stops, 0) * strength;
      const contrast = 1 + (number(this.correction.contrast_multiplier, 1) - 1) * strength;
      const saturation = 1 + (number(this.correction.saturation_multiplier, 1) - 1) * strength;
      const grayscale = this.plan.color.black_and_white ? " grayscale(1)" : "";
      this.stage.style.setProperty("--preview-filter", `brightness(${2 ** exposure}) contrast(${contrast}) saturate(${saturation})${grayscale}`);
      const presets = {
        neutral: "#ffffff", warm: "#ffb28f", cool: "#8abaff", golden_hour: "#ffc071",
        moonlight: "#7599ff", fluorescent: "#8effc1", candlelight: "#ff975f",
      };
      const color = this.plan.color.tint.toLowerCase() === "#ffffff" ? presets[this.plan.color.mode] : this.plan.color.tint;
      this.stage.style.setProperty("--preview-tint", color);
      this.stage.style.setProperty("--preview-tint-strength", String(this.plan.color.intensity / 100 * 0.42));
    }

    renderTextPreview() {
      const layer = this.root.querySelector("[data-text-preview-layer]");
      if (!layer) return;
      const current = this.video?.currentTime || 0;
      layer.replaceChildren();
      this.plan.text_overlays.filter((item) => current >= item.start && current <= item.end).forEach((item) => {
        const node = document.createElement("span");
        node.className = "text-preview";
        node.dataset.background = String(item.background);
        node.textContent = item.text;
        node.style.left = `${item.x * 100}%`;
        node.style.top = `${item.y * 100}%`;
        node.style.setProperty("--overlay-color", item.color);
        node.style.setProperty("--overlay-size", `${Math.max(12, (this.stage?.clientHeight || 360) * item.size / 100)}px`);
        layer.append(node);
      });
    }

    render() {
      this.renderTrimSelection();
      const trimList = this.root.querySelector("[data-trim-list]");
      if (trimList) {
        trimList.replaceChildren();
        this.plan.trims.forEach((item, index) => {
          const li = document.createElement("li");
          const label = document.createElement("span");
          label.textContent = `${item.mode === "keep" ? "Preserve" : "Remove"} ${formatTime(item.start)} to ${formatTime(item.end)}`;
          const button = document.createElement("button");
          button.type = "button";
          button.textContent = "Remove";
          button.addEventListener("click", () => { this.snapshot(); this.plan.trims.splice(index, 1); this.render(); });
          li.append(label, button);
          trimList.append(li);
        });
      }
      const textList = this.root.querySelector("[data-text-list]");
      if (textList) {
        textList.replaceChildren();
        this.plan.text_overlays.forEach((item, index) => {
          const li = document.createElement("li");
          const label = document.createElement("span");
          label.textContent = `“${item.text}” ${formatTime(item.start)} to ${formatTime(item.end)}`;
          const button = document.createElement("button");
          button.type = "button";
          button.textContent = "Remove";
          button.addEventListener("click", () => { this.snapshot(); this.plan.text_overlays.splice(index, 1); this.render(); });
          li.append(label, button);
          textList.append(li);
        });
      }
      const crop = this.plan.crop;
      if (this.stage) {
        this.stage.style.setProperty("--crop-x", crop.x);
        this.stage.style.setProperty("--crop-y", crop.y);
        this.stage.style.setProperty("--crop-width", crop.width);
        this.stage.style.setProperty("--crop-height", crop.height);
      }
      const cropFields = { x: "[data-crop-x]", y: "[data-crop-y]", width: "[data-crop-width]", height: "[data-crop-height]" };
      Object.entries(cropFields).forEach(([name, selector]) => {
        const input = this.root.querySelector(selector);
        if (input) input.value = (crop[name] * 100).toFixed(1);
      });
      const mode = this.root.querySelector("[data-lighting-mode]");
      const tint = this.root.querySelector("[data-color-wheel]");
      const intensity = this.root.querySelector("[data-color-intensity]");
      const monochrome = this.root.querySelector("[data-black-white]");
      if (mode) mode.value = this.plan.color.mode;
      if (tint) tint.value = this.plan.color.tint;
      if (intensity) intensity.value = this.plan.color.intensity;
      if (monochrome) monochrome.checked = this.plan.color.black_and_white;
      const correctionOutput = this.root.querySelector("[data-correction-strength-output]");
      if (correctionOutput) correctionOutput.textContent = `${Math.round(this.correctionStrength)}%`;
      this.renderPreviewStyle();
      this.renderTextPreview();
      this.root.dispatchEvent(new CustomEvent("colorcheck:plan", { detail: this.getPlan() }));
    }
  }

  const editors = [];
  document.querySelectorAll("[data-video-editor]").forEach((root) => {
    const initial = parseScript(root, "[data-initial-plan]", DEFAULT_PLAN);
    const correction = parseScript(root, "[data-correction]", {});
    const editor = new Editor(root, root.querySelector("[data-editor-source]"), initial, correction);
    root.colorCheckEditor = editor;
    editors.push(editor);
  });
  window.ColorCheckEditor = { Editor, retainedSegments, normalizedPlan, editors };
})();
