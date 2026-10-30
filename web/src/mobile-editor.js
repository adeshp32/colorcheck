/** Presentation only: portals retain the original controls and their event handlers. */
export function initializeMobileEditor({
  onViewChange,
  hasPhoto,
  maskIsActive = () => false,
}) {
  const $ = (selector) => document.querySelector(selector),
    make = (tag, className) => {
      const node = document.createElement(tag);
      if (className) node.className = className;
      return node;
    };
  const layout = $("#editor-layout"),
    viewer = $("#viewer"),
    preview = $("#preview"),
    media = matchMedia("(max-width:760px)");
  let active = null,
    marker = null,
    activeRegion = null,
    regionMarker = null,
    returnTarget = null,
    zoom = 1,
    panX = 0,
    panY = 0,
    gesture = null,
    lastTap = 0,
    tapTimer = null,
    sheetDrag = null,
    photoDismiss = null;
  const pointers = new Map(),
    dock = make("section", "single-adjustment"),
    heading = make("div", "single-adjustment-heading"),
    title = make("strong"),
    content = make("div", "single-adjustment-content");
  const transport = $(".transport"),
    transportMarker = document.createComment("transport");
  transport.before(transportMarker);
  function placeTransport() {
    if (media.matches) viewer.append(transport);
    else transportMarker.after(transport);
  }
  placeTransport();
  $("#curve-point-options").open = !media.matches;
  dock.hidden = true;
  dock.setAttribute("aria-label", "Active adjustment");
  const back = make("button"),
    done = make("button"),
    sheetToggle = make("button", "sheet-toggle"),
    overlayToggle = make("button", "region-button");
  overlayToggle.title = "Show mask overlay";
  overlayToggle.setAttribute("aria-label", "Show mask overlay");
  const overlayIcon = make("img", "icon");
  overlayIcon.src = "./assets/icons/icon-eye.svg";
  overlayIcon.alt = "";
  overlayToggle.append(overlayIcon);
  overlayToggle.onclick = () => {
    const checkbox = $("#mask-show");
    checkbox.checked = !checkbox.checked;
    checkbox.dispatchEvent(new Event("change"));
    sync();
  };
  back.textContent = "‹";
  back.title = "Back to tools";
  back.setAttribute("aria-label", "Back to tools");
  done.textContent = "Done";
  sheetToggle.textContent = "⌄";
  sheetToggle.title = "Collapse adjustment";
  sheetToggle.setAttribute("aria-label", "Collapse adjustment");
  sheetToggle.setAttribute("aria-expanded", "true");
  heading.append(back, title, overlayToggle, sheetToggle, done);
  dock.append(heading, content);
  layout.append(dock);
  function restore() {
    if (activeRegion) {
      regionMarker.replaceWith(activeRegion);
      activeRegion = regionMarker = null;
    }
    if (active) {
      marker.replaceWith(active);
      active.classList.remove("focused-control");
      active = null;
      marker = null;
    }
    dock.hidden = true;
    dock.dataset.sheetState = "hidden";
    delete viewer.dataset.toolSwipe;
    viewer.dispatchEvent(new Event("photo-layout-change"));
  }
  function close() {
    restore();
    layout.dataset.tray = "closed";
  }
  function focus(node, name) {
    if (!media.matches) return;
    restore();
    marker = document.createComment("active adjustment");
    node.before(marker);
    active = node;
    node.classList.add("focused-control");
    content.append(node);
    activeRegion = node.querySelector(":scope > .region-button");
    if (activeRegion) {
      regionMarker = document.createComment("active region control");
      activeRegion.before(regionMarker);
      heading.insertBefore(activeRegion, overlayToggle);
    }
    title.textContent = name;
    dock.hidden = false;
    dock.dataset.sheetState = "expanded";
    if (!maskIsActive() && $("#crop-box").hidden)
      viewer.dataset.toolSwipe = "true";
    sheetToggle.textContent = "⌄";
    sheetToggle.title = "Collapse adjustment";
    sheetToggle.setAttribute("aria-label", "Collapse adjustment");
    sheetToggle.setAttribute("aria-expanded", "true");
    layout.dataset.tray = "adjustment";
    sync();
    viewer.dispatchEvent(new Event("photo-layout-change"));
  }
  back.onclick = () => {
    restore();
    layout.dataset.tray = "open";
  };
  done.onclick = close;
  sheetToggle.onclick = () => {
    const expanded = dock.dataset.sheetState === "expanded";
    dock.dataset.sheetState = expanded ? "peek" : "expanded";
    sheetToggle.textContent = expanded ? "⌃" : "⌄";
    sheetToggle.title = expanded ? "Expand adjustment" : "Collapse adjustment";
    sheetToggle.setAttribute("aria-label", sheetToggle.title);
    sheetToggle.setAttribute("aria-expanded", String(!expanded));
    viewer.dispatchEvent(new Event("photo-layout-change"));
    onViewChange();
  };
  heading.addEventListener("pointerdown", (event) => {
    if (!media.matches || event.target.closest("button")) return;
    sheetDrag = { id: event.pointerId, y: event.clientY };
    heading.setPointerCapture(event.pointerId);
  });
  heading.addEventListener("pointermove", (event) => {
    if (sheetDrag?.id !== event.pointerId) return;
    dock.style.setProperty(
      "--sheet-drag-y",
      `${Math.max(-32, event.clientY - sheetDrag.y)}px`,
    );
  });
  for (const eventName of ["pointerup", "pointercancel", "lostpointercapture"])
    heading.addEventListener(eventName, (event) => {
      if (sheetDrag?.id !== event.pointerId) return;
      const delta = event.clientY - sheetDrag.y;
      dock.style.removeProperty("--sheet-drag-y");
      sheetDrag = null;
      if (delta > 150) close();
      else if (delta > 45 && dock.dataset.sheetState === "expanded")
        sheetToggle.click();
      else if (delta < -45 && dock.dataset.sheetState === "peek")
        sheetToggle.click();
    });
  $("#close-tools").addEventListener("click", close);
  for (const button of document.querySelectorAll("[data-panel]"))
    button.addEventListener("click", restore);
  for (const row of document.querySelectorAll(".control")) {
    const label = row.querySelector("label");
    for (const event of ["click", "keydown"])
      label.addEventListener(event, (e) => {
        if (event === "keydown" && !["Enter", " "].includes(e.key)) return;
        if (media.matches) {
          e.preventDefault();
          focus(row, label.textContent);
        }
      });
  }
  for (const [button, id, name] of [
    ["#open-curves", "#curve-panel", "Curves"],
    ["#open-grading", "#grading-panel", "Color wheels"],
    ["#open-color-mixer", "#color-mixer-panel", "Color mixer"],
  ])
    $(button).onclick = () => focus($(id), name);

  const region = make("dialog", "region-picker"),
    regionTitle = make("h2"),
    choice = make("select"),
    actions = make("div", "commands");
  regionTitle.textContent = "Apply to region";
  choice.setAttribute("aria-label", "Adjustment region");
  const use = make("button"),
    cancel = make("button");
  use.textContent = "Use selection";
  cancel.textContent = "Cancel";
  const radial = make("button"),
    linear = make("button");
  radial.textContent = "New radial mask";
  linear.textContent = "New linear mask";
  actions.append(use, radial, linear, cancel);
  region.append(regionTitle, choice, actions);
  layout.append(region);
  let regionControl = null;
  function openRegion(node) {
    regionControl = node;
    choice.replaceChildren(
      ...[...$("#adjustment-scope").options].map(
        (option) => new Option(option.text, option.value),
      ),
    );
    choice.value = $("#adjustment-scope").value;
    region.showModal();
  }
  for (const row of [
    ...document.querySelectorAll(".control"),
    $("#curve-panel"),
    $("#grading-panel"),
    $("#color-mixer-panel"),
  ]) {
    if (
      row.querySelector("#slider-quality") ||
      row.closest("#mask-settings") ||
      row.querySelector('[id^="slider-crop-"]')
    )
      continue;
    const button = make("button", "region-button");
    button.type = "button";
    button.title = "Apply to region";
    button.setAttribute(
      "aria-label",
      `Apply ${row.querySelector("label,h3")?.textContent ?? "adjustment"} to region`,
    );
    const icon = make("img", "icon");
    icon.src = "./assets/icons/icon-scan-line.svg";
    icon.alt = "";
    button.append(icon);
    button.onclick = () => openRegion(row);
    (row.classList.contains("control")
      ? row.querySelector(".control-top")
      : row
    ).append(button);
  }
  use.onclick = () => {
    const scope = $("#adjustment-scope");
    scope.value = choice.value;
    scope.dispatchEvent(new Event("change"));
    region.close();
    sync();
  };
  cancel.onclick = () => region.close();
  const returnButton = make("button", "return-adjustment");
  returnButton.hidden = true;
  viewer.append(returnButton);
  for (const [button, type] of [
    [radial, "radial"],
    [linear, "linear"],
  ])
    button.onclick = () => {
      returnTarget = regionControl;
      region.close();
      restore();
      $("[data-panel=mask]").click();
      $(`#add-${type}`).click();
      returnButton.textContent = `Edit ${returnTarget.querySelector("label,h3")?.textContent ?? "adjustment"}`;
      returnButton.hidden = false;
    };
  returnButton.onclick = () => {
    const node = returnTarget;
    if (!node) return;
    const section = node.closest("[data-section]");
    $(`[data-panel=${section.dataset.section}]`).click();
    focus(node, node.querySelector("label,h3")?.textContent ?? "Adjustment");
    returnButton.hidden = true;
  };

  const viewControls = make("div", "view-controls"),
    viewToggle = make("button", "view-controls-toggle"),
    viewMenu = make("div", "view-controls-menu"),
    zoomOut = make("button"),
    zoomIn = make("button"),
    fit = make("button"),
    fullscreen = make("button");
  viewToggle.textContent = "View";
  viewToggle.title = "View controls";
  viewToggle.setAttribute("aria-label", "View controls");
  viewToggle.setAttribute("aria-expanded", "false");
  viewMenu.hidden = true;
  viewToggle.onclick = () => {
    const expanded = viewToggle.getAttribute("aria-expanded") !== "true";
    viewToggle.setAttribute("aria-expanded", String(expanded));
    viewMenu.hidden = !expanded;
  };
  zoomOut.textContent = "−";
  zoomOut.title = "Zoom out";
  zoomOut.setAttribute("aria-label", "Zoom out");
  zoomIn.textContent = "+";
  zoomIn.title = "Zoom in";
  zoomIn.setAttribute("aria-label", "Zoom in");
  fit.textContent = "Fit";
  fit.title = "Fit image";
  fit.setAttribute("aria-label", "Fit image");
  fullscreen.title = "Fullscreen image";
  fullscreen.setAttribute("aria-label", "Fullscreen image");
  fullscreen.setAttribute("aria-pressed", "false");
  const fullIcon = make("img", "icon");
  fullIcon.src = "./assets/icons/icon-maximize.svg";
  fullIcon.alt = "";
  fullscreen.append(fullIcon);
  viewMenu.append(zoomOut, fit, zoomIn, fullscreen);
  viewControls.append(viewToggle, viewMenu);
  viewer.append(viewControls);
  function paintView() {
    const width = parseFloat(preview.style.width) || 0,
      height = parseFloat(preview.style.height) || 0;
    const maxX = Math.max(0, (width * zoom - viewer.clientWidth) / 2),
      maxY = Math.max(0, (height * zoom - viewer.clientHeight) / 2);
    panX = Math.max(-maxX, Math.min(maxX, panX));
    panY = Math.max(-maxY, Math.min(maxY, panY));
    viewer.style.setProperty("--view-zoom", zoom);
    viewer.style.setProperty("--view-x", `${panX}px`);
    viewer.style.setProperty("--view-y", `${panY}px`);
    fit.textContent = zoom === 1 ? "Fit" : `${Math.round(zoom * 100)}%`;
    viewToggle.textContent = zoom === 1 ? "View" : `${Math.round(zoom * 100)}%`;
    zoomOut.disabled = zoom <= 1;
    zoomIn.disabled = zoom >= 6;
    onViewChange();
  }
  function setZoom(value) {
    zoom = Math.max(1, Math.min(6, value));
    if (zoom === 1) panX = panY = 0;
    paintView();
  }
  zoomOut.onclick = () => setZoom(zoom / 1.4);
  zoomIn.onclick = () => setZoom(zoom * 1.4);
  fit.onclick = () => setZoom(1);
  fullscreen.onclick = async () => {
    const entering = !document.body.classList.contains("image-fullscreen");
    if (entering) {
      document.body.classList.remove("preview-mode");
      document.body.classList.add("image-fullscreen");
      try {
        if (layout.requestFullscreen) await layout.requestFullscreen();
      } catch {
        /* CSS fullscreen remains available when browser fullscreen is unavailable. */
      }
    } else {
      document.body.classList.remove("image-fullscreen");
      if (document.fullscreenElement) await document.exitFullscreen();
    }
    fullscreen.setAttribute("aria-pressed", String(entering));
  };
  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement) {
      document.body.classList.remove("image-fullscreen");
      fullscreen.setAttribute("aria-pressed", "false");
    }
  });
  viewer.addEventListener(
    "pointerdown",
    (event) => {
      if (event.target.closest("button") || !hasPhoto()) return;
      if (maskIsActive()) return;
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (
        media.matches &&
        active &&
        zoom === 1 &&
        $("#crop-box").hidden &&
        (event.target === preview || event.target === viewer)
      )
        photoDismiss = {
          id: event.pointerId,
          x: event.clientX,
          y: event.clientY,
          used: false,
        };
      const values = [...pointers.values()];
      if (values.length === 2) {
        viewer.dataset.navigation = "true";
        viewer.dispatchEvent(new Event("image-navigation"));
        gesture = {
          distance: Math.hypot(
            values[0].x - values[1].x,
            values[0].y - values[1].y,
          ),
          zoom,
          x: panX,
          y: panY,
          cx: (values[0].x + values[1].x) / 2,
          cy: (values[0].y + values[1].y) / 2,
        };
        event.preventDefault();
      } else if (
        zoom > 1 &&
        ($("#mask-overlay").hidden ||
          $("#mask-overlay").style.pointerEvents === "none") &&
        $("#crop-box").hidden
      ) {
        viewer.dataset.navigation = "true";
        gesture = { x: panX, y: panY, cx: event.clientX, cy: event.clientY };
        viewer.setPointerCapture(event.pointerId);
      }
    },
    { capture: true },
  );
  viewer.addEventListener(
    "pointermove",
    (event) => {
      if (!pointers.has(event.pointerId)) return;
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (photoDismiss?.id === event.pointerId && !photoDismiss.used) {
        const dx = event.clientX - photoDismiss.x,
          dy = event.clientY - photoDismiss.y;
        if (!photoDismiss.captured && dy > 12 && dy > Math.abs(dx) * 1.3) {
          viewer.setPointerCapture(event.pointerId);
          photoDismiss.captured = true;
        }
        if (dy > 75 && dy > Math.abs(dx) * 1.3 && pointers.size === 1) {
          photoDismiss.used = true;
          restore();
          layout.dataset.tray = "hidden";
          $("#show-tools").hidden = false;
          document.body.classList.add("image-fullscreen");
          fullscreen.setAttribute("aria-pressed", "true");
          onViewChange();
          event.preventDefault();
          return;
        }
      }
      if (!gesture) return;
      const values = [...pointers.values()];
      if (values.length === 2 && gesture.distance) {
        zoom = Math.max(
          1,
          Math.min(
            6,
            (gesture.zoom *
              Math.hypot(
                values[0].x - values[1].x,
                values[0].y - values[1].y,
              )) /
              Math.max(1, gesture.distance),
          ),
        );
        panX = gesture.x + (values[0].x + values[1].x) / 2 - gesture.cx;
        panY = gesture.y + (values[0].y + values[1].y) / 2 - gesture.cy;
      } else if (values.length === 1 && !gesture.distance) {
        panX = gesture.x + event.clientX - gesture.cx;
        panY = gesture.y + event.clientY - gesture.cy;
      }
      event.preventDefault();
      paintView();
    },
    { capture: true },
  );
  function endPointer(event) {
    const start = pointers.get(event.pointerId);
    const dismissed = photoDismiss?.id === event.pointerId && photoDismiss.used;
    if (photoDismiss?.id === event.pointerId) photoDismiss = null;
    pointers.delete(event.pointerId);
    if (
      event.type === "pointerup" &&
      start &&
      !dismissed &&
      !gesture &&
      $("#crop-box").hidden &&
      !$("#lens-pick")?.checked &&
      event.target === preview
    ) {
      const now = performance.now();
      if (now - lastTap < 300) {
        clearTimeout(tapTimer);
        tapTimer = null;
        setZoom(zoom > 1 ? 1 : 2);
        lastTap = 0;
      } else {
        lastTap = now;
        clearTimeout(tapTimer);
        tapTimer = setTimeout(() => {
          document.body.classList.toggle("preview-mode");
          viewMenu.hidden = true;
          viewToggle.setAttribute("aria-expanded", "false");
          onViewChange();
          tapTimer = null;
        }, 300);
      }
    }
    if (pointers.size < 2) gesture = null;
    if (!pointers.size) delete viewer.dataset.navigation;
  }
  for (const event of ["pointerup", "pointercancel", "lostpointercapture"])
    window.addEventListener(event, endPointer, { capture: true });
  viewer.addEventListener(
    "wheel",
    (event) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      if (maskIsActive()) return;
      setZoom(zoom * (event.deltaY < 0 ? 1.1 : 1 / 1.1));
    },
    { passive: false },
  );
  new ResizeObserver(paintView).observe(viewer);
  media.addEventListener("change", () => {
    restore();
    placeTransport();
    $("#curve-point-options").open = !media.matches;
    paintView();
  });
  function sync() {
    viewControls.hidden = !hasPhoto();
    if (media.matches && active && !maskIsActive() && $("#crop-box").hidden)
      viewer.dataset.toolSwipe = "true";
    else delete viewer.dataset.toolSwipe;
    const scope = $("#adjustment-scope"),
      name = scope.selectedOptions[0]?.text ?? "Whole photo";
    dock.dataset.scope = name;
    overlayToggle.hidden = !scope.value;
    overlayToggle.setAttribute("aria-pressed", String($("#mask-show").checked));
    dock.setAttribute("aria-label", `${title.textContent} · ${name}`);
  }
  return {
    sync,
    resetView() {
      zoom = 1;
      panX = panY = 0;
      returnButton.hidden = true;
      document.body.classList.remove("preview-mode");
      close();
      paintView();
    },
  };
}
