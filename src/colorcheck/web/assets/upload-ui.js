(function () {
  "use strict";

  const form = document.querySelector(".upload-page .analysis-form");
  if (!form) return;
  const button = form.querySelector(".submit");
  const readiness = form.querySelector("[data-upload-readiness]");
  const action = form.querySelector(".run-step");
  const inputs = [...form.querySelectorAll("input[type=file]")];
  const consent = form.elements.rights_confirmed;
  const imageExtensions = /\.(jpe?g|png|webp|tiff?)$/i;
  const videoExtensions = /\.(mp4|mov|m4v|avi|mkv|webm)$/i;

  function fileSize(bytes) {
    const index = Math.min(3, Math.floor(Math.log(Math.max(1, bytes)) / Math.log(1000)));
    const value = (bytes / 1000 ** index).toLocaleString(undefined, { maximumFractionDigits: 1 });
    return `${value} ${["B", "KB", "MB", "GB"][index]}`;
  }

  function updateReadiness() {
    if (form.dataset.submitting === "true") return;
    const selected = inputs.every((input) => input.files.length);
    const valid = selected && inputs.every((input) => input.validity.valid);
    const ready = valid && consent.checked;
    button.disabled = !ready;
    action.dataset.ready = String(ready);
    readiness.textContent = !selected ? "Awaiting files" : !valid
      ? "Check the selected files" : !consent.checked ? "Confirm file permissions" : "Ready to analyze";
  }

  for (const input of inputs) {
    const step = input.closest("[data-file-step]");
    const drop = step.querySelector("[data-file-drop]");
    const name = step.querySelector("[data-file-name]");
    const metadata = step.querySelector("[data-file-meta]");
    const remove = step.querySelector("[data-file-remove]");
    const defaultName = name.textContent;
    const defaultMetadata = metadata.textContent;

    function syncFile() {
      const file = input.files[0];
      const limit = Number(input.name === "reference" && file && imageExtensions.test(file.name)
        ? form.dataset.maxImageBytes : form.dataset.maxSourceBytes);
      const supported = !file || videoExtensions.test(file.name)
        || (input.name === "reference" && imageExtensions.test(file.name));
      const error = !file ? "" : !supported ? "Unsupported file format."
        : file.size === 0 ? "This file is empty." : file.size > limit
        ? `Maximum ${Math.floor(limit / 1_000_000)} MB per file.` : "";
      input.setCustomValidity(error);
      step.dataset.selected = String(Boolean(file));
      step.dataset.invalid = String(Boolean(error));
      name.textContent = file ? file.name : defaultName;
      name.title = file ? file.name : "";
      metadata.textContent = error || (file
        ? `${fileSize(file.size)} · Selected`
        : defaultMetadata);
      remove.hidden = !file;
      updateReadiness();
    }

    input.addEventListener("change", syncFile);
    remove.addEventListener("click", () => {
      if (form.dataset.submitting === "true") return;
      input.value = "";
      input.dispatchEvent(new Event("change", { bubbles: true }));
      input.focus();
    });
    for (const eventName of ["dragenter", "dragover"]) {
      drop.addEventListener(eventName, (event) => {
        event.preventDefault();
        if (form.dataset.submitting !== "true") drop.dataset.dragging = "true";
      });
    }
    drop.addEventListener("dragleave", () => { drop.dataset.dragging = "false"; });
    drop.addEventListener("drop", (event) => {
      event.preventDefault();
      drop.dataset.dragging = "false";
      if (form.dataset.submitting === "true" || !event.dataTransfer?.files.length) return;
      const selection = new DataTransfer();
      selection.items.add(event.dataTransfer.files[0]);
      input.files = selection.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    syncFile();
  }
  consent.addEventListener("change", updateReadiness);
})();
