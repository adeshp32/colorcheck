(function () {
  "use strict";

  const form = document.querySelector(".analysis-form");
  if (!form) return;

  const button = form.querySelector(".submit");
  const progress = form.querySelector(".processing-progress");
  const note = form.querySelector(".processing-note");
  const referenceInput = form.querySelector("[name=reference]");
  const targetInput = form.querySelector("[name=video]");
  const maxSourceBytes = Number(form.dataset.maxSourceBytes || 0);

  function status(message, value) {
    note.textContent = message;
    note.hidden = false;
    progress.hidden = false;
    progress.value = value;
  }

  function loadVideo(file) {
    return new Promise((resolve, reject) => {
      const video = document.createElement("video");
      const url = URL.createObjectURL(file);
      video.preload = "metadata";
      video.muted = true;
      video.playsInline = true;
      video.src = url;
      video.addEventListener("loadedmetadata", () => resolve({ video, url }), { once: true });
      video.addEventListener("error", () => {
        URL.revokeObjectURL(url);
        reject(new Error("This browser could not decode the selected video."));
      }, { once: true });
    });
  }

  function seek(video, time) {
    return new Promise((resolve, reject) => {
      const done = () => resolve();
      const failed = () => reject(new Error("A frame could not be decoded locally."));
      video.addEventListener("seeked", done, { once: true });
      video.addEventListener("error", failed, { once: true });
      video.currentTime = Math.max(0, Math.min(time, Math.max(0, video.duration - 0.002)));
    });
  }

  function canvasFor(width, height, maxSide) {
    const scale = Math.min(1, maxSide / Math.max(width, height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(2, Math.round(width * scale));
    canvas.height = Math.max(2, Math.round(height * scale));
    return canvas;
  }

  function blobFromCanvas(canvas) {
    return new Promise((resolve, reject) => canvas.toBlob(
      (blob) => blob ? resolve(blob) : reject(new Error("A sample image could not be created.")),
      "image/jpeg",
      0.88,
    ));
  }

  function signature(source) {
    const canvas = canvasFor(source.videoWidth || source.width, source.videoHeight || source.height, 32);
    const context = canvas.getContext("2d", { willReadFrequently: true });
    context.drawImage(source, 0, 0, canvas.width, canvas.height);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    const bins = new Float32Array(16);
    let red = 0; let green = 0; let blue = 0; let luma = 0; let saturation = 0;
    for (let index = 0; index < pixels.length; index += 4) {
      const r = pixels[index] / 255; const g = pixels[index + 1] / 255; const b = pixels[index + 2] / 255;
      const y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
      red += r; green += g; blue += b; luma += y;
      saturation += Math.max(r, g, b) - Math.min(r, g, b);
      bins[Math.min(15, Math.floor(y * 16))] += 1;
    }
    const count = pixels.length / 4;
    return [red / count, green / count, blue / count, luma / count, saturation / count,
      ...Array.from(bins, (value) => value / count)];
  }

  function distance(a, b) {
    return Math.sqrt(a.reduce((sum, value, index) => sum + (value - b[index]) ** 2, 0));
  }

  function diverse(items, count) {
    if (items.length <= count) return items;
    const chosen = [items[0], items[items.length - 1]];
    const remaining = items.slice(1, -1);
    while (chosen.length < count && remaining.length) {
      let bestIndex = 0; let bestDistance = -1;
      remaining.forEach((item, index) => {
        const nearest = Math.min(...chosen.map((selected) => distance(item.signature, selected.signature)));
        if (nearest > bestDistance) { bestDistance = nearest; bestIndex = index; }
      });
      chosen.push(remaining.splice(bestIndex, 1)[0]);
    }
    return chosen.sort((a, b) => a.time - b.time);
  }

  function sampleTimes(segments, count) {
    const lengths = segments.map(([start, end]) => Math.max(0, end - start));
    const total = lengths.reduce((sum, value) => sum + value, 0);
    if (!total) return [];
    return Array.from({ length: count }, (_, index) => {
      let position = count === 1 ? total / 2 : total * index / (count - 1);
      for (let segmentIndex = 0; segmentIndex < segments.length; segmentIndex += 1) {
        if (position <= lengths[segmentIndex] || segmentIndex === segments.length - 1) {
          return segments[segmentIndex][0] + Math.min(position, lengths[segmentIndex]);
        }
        position -= lengths[segmentIndex];
      }
      return segments[segments.length - 1][1];
    });
  }

  async function videoSamples(file, desired, segmentsOverride) {
    const { video, url } = await loadVideo(file);
    try {
      const segments = segmentsOverride?.length ? segmentsOverride : [[0, video.duration]];
      const candidateCount = Math.min(96, Math.max(12, desired * 2));
      const candidates = [];
      for (const [index, time] of sampleTimes(segments, candidateCount).entries()) {
        await seek(video, time);
        const canvas = canvasFor(video.videoWidth, video.videoHeight, 512);
        canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
        candidates.push({ time, canvas, signature: signature(video) });
        status(`Selecting representative frames locally (${index + 1}/${candidateCount})`, 8 + index / candidateCount * 35);
      }
      const selected = diverse(candidates, desired);
      const blobs = await Promise.all(selected.map((item) => blobFromCanvas(item.canvas)));
      return {
        blobs,
        times: selected.map((item) => item.time),
        metadata: { duration: video.duration, width: video.videoWidth, height: video.videoHeight },
      };
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  async function imageSample(file) {
    const bitmap = await createImageBitmap(file);
    try {
      const canvas = canvasFor(bitmap.width, bitmap.height, 512);
      canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      return [await blobFromCanvas(canvas)];
    } finally {
      bitmap.close();
    }
  }

  function appendSamples(data, name, blobs) {
    blobs.forEach((blob, index) => data.append(name, blob, `${name}-${index}.jpg`));
  }

  async function localAnalysis(reference, target, desired) {
    const plan = {};
    const targetResult = await videoSamples(target, desired, []);
    let referenceBlobs;
    if (reference.type.startsWith("image/")) referenceBlobs = await imageSample(reference);
    else referenceBlobs = (await videoSamples(reference, Math.min(8, desired), null)).blobs;

    status("Uploading compact analysis samples", 55);
    const data = new FormData();
    appendSamples(data, "reference_samples", referenceBlobs);
    appendSamples(data, "target_samples", targetResult.blobs);
    data.append("sample_metadata", JSON.stringify({
      target_timestamps: targetResult.times,
      source: { size: target.size, type: target.type, ...targetResult.metadata },
    }));
    data.append("edit_plan", JSON.stringify(plan));
    data.append("samples", String(desired));
    data.append("strength", form.elements.strength.value);
    data.append("lighting_threshold", form.elements.lighting_threshold.value);
    data.append("rights_confirmed", "true");
    const response = await fetch("/api/jobs/samples", { method: "POST", body: data });
    try {
      return await window.ColorCheckUploads.responseJson(response);
    } catch (error) {
      error.noFallback = true;
      throw error;
    }
  }

  async function serverFallback(reference, target, desired) {
    const chunkBytes = Number(form.dataset.chunkBytes || 16 * 1024 * 1024);
    status("Uploading reference for server-side fallback", 8);
    const referenceUpload = await window.ColorCheckUploads.uploadFile(reference, "reference", chunkBytes, (ratio) => status("Uploading reference", 8 + ratio * 18));
    let targetUpload;
    try {
      targetUpload = await window.ColorCheckUploads.uploadFile(target, "video", chunkBytes, (ratio) => status("Uploading source clip", 26 + ratio * 62));
      const response = await fetch("/api/jobs/from-uploads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reference: referenceUpload,
          video: targetUpload,
          samples: desired,
          strength: Number(form.elements.strength.value),
          lighting_threshold: Number(form.elements.lighting_threshold.value),
          rights_confirmed: true,
          edit_plan: {},
          source_metadata: { size: target.size, type: target.type },
        }),
      });
      return await window.ColorCheckUploads.responseJson(response);
    } catch (error) {
      await Promise.all([
        window.ColorCheckUploads.cancel(referenceUpload),
        window.ColorCheckUploads.cancel(targetUpload),
      ]);
      throw error;
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (form.dataset.submitting === "true" || !form.reportValidity()) return;
    const reference = referenceInput.files[0];
    const target = targetInput.files[0];
    if (!reference || !target) return;
    if (target.size > maxSourceBytes || reference.size > maxSourceBytes) {
      note.textContent = `Each source file must be ${Math.floor(maxSourceBytes / 1024 / 1024)} MB or smaller.`;
      note.hidden = false;
      return;
    }
    form.dataset.submitting = "true";
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.textContent = "Running ColorCheck...";
    try {
      let result;
      try {
        status("Decoding representative frames on this device", 4);
        result = await localAnalysis(reference, target, Number(form.elements.samples.value));
      } catch (localError) {
        if (localError.noFallback) throw localError;
        console.info("Local sampling unavailable; using resumable source upload.", localError);
        result = await serverFallback(reference, target, Number(form.elements.samples.value));
      }
      status("Analysis queued", 100);
      window.location.assign(result.job_url);
    } catch (error) {
      note.textContent = error.message || "The request could not be started.";
      note.hidden = false;
      progress.hidden = true;
      form.dataset.submitting = "false";
      button.disabled = false;
      button.removeAttribute("aria-busy");
      button.textContent = button.dataset.defaultLabel;
    }
  });
})();
