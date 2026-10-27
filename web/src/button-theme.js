const DEFAULT_COLOR = "#7777ff";
const STORAGE_KEY = "colorcheck-button-theme";

export function normalizeHex(value) {
  return /^#[0-9a-f]{6}$/i.test(value) ? value.toLowerCase() : null;
}

function channels(hex) {
  return [1, 3, 5].map((index) => parseInt(hex.slice(index, index + 2), 16));
}

function luminance(rgb) {
  const linear = rgb.map((value) => {
    const channel = value / 255;
    return channel <= 0.04045
      ? channel / 12.92
      : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
}

function contrast(first, second) {
  const [lighter, darker] = [luminance(first), luminance(second)].sort(
    (a, b) => b - a,
  );
  return (lighter + 0.05) / (darker + 0.05);
}

function hexFromChannels(rgb) {
  return `#${rgb.map((value) => Math.round(value).toString(16).padStart(2, "0")).join("")}`;
}

export function resolveThemeColors(value) {
  const selected = normalizeHex(value) ?? DEFAULT_COLOR;
  const rgb = channels(selected);
  const surface = channels("#28282e");
  let accent = rgb;
  if (contrast(accent, surface) < 4.6) {
    let low = 0;
    let high = 1;
    for (let step = 0; step < 16; step++) {
      const middle = (low + high) / 2;
      const candidate = rgb.map(
        (channel) => channel + (255 - channel) * middle,
      );
      if (contrast(candidate, surface) >= 4.6) high = middle;
      else low = middle;
    }
    accent = rgb.map((channel) => channel + (255 - channel) * high);
  }
  const darkInk = channels("#111115");
  const lightInk = channels("#ffffff");
  return {
    selected,
    accent: hexFromChannels(accent),
    ink:
      contrast(accent, darkInk) >= contrast(accent, lightInk)
        ? "#111115"
        : "#ffffff",
  };
}

export function initializeButtonTheme() {
  const menu = document.querySelector("#button-theme");
  const picker = document.querySelector("#theme-color");
  const hexField = document.querySelector("#theme-hex");
  const presets = [...menu.querySelectorAll("[data-theme-color]")];

  function apply(value) {
    const theme = resolveThemeColors(value);
    document.documentElement.style.setProperty("--accent", theme.accent);
    document.documentElement.style.setProperty("--accent-ink", theme.ink);
    picker.value = theme.selected;
    hexField.value = theme.selected.toUpperCase();
    hexField.setAttribute("aria-invalid", "false");
    for (const preset of presets) {
      preset.setAttribute(
        "aria-pressed",
        String(preset.dataset.themeColor === theme.selected),
      );
    }
    try {
      localStorage.setItem(STORAGE_KEY, theme.selected);
    } catch {
      // The preference remains usable when browser storage is unavailable.
    }
  }

  for (const preset of presets) {
    preset.style.setProperty("--preset", preset.dataset.themeColor);
    preset.addEventListener("click", () => apply(preset.dataset.themeColor));
  }
  picker.addEventListener("input", () => apply(picker.value));
  hexField.addEventListener("change", () => {
    const value = normalizeHex(hexField.value.trim());
    if (value) apply(value);
    else hexField.setAttribute("aria-invalid", "true");
  });
  document
    .querySelector("#theme-reset")
    .addEventListener("click", () => apply(DEFAULT_COLOR));
  document.addEventListener("pointerdown", (event) => {
    if (menu.open && !menu.contains(event.target)) menu.open = false;
  });
  menu.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      menu.open = false;
      menu.querySelector("summary").focus();
    }
  });

  let stored;
  try {
    stored = localStorage.getItem(STORAGE_KEY);
  } catch {
    // Private browsing can block storage reads too.
  }
  apply(normalizeHex(stored) ?? DEFAULT_COLOR);
}
