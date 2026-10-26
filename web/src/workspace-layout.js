/** Display sizing only: never resize the source pixels or export canvas. */
export function fitPreviewDimensions(
  width,
  height,
  availableWidth,
  availableHeight,
) {
  if (
    ![width, height, availableWidth, availableHeight].every(
      (v) => Number.isFinite(v) && v > 0,
    )
  )
    return { width: 0, height: 0 };
  const scale = Math.min(1, availableWidth / width, availableHeight / height);
  return { width: width * scale, height: height * scale };
}

export function initializeWorkspaceLayout(onPreviewLayout) {
  const layout = document.querySelector("#editor-layout"),
    panel = document.querySelector("#editing-tools"),
    viewer = document.querySelector("#viewer"),
    preview = document.querySelector("#preview"),
    grip = document.querySelector("#panel-grip"),
    showTools = document.querySelector("#show-tools"),
    restoreTools = document.querySelector("#restore-tools"),
    mobile = matchMedia("(max-width: 760px)");
  let mode = mobile.matches ? "bottom" : "right",
    drag = null,
    sheetDrag = null;
  const buttons = [...document.querySelectorAll("[data-dock-mode]")];
  function toggleAdjustment(label) {
    if (!mobile.matches) return;
    const row = label.closest(".control"),
      open = row.dataset.expanded !== "true";
    panel.querySelectorAll(".control").forEach((control) => {
      control.dataset.expanded = "false";
      control.querySelector("label")?.setAttribute("aria-expanded", "false");
    });
    row.dataset.expanded = String(open);
    label.setAttribute("aria-expanded", String(open));
  }
  panel.querySelectorAll(".control-top label").forEach((label) => {
    label.addEventListener("click", (event) => {
      if (mobile.matches) {
        event.preventDefault();
        toggleAdjustment(label);
      }
    });
    label.addEventListener("keydown", (event) => {
      if (mobile.matches && ["Enter", " "].includes(event.key)) {
        event.preventDefault();
        toggleAdjustment(label);
      }
    });
  });
  function adjustmentAccessibility() {
    panel.querySelectorAll(".control-top label").forEach((label) => {
      if (mobile.matches) {
        label.setAttribute("role", "button");
        label.setAttribute("aria-label", label.textContent);
        label.tabIndex = 0;
        label.setAttribute(
          "aria-expanded",
          String(label.closest(".control").dataset.expanded === "true"),
        );
      } else {
        label.removeAttribute("role");
        label.removeAttribute("aria-label");
        label.removeAttribute("tabindex");
        label.removeAttribute("aria-expanded");
      }
    });
  }
  function setTray(state) {
    layout.dataset.tray = state;
    showTools.hidden = !(mobile.matches && state === "hidden");
    updateExpanded();
    onPreviewLayout();
  }
  setTray(mobile.matches ? "closed" : "open");
  for (const button of document.querySelectorAll("[data-panel]"))
    button.addEventListener("click", () => {
      if (!mobile.matches) return;
      const same = layout.dataset.activeTool === button.dataset.panel;
      setTray(same && layout.dataset.tray === "open" ? "closed" : "open");
      layout.dataset.activeTool = button.dataset.panel;
    });
  function updateExpanded() {
    document
      .querySelectorAll("[data-panel]")
      .forEach((button) =>
        button.setAttribute(
          "aria-expanded",
          String(
            !mobile.matches ||
              (layout.dataset.tray === "open" &&
                layout.dataset.activeTool === button.dataset.panel),
          ),
        ),
      );
  }
  document.querySelector("#close-tools").onclick = () => {
    if (mobile.matches) {
      setTray("closed");
      return;
    }
    layout.dataset.toolVisibility = "hidden";
    restoreTools.hidden = false;
    fitPreview();
  };
  restoreTools.onclick = () => {
    layout.dataset.toolVisibility = "open";
    restoreTools.hidden = true;
    dock("right");
    document.querySelector("#close-tools").focus();
  };
  showTools.onclick = () => setTray("closed");

  function fitPreview() {
    const fitted = fitPreviewDimensions(
      preview.width,
      preview.height,
      Math.max(0, viewer.clientWidth - 24),
      Math.max(0, viewer.clientHeight - 24),
    );
    preview.style.width = `${fitted.width}px`;
    preview.style.height = `${fitted.height}px`;
    onPreviewLayout();
  }
  function keepVisible() {
    if (mode !== "floating") return;
    const bounds = panel.getBoundingClientRect();
    panel.style.left = `${Math.max(8, Math.min(bounds.left, innerWidth - bounds.width - 8))}px`;
    panel.style.top = `${Math.max(8, Math.min(bounds.top, innerHeight - bounds.height - 8))}px`;
  }
  function dock(next) {
    if (mobile.matches && next === "right") next = "bottom";
    mode = next;
    if (next === "floating") layout.dataset.tray = "open";
    layout.dataset.dock = next;
    panel.style.cssText = "";
    buttons.forEach((button) =>
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.dockMode === next),
      ),
    );
    if (next === "floating") {
      panel.style.left = `${Math.max(8, innerWidth - panel.offsetWidth - 24)}px`;
      panel.style.top = "80px";
    }
    keepVisible();
    fitPreview();
  }
  buttons.forEach((button) =>
    button.addEventListener("click", () => dock(button.dataset.dockMode)),
  );
  grip.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    if (mobile.matches) {
      sheetDrag = {
        id: event.pointerId,
        y: event.clientY,
        state: layout.dataset.tray,
      };
      grip.setPointerCapture(event.pointerId);
      return;
    }
    const previous = panel.getBoundingClientRect();
    if (mode !== "floating") {
      dock("floating");
      panel.style.left = `${Math.min(previous.left, innerWidth - panel.offsetWidth - 8)}px`;
      panel.style.top = `${previous.top}px`;
      keepVisible();
    }
    const bounds = panel.getBoundingClientRect();
    drag = {
      x: event.clientX,
      y: event.clientY,
      left: bounds.left,
      top: bounds.top,
    };
    grip.setPointerCapture(event.pointerId);
  });
  grip.addEventListener("pointermove", (event) => {
    if (sheetDrag?.id === event.pointerId) {
      panel.style.setProperty(
        "--panel-drag-y",
        `${Math.max(-48, event.clientY - sheetDrag.y)}px`,
      );
      return;
    }
    if (!drag) return;
    panel.style.left = `${drag.left + event.clientX - drag.x}px`;
    panel.style.top = `${drag.top + event.clientY - drag.y}px`;
    keepVisible();
  });
  for (const name of ["pointerup", "pointercancel", "lostpointercapture"])
    grip.addEventListener(name, (event) => {
      if (sheetDrag?.id === event.pointerId) {
        const delta = event.clientY - sheetDrag.y;
        panel.style.removeProperty("--panel-drag-y");
        const previous = sheetDrag.state;
        sheetDrag = null;
        if (delta < -55) setTray("open");
        else if (delta > 150 || (previous === "closed" && delta > 70))
          setTray("hidden");
        else if (delta > 45) setTray("closed");
        return;
      }
      drag = null;
    });
  grip.addEventListener("keydown", (event) => {
    const delta = {
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
      ArrowUp: [0, -1],
      ArrowDown: [0, 1],
    }[event.key];
    if (!delta) return;
    event.preventDefault();
    if (mode !== "floating") dock("floating");
    const bounds = panel.getBoundingClientRect(),
      step = event.shiftKey ? 40 : 10;
    panel.style.left = `${bounds.left + delta[0] * step}px`;
    panel.style.top = `${bounds.top + delta[1] * step}px`;
    keepVisible();
  });
  new ResizeObserver(fitPreview).observe(viewer);
  new ResizeObserver(keepVisible).observe(panel);
  // Canvas attributes change when a crop or rotation changes the preview aspect ratio.
  new MutationObserver(fitPreview).observe(preview, {
    attributes: true,
    attributeFilter: ["width", "height", "hidden"],
  });
  addEventListener("resize", () => {
    keepVisible();
    fitPreview();
  });
  addEventListener("scroll", keepVisible, { passive: true });
  mobile.addEventListener("change", () => {
    layout.dataset.toolVisibility = "open";
    restoreTools.hidden = true;
    setTray(mobile.matches ? "closed" : "open");
    dock(mobile.matches ? "bottom" : "right");
    adjustmentAccessibility();
  });
  dock(mode);
  updateExpanded();
  adjustmentAccessibility();
}
