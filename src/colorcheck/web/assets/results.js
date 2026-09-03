(function () {
  "use strict";

  const progressRoot = document.querySelector("[data-job-progress]");
  if (progressRoot) {
    const jobId = progressRoot.dataset.jobId;
    const stage = progressRoot.querySelector("[data-job-stage]");
    const bar = progressRoot.querySelector("[data-job-progress-bar]");
    const poll = async () => {
      try {
        const response = await fetch(`/api/jobs/${jobId}`, { cache: "no-store" });
        const state = await window.ColorCheckUploads.responseJson(response);
        stage.textContent = state.stage || "Working";
        bar.value = Number(state.progress || 0);
        if (state.status === "complete") window.location.reload();
        else if (state.status === "failed") stage.textContent = state.error || "Analysis failed.";
        else window.setTimeout(poll, 1400);
      } catch (error) {
        stage.textContent = error.message;
        window.setTimeout(poll, 3000);
      }
    };
    poll();
  }

  document.querySelectorAll("[data-video-editor]").forEach((root) => {
    const input = root.querySelector("[data-editor-source]");
    const bar = root.querySelector("[data-render-progress]");
    const status = root.querySelector("[data-render-status]");
    const maxBytes = Number(root.dataset.maxSourceBytes || 0);
    const chunkBytes = Number(root.dataset.chunkBytes || 16 * 1024 * 1024);
    const sourceMetadata = (() => {
      try { return JSON.parse(root.querySelector("[data-source-metadata]")?.textContent || "{}"); }
      catch (_error) { return {}; }
    })();

    root.querySelectorAll("[data-render]").forEach((button) => button.addEventListener("click", async () => {
      if (root.dataset.rendering === "true") return;
      const file = input.files[0];
      if (!file) { status.textContent = "Select the original target clip first."; return; }
      if (file.size > maxBytes) { status.textContent = `The source must be ${Math.floor(maxBytes / 1024 / 1024)} MB or smaller.`; return; }
      if (sourceMetadata.size && Number(sourceMetadata.size) !== file.size) {
        status.textContent = "This does not appear to be the target clip used for the report.";
        return;
      }
      root.dataset.rendering = "true";
      root.querySelectorAll("[data-render]").forEach((item) => { item.disabled = true; });
      bar.hidden = false;
      bar.value = 0;
      try {
        const uploaded = await window.ColorCheckUploads.uploadFile(file, "video", chunkBytes, (ratio) => {
          bar.value = ratio * 90;
          status.textContent = `Uploading source securely: ${Math.round(ratio * 100)}%`;
        });
        const form = document.createElement("form");
        form.method = "post";
        form.action = `/jobs/${root.dataset.jobId}/render/${button.dataset.render}`;
        form.hidden = true;
        [["upload_session", uploaded.session_id], ["upload_token", uploaded.token],
          ["edit_plan", JSON.stringify(root.colorCheckEditor.getPlan())],
          ["apply_correction", button.dataset.correction]].forEach(([name, value]) => {
          const field = document.createElement("input");
          field.name = name; field.value = value; form.append(field);
        });
        document.body.append(form);
        bar.value = 100;
        status.textContent = "Rendering once and streaming the download. Keep this tab open.";
        form.submit();
        window.setTimeout(() => form.remove(), 10000);
      } catch (error) {
        status.textContent = error.message || "The export could not be started.";
      } finally {
        window.setTimeout(() => {
          root.dataset.rendering = "false";
          root.querySelectorAll("[data-render]").forEach((item) => { item.disabled = false; });
        }, 3000);
      }
    }));
  });
})();
