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
    mobile = matchMedia("(max-width: 760px)");
  let mode = mobile.matches ? "bottom" : "right",
    drag = null;
  const buttons = [...document.querySelectorAll("[data-dock-mode]")];

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
    if (mode === "right" && !mobile.matches) {
      panel.style.top = `${Math.max(8, 64 - scrollY)}px`;
      return;
    }
    if (mode !== "floating") return;
    const bounds = panel.getBoundingClientRect();
    panel.style.left = `${Math.max(8, Math.min(bounds.left, innerWidth - bounds.width - 8))}px`;
    panel.style.top = `${Math.max(8, Math.min(bounds.top, innerHeight - bounds.height - 8))}px`;
  }
  function dock(next) {
    if (mobile.matches && next === "right") next = "bottom";
    mode = next;
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
    if (!drag) return;
    panel.style.left = `${drag.left + event.clientX - drag.x}px`;
    panel.style.top = `${drag.top + event.clientY - drag.y}px`;
    keepVisible();
  });
  for (const name of ["pointerup", "pointercancel", "lostpointercapture"])
    grip.addEventListener(name, () => {
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
  mobile.addEventListener("change", () =>
    dock(mobile.matches ? "bottom" : "right"),
  );
  dock(mode);
}
