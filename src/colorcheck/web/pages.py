from __future__ import annotations

import html

LINKEDIN_URL = "https://www.linkedin.com/in/aditya-deshpande-127218205/"


def page_shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <link rel="icon" href="/assets/colorcheck-mark.svg" type="image/svg+xml">
  <style>
    :root {{
      --bg: #f9f8ff;
      --bg-elevated: rgba(255, 255, 255, 0.58);
      --glass-strong: rgba(255, 255, 255, 0.74);
      --ink: #17172b;
      --muted: #5e6078;
      --line: rgba(92, 92, 255, 0.18);
      --accent: #5C5CFF;
      --accent-strong: #3d3dcc;
      --accent-soft: #ececff;
      --third: #8ac8bb;
      --third-strong: #4f9186;
      --third-soft: #e9f8f4;
      --cream: rgba(255, 255, 255, 0.62);
      --shadow: 0 28px 80px rgba(45, 45, 150, 0.16);
      --focus: #1a5cff;
      --tool-font: "Avenir Next", "Nunito Sans", "Helvetica Neue", ui-sans-serif, system-ui, sans-serif;
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: var(--font-scale, 16px);
      line-height: 1.5;
      color: var(--ink);
      background: var(--bg);
    }}
    [data-theme="dark"] {{
      --bg: #0f1024;
      --bg-elevated: rgba(22, 22, 48, 0.62);
      --glass-strong: rgba(28, 28, 62, 0.76);
      --ink: #f8f7ff;
      --muted: #c9c8e2;
      --line: rgba(188, 188, 255, 0.22);
      --accent: #8b8bff;
      --accent-strong: #b4b4ff;
      --accent-soft: rgba(92, 92, 255, 0.22);
      --third: #9bd8cc;
      --third-strong: #b8eee5;
      --third-soft: rgba(138, 200, 187, 0.16);
      --cream: rgba(255, 255, 255, 0.08);
      --shadow: 0 24px 70px rgba(0, 0, 0, 0.34);
      --focus: #9fc0ff;
      color-scheme: dark;
    }}
    [data-contrast="high"] {{
      --line: currentColor;
      --muted: var(--ink);
      --shadow: none;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      min-height: 100vh;
      margin: 0;
      background:
        linear-gradient(120deg, rgba(255, 255, 255, 0.92), rgba(255, 255, 255, 0.16) 38%, rgba(92, 92, 255, 0.26)),
        linear-gradient(160deg, #fffdfd 0%, #f1efff 44%, #5C5CFF 100%);
    }}
    [data-theme="dark"] body {{
      background:
        linear-gradient(120deg, rgba(15,16,36,0.94), rgba(15,16,36,0.46) 42%, rgba(92, 92, 255, 0.22)),
        linear-gradient(160deg, #0f1024 0%, #1e214a 48%, #4a49cc 100%);
    }}
    a {{ color: var(--accent-strong); }}
    button, input, output {{ font: inherit; }}
    :focus-visible {{
      outline: 3px solid var(--focus);
      outline-offset: 4px;
    }}
    .skip {{
      position: fixed;
      left: 16px;
      top: 12px;
      z-index: 10;
      transform: translateY(-140%);
      background: var(--ink);
      color: var(--bg);
      padding: 10px 12px;
      border-radius: 8px;
    }}
    .skip:focus {{ transform: translateY(0); }}
    .topbar {{
      position: sticky;
      top: 0;
      z-index: 4;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px clamp(18px, 4vw, 48px);
      backdrop-filter: blur(18px);
      background: color-mix(in srgb, var(--bg) 72%, transparent);
      border-bottom: 1px solid var(--line);
    }}
    .brand {{
      display: inline-flex;
      align-items: center;
      text-decoration: none;
    }}
    .brand-logo {{
      display: block;
      width: 142px;
      height: auto;
    }}
    [data-theme="dark"] .brand-logo {{
      filter: brightness(1.28);
    }}
    nav {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    nav a, .icon-button {{
      border: 1px solid var(--line);
      border-radius: 999px;
      background: color-mix(in srgb, var(--bg-elevated) 82%, transparent);
      color: var(--ink);
      text-decoration: none;
      padding: 9px 12px;
      min-height: 40px;
    }}
    .icon-button {{ cursor: pointer; }}
    .page {{
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
    }}
    .hero {{
      min-height: min(720px, calc(86vh - 78px));
      display: grid;
      grid-template-columns: minmax(0, 0.92fr) minmax(320px, 1.08fr);
      gap: clamp(22px, 4vw, 52px);
      align-items: center;
      padding: clamp(28px, 4vw, 56px) 0 48px;
    }}
    .eyebrow {{
      width: fit-content;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--glass-strong);
      color: var(--accent-strong);
      font-size: 0.86rem;
      font-weight: 800;
      padding: 8px 12px;
      margin-bottom: 18px;
    }}
    h1 {{
      max-width: 12ch;
      margin: 0;
      font-size: clamp(2.65rem, 5.8vw, 5.25rem);
      line-height: 0.96;
      letter-spacing: 0;
    }}
    .lede {{
      max-width: 54ch;
      color: var(--muted);
      font-size: clamp(1.05rem, 2vw, 1.3rem);
      margin: 16px 0 0;
    }}
    .descriptor {{
      max-width: 54ch;
      margin: 14px 0 0;
      font-weight: 850;
    }}
    .panel {{
      border: 1px solid var(--line);
      border-radius: 18px;
      background: var(--bg-elevated);
      box-shadow: var(--shadow);
      backdrop-filter: blur(26px);
      overflow: hidden;
    }}
    .analysis-panel {{
      position: relative;
      font-family: var(--tool-font);
      border-color: rgba(255, 255, 255, 0.62);
      background:
        linear-gradient(145deg, rgba(255,255,255,0.84), rgba(255,255,255,0.36)),
        linear-gradient(160deg, rgba(92, 92, 255, 0.10), rgba(138, 200, 187, 0.10));
      box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.86),
        inset 0 -1px 0 rgba(92,92,255,0.12),
        0 28px 82px rgba(56, 56, 168, 0.22);
      transition: border-color 180ms ease, box-shadow 180ms ease;
    }}
    .analysis-panel::before {{
      content: "";
      position: absolute;
      inset: 0 0 auto;
      height: 5px;
      background: linear-gradient(
        90deg,
        #5c5cff 0 28%,
        #d989a0 28% 52%,
        #8ac8bb 52% 76%,
        #f1c879 76% 100%
      );
    }}
    .analysis-panel:focus-within {{
      border-color: color-mix(in srgb, var(--accent) 52%, white);
      box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.86),
        0 30px 86px rgba(56, 56, 168, 0.25);
    }}
    [data-theme="dark"] .analysis-panel {{
      border-color: rgba(188, 188, 255, 0.22);
      background:
        linear-gradient(145deg, rgba(35, 36, 74, 0.74), rgba(18, 19, 44, 0.58)),
        linear-gradient(160deg, rgba(92, 92, 255, 0.18), rgba(138, 200, 187, 0.08));
    }}
    .tool-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 22px 18px 18px;
      border-bottom: 1px solid var(--line);
    }}
    .tool-head-actions {{
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
    }}
    .palette-swatches {{
      display: grid;
      grid-template-columns: repeat(4, 18px);
      gap: 4px;
      padding: 5px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--cream);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.72);
    }}
    .palette-swatches span {{
      width: 18px;
      height: 22px;
      border-radius: 4px;
      border: 1px solid rgba(23, 23, 43, 0.12);
    }}
    .palette-swatches span:nth-child(1) {{ background: #5c5cff; }}
    .palette-swatches span:nth-child(2) {{ background: #d989a0; }}
    .palette-swatches span:nth-child(3) {{ background: #8ac8bb; }}
    .palette-swatches span:nth-child(4) {{ background: #f1c879; }}
    .status-pill {{
      border-radius: 999px;
      background: linear-gradient(135deg, var(--accent-soft), var(--third-soft));
      color: var(--accent-strong);
      font-weight: 800;
      padding: 8px 12px;
      white-space: nowrap;
    }}
    form {{ display: grid; gap: 16px; padding: 18px; }}
    .analysis-form {{
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 18px;
      padding: 20px;
    }}
    label {{ display: grid; gap: 8px; font-weight: 800; }}
    .field-reference, .field-target {{ min-width: 0; }}
    .field-samples {{ min-width: 0; }}
    .hint {{ color: var(--muted); font-size: 0.92rem; font-weight: 550; }}
    input[type="file"], input[type="number"] {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: var(--cream);
      color: var(--ink);
      min-height: 54px;
      padding: 13px 14px;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.76);
      transition: border-color 160ms ease, background-color 160ms ease;
    }}
    input[type="file"]:hover, input[type="number"]:hover {{
      border-color: color-mix(in srgb, var(--accent) 44%, var(--line));
      background: color-mix(in srgb, var(--cream) 88%, var(--accent-soft));
    }}
    input[type="range"] {{
      width: 100%;
      accent-color: var(--accent);
    }}
    .range-box {{
      display: grid;
      gap: 10px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: var(--cream);
      min-height: 54px;
      padding: 13px 14px;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.76);
    }}
    .range-meta {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      color: var(--muted);
      font-size: 0.82rem;
      font-weight: 750;
    }}
    .range-meta output {{
      color: var(--accent-strong);
      font-weight: 950;
    }}
    .field-action {{ align-self: end; display: grid; gap: 10px; }}
    .consent {{
      display: flex;
      grid-template-columns: none;
      align-items: flex-start;
      gap: 10px;
      color: var(--muted);
      font-size: 0.82rem;
      font-weight: 650;
    }}
    .consent input {{ width: 18px; height: 18px; margin: 2px 0 0; accent-color: var(--accent); }}
    .submit {{
      width: 100%;
      min-height: 58px;
      align-self: end;
      border: 2px solid var(--accent);
      border-radius: 18px;
      background: transparent;
      color: #17172b;
      cursor: pointer;
      font-weight: 900;
      padding: 15px 18px;
      box-shadow: none;
      transition: background-color 160ms ease, color 160ms ease, transform 160ms ease;
    }}
    .submit:hover {{
      background: var(--accent);
      color: #17172b;
      transform: translateY(-1px);
    }}
    .submit:active,
    .submit[aria-busy="true"] {{
      background: var(--accent);
      color: #ffffff;
      transform: translateY(0);
    }}
    .submit:disabled {{ cursor: wait; opacity: 1; }}
    .mini-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      border-top: 1px solid var(--line);
      background: color-mix(in srgb, var(--glass-strong) 74%, transparent);
    }}
    .mini-grid div {{ padding: 14px 18px; border-right: 1px solid var(--line); }}
    .mini-grid div:nth-child(1) {{ box-shadow: inset 0 3px #d989a0; }}
    .mini-grid div:nth-child(2) {{ box-shadow: inset 0 3px var(--accent); }}
    .mini-grid div:nth-child(3) {{ box-shadow: inset 0 3px var(--third); }}
    .mini-grid div:last-child {{ border-right: 0; }}
    .mini-grid span {{ display: block; color: var(--muted); font-size: 0.82rem; }}
    .mini-grid strong {{ display: block; margin-top: 2px; }}
    section.info {{
      display: grid;
      align-content: center;
      padding: 56px 0;
    }}
    .section-title {{
      max-width: 760px;
      font-size: clamp(2rem, 5vw, 4.6rem);
      line-height: 0.98;
      margin: 0;
    }}
    .about-text {{
      max-width: 760px;
      color: var(--muted);
      font-size: 1.08rem;
      margin-top: 20px;
    }}
    .about-story {{
      font-weight: 350;
      line-height: 1.75;
    }}
    .footer {{
      padding: 54px 0 72px;
      border-top: 1px solid var(--line);
      display: flex;
      justify-content: space-between;
      gap: 20px;
      flex-wrap: wrap;
    }}
    .social-icon {{
      width: 46px;
      height: 46px;
      display: inline-grid;
      place-items: center;
      border: 1px solid var(--line);
      border-radius: 14px;
      background:
        linear-gradient(145deg, rgba(255,255,255,0.52), rgba(255,255,255,0.16)),
        var(--glass-strong);
      color: var(--accent-strong);
      text-decoration: none;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.72), 0 16px 34px rgba(45,45,150,0.12);
    }}
    .social-icon svg {{
      width: 24px;
      height: 24px;
      display: block;
      fill: currentColor;
    }}
    .a11y {{
      position: fixed;
      right: 16px;
      bottom: 16px;
      z-index: 5;
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px;
      max-width: min(460px, calc(100% - 32px));
    }}
    .a11y button {{
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--bg-elevated);
      color: var(--ink);
      padding: 9px 11px;
      cursor: pointer;
      backdrop-filter: blur(14px);
    }}
    .result-page {{
      min-height: calc(100vh - 78px);
      padding: clamp(34px, 6vw, 76px) 0;
    }}
    .result-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin: 24px 0;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 14px;
      background: var(--bg-elevated);
      padding: 16px;
    }}
    .metric span {{ display: block; color: var(--muted); font-size: 0.86rem; }}
    .metric strong {{ display: block; font-size: 1.55rem; margin-top: 4px; }}
    .file-list {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 10px;
      margin: 0;
      padding: 0;
      list-style: none;
    }}
    .file-list a {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      min-height: 54px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--cream);
      color: var(--ink);
      text-decoration: none;
      font-weight: 850;
      padding: 12px 14px;
    }}
    .file-list span {{ color: var(--muted); font-size: 0.86rem; font-weight: 700; }}
    .preview-video {{
      display: block;
      width: 100%;
      max-height: 520px;
      margin-top: 14px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: #080912;
    }}
    @media (max-width: 860px) {{
      .hero {{ grid-template-columns: 1fr; min-height: auto; }}
      .analysis-form {{ grid-template-columns: 1fr; }}
      .mini-grid {{ grid-template-columns: 1fr; }}
      .mini-grid div {{ border-right: 0; border-bottom: 1px solid var(--line); }}
      .mini-grid div:last-child {{ border-bottom: 0; }}
      .tool-head {{ align-items: flex-start; }}
      .tool-head-actions {{ align-items: flex-end; flex-direction: column-reverse; }}
      nav a {{ display: none; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      html {{ scroll-behavior: auto; }}
      *, *::before, *::after {{ animation-duration: 0.001ms !important; transition-duration: 0.001ms !important; }}
    }}
    [data-motion="reduced"] {{ scroll-behavior: auto; }}
  </style>
</head>
<body>
  <a class="skip" href="#main">Skip to main content</a>
  <header class="topbar">
    <a class="brand" href="/" aria-label="ColorCheck home"><img class="brand-logo" src="/assets/colorcheck-wordmark.svg" alt="colorcheck."></a>
    <nav aria-label="Primary navigation">
      <a href="/#tool">Analyze</a>
      <a href="/#about">About</a>
      <a href="{LINKEDIN_URL}" target="_blank" rel="noreferrer">LinkedIn</a>
      <button class="icon-button" type="button" data-theme-toggle aria-label="Toggle dark mode">Dark</button>
    </nav>
  </header>
  <main id="main">{body}</main>
  <div class="a11y" aria-label="Accessibility controls">
    <button type="button" data-contrast-toggle>High contrast</button>
    <button type="button" data-motion-toggle>Reduce motion</button>
    <button type="button" data-font-toggle>Larger text</button>
  </div>
  <script>
    const root = document.documentElement;
    const settings = JSON.parse(localStorage.getItem("vccSettings") || "{{}}");
    const save = () => localStorage.setItem("vccSettings", JSON.stringify(settings));
    const apply = () => {{
      root.dataset.theme = settings.theme || "light";
      root.dataset.contrast = settings.contrast || "normal";
      root.dataset.motion = settings.motion || "standard";
      root.style.setProperty("--font-scale", settings.largeText ? "18px" : "16px");
      const themeButton = document.querySelector("[data-theme-toggle]");
      if (themeButton) themeButton.textContent = root.dataset.theme === "dark" ? "Light" : "Dark";
    }};
    document.querySelector("[data-theme-toggle]")?.addEventListener("click", () => {{
      settings.theme = root.dataset.theme === "dark" ? "light" : "dark";
      save(); apply();
    }});
    document.querySelector("[data-contrast-toggle]")?.addEventListener("click", () => {{
      settings.contrast = root.dataset.contrast === "high" ? "normal" : "high";
      save(); apply();
    }});
    document.querySelector("[data-motion-toggle]")?.addEventListener("click", () => {{
      settings.motion = root.dataset.motion === "reduced" ? "standard" : "reduced";
      save(); apply();
    }});
    document.querySelector("[data-font-toggle]")?.addEventListener("click", () => {{
      settings.largeText = !settings.largeText;
      save(); apply();
    }});
    document.querySelectorAll("input[type='range'][data-output]").forEach((input) => {{
      const output = document.getElementById(input.dataset.output);
      const sync = () => {{
        if (output) output.textContent = `${{input.value}}%`;
      }};
      input.addEventListener("input", sync);
      sync();
    }});
    const analysisForm = document.querySelector(".analysis-form");
    analysisForm?.addEventListener("submit", (event) => {{
      const form = event.currentTarget;
      if (form.dataset.submitting === "true") {{
        event.preventDefault();
        return;
      }}
      if (!form.checkValidity()) return;
      const submitButton = form.querySelector(".submit");
      if (!submitButton) return;
      form.dataset.submitting = "true";
      form.setAttribute("aria-busy", "true");
      submitButton.disabled = true;
      submitButton.setAttribute("aria-busy", "true");
      submitButton.textContent = "Mapping report & video...";
    }});
    window.addEventListener("pageshow", () => {{
      if (!analysisForm) return;
      const submitButton = analysisForm.querySelector(".submit");
      analysisForm.dataset.submitting = "false";
      analysisForm.removeAttribute("aria-busy");
      if (!submitButton) return;
      submitButton.disabled = false;
      submitButton.removeAttribute("aria-busy");
      submitButton.textContent = submitButton.dataset.defaultLabel;
    }});
    apply();
  </script>
</body>
</html>"""


def home_page(
    max_upload_mb: int = 250,
    max_request_mb: int = 504,
    max_video_seconds: int = 120,
) -> str:
    body = f"""<div class="page">
  <section class="hero" id="tool" aria-labelledby="hero-title">
    <div>
      <p class="eyebrow">Reference-led color review</p>
      <h1 id="hero-title">Color that isn't artificial.</h1>
      <p class="descriptor">Compares a video to a reference look, then exports a guarded corrected preview and editor-ready color guidance.</p>
      <p class="lede">Upload a reference image or reference video, then add the clip you want checked. ColorCheck samples the footage, finds matching lighting moments, flags drift, and lets you choose how strongly the correction should be applied.</p>
    </div>
    <div class="panel analysis-panel" aria-label="Upload analyzer">
      <div class="tool-head">
        <div>
          <strong>Analyze footage</strong>
          <div class="hint">Image or video reference accepted</div>
          <div class="hint">Up to {max_upload_mb} MB per file, {max_request_mb} MB combined, and {max_video_seconds}-second clips</div>
        </div>
        <div class="tool-head-actions">
          <div class="palette-swatches" role="img" aria-label="Reference palette: violet, rose, mint, and amber">
            <span aria-hidden="true"></span>
            <span aria-hidden="true"></span>
            <span aria-hidden="true"></span>
            <span aria-hidden="true"></span>
          </div>
          <div class="status-pill">Preview + report</div>
        </div>
      </div>
      <form class="analysis-form" action="/analyze-form" method="post" enctype="multipart/form-data">
        <label class="field-reference">
          Reference image or video
          <input name="reference" type="file" accept="image/*,video/*" required>
          <span class="hint">Use the frame, still, or clip whose look you want to preserve.</span>
        </label>
        <label class="field-target">
          Target video
          <input name="video" type="file" accept="video/*" required>
          <span class="hint">This is the footage ColorCheck compares against your reference look.</span>
        </label>
        <label class="field-samples">
          Frame samples
          <input name="samples" type="number" min="4" max="96" value="24">
          <span class="hint">More samples give a steadier read on longer clips.</span>
        </label>
        <label class="field-strength">
          Correction strength
          <span class="range-box">
            <input name="strength" type="range" min="0" max="100" value="50" data-output="strength-output">
            <span class="range-meta"><span>Report only</span><output id="strength-output">50%</output><span>Full correction</span></span>
          </span>
          <span class="hint">Controls how strongly the preview video and exported LUT/CDL apply the recommendation.</span>
        </label>
        <label class="field-threshold">
          Lighting safety threshold
          <span class="range-box">
            <input name="lighting_threshold" type="range" min="25" max="90" value="60" data-output="threshold-output">
            <span class="range-meta"><span>Strict</span><output id="threshold-output">60%</output><span>Flexible</span></span>
          </span>
          <span class="hint">Warnings appear when the selected strength risks changing the original lighting setup.</span>
        </label>
        <div class="field-action">
          <label class="consent">
            <input name="rights_confirmed" type="checkbox" required>
            <span>I have permission to process these files. Uploads are deleted after processing and generated results expire automatically.</span>
          </label>
          <button class="submit" type="submit" data-default-label="Generate Mapped Report &amp; Video">Generate Mapped Report &amp; Video</button>
        </div>
      </form>
      <div class="mini-grid" aria-label="Outputs">
        <div><span>Exports</span><strong>Preview + master + LUT/CDL</strong></div>
        <div><span>Editors</span><strong>Resolve, Premiere, Avid, iMovie</strong></div>
        <div><span>Safety</span><strong>Strength threshold</strong></div>
      </div>
    </div>
  </section>
  <section class="info" aria-labelledby="output-title">
    <p class="eyebrow">What you get</p>
    <h2 class="section-title" id="output-title">A clean report, not a mystery filter.</h2>
    <p class="about-text">The output tells you whether the target clip is brighter, flatter, warmer, cooler, more saturated, or less saturated than the reference. It also gives individual downloads for the corrected preview, full report, JSON data, LUT, CDL, and editor-specific instructions.</p>
  </section>
  <section class="info" id="about" aria-labelledby="about-title">
    <p class="eyebrow">About the project</p>
    <h2 class="section-title" id="about-title">Built from editing frustration, shaped by machine learning curiosity.</h2>
    <p class="about-text about-story">I made ColorCheck for the amateur editor version of myself: someone who can feel when two shots do not quite belong together, but wants a clearer way to measure why. It sits at the overlap of visual art, editing judgment, and machine learning by turning reference footage into practical, bounded color guidance instead of letting automation push an image until it breaks.</p>
  </section>
  <footer class="footer">
    <div>
      <strong>ColorCheck by Aditya Deshpande</strong>
      <div class="hint">PyTorch, OpenCV, FastAPI, Docker, and Kubernetes.</div>
    </div>
    <a class="social-icon" href="https://www.linkedin.com/in/aditya-deshpande-127218205/" target="_blank" rel="noreferrer" aria-label="Aditya Deshpande on LinkedIn">
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M6.94 8.98H3.56v10.8h3.38V8.98ZM5.25 4.22c-1.08 0-1.95.8-1.95 1.82 0 1.03.87 1.84 1.95 1.84s1.95-.81 1.95-1.84c0-1.02-.87-1.82-1.95-1.82Zm14.5 9.5c0-3.06-1.63-4.48-3.81-4.48-1.75 0-2.54.96-2.98 1.64h-.04v-1.4H9.68v10.8h3.38v-5.34c0-1.4.26-2.76 2-2.76 1.72 0 1.74 1.6 1.74 2.85v5.25h3.38v-5.92c0-.29-.01-.51-.03-.64Z"/>
      </svg>
    </a>
  </footer>
</div>"""
    return page_shell("ColorCheck", body)


def job_page(job_id: str, report: dict[str, object]) -> str:
    summary = report["summary"]
    guardrails = report["guardrails"]
    correction = report["correction"]
    export_settings = report.get(
        "export_settings",
        {
            "correction_strength_percent": 0,
            "lighting_shift_threshold_percent": 60,
            "audio_status": "unknown",
        },
    )
    lighting_shift = report.get(
        "lighting_shift",
        {
            "shift_percent": 0.0,
            "threshold_percent": 60,
            "preserves_lighting_setup": True,
            "warnings": [],
        },
    )
    corrected_video_filename = report.get("corrected_video_filename")
    corrected_master_filename = report.get("corrected_master_filename")
    outputs = [
        ("Full report", "report.html", "HTML"),
        ("Raw analysis", "report.json", "JSON"),
        ("DaVinci Resolve", "davinci_resolve_steps.md", "Guide"),
        ("Premiere Pro", "premiere_pro_steps.md", "Guide"),
        ("Avid Media Composer", "avid_media_composer_steps.md", "Guide"),
        ("iMovie", "imovie_steps.md", "Guide"),
        ("Recommended LUT", "recommended_correction.cube", "CUBE"),
        ("ASC CDL", "recommended_correction.cdl", "CDL"),
    ]
    if corrected_video_filename:
        outputs.insert(0, ("Corrected preview", str(corrected_video_filename), "MP4"))
    if corrected_master_filename:
        outputs.insert(0, ("Quality-preserved master", str(corrected_master_filename), "MOV"))
    file_links = "\n".join(
        f'<li><a href="/jobs/{job_id}/{filename}">{label}<span>{kind}</span></a></li>'
        for label, filename, kind in outputs
    )
    warnings = [
        *list(lighting_shift.get("warnings", [])),
        *list(guardrails["warnings"]),
    ] or ["No guardrail warnings."]
    warning_items = "".join(f"<li>{html.escape(str(warning))}</li>" for warning in warnings)
    preserves_lighting = bool(lighting_shift.get("preserves_lighting_setup", True))
    safe_label = "Preserves lighting setup" if preserves_lighting else "Lighting threshold crossed"
    preview_section = ""
    if corrected_video_filename:
        audio_messages = {
            "preserved": "The source video's audio is included in this corrected preview.",
            "source_has_no_audio": "The uploaded source has no audio track, so this preview is silent.",
            "unavailable": "Audio could not be included in this export, so this preview is silent.",
            "unknown": "Audio status was not recorded for this export.",
        }
        audio_status = str(export_settings.get("audio_status", "unknown"))
        audio_message = audio_messages.get(audio_status, audio_messages["unknown"])
        preview_section = f"""
  <section class="panel" style="padding:18px; margin-bottom:18px;">
    <h2>Corrected preview</h2>
    <p class="hint">{html.escape(audio_message)}</p>
    <p class="hint">The browser preview is capped at 1080p for responsive playback. Download the quality-preserved master for the source resolution and bit depth.</p>
    <video class="preview-video" controls playsinline preload="metadata">
      <source src="/jobs/{job_id}/{html.escape(str(corrected_video_filename))}?codec=h264" type="video/mp4">
      Your browser could not play this preview. Download the MP4 below instead.
    </video>
  </section>"""
    body = f"""<div class="page result-page">
  <p class="eyebrow">Analysis complete</p>
  <h1>Match score {summary["overall_score"]}/100</h1>
  <p class="descriptor">{html.escape(str(summary["recommendation"]))}</p>
  <div class="result-grid">
    <div class="metric"><span>Drift level</span><strong>{html.escape(str(summary["drift_level"]))}</strong></div>
    <div class="metric"><span>Reference lighting</span><strong>{html.escape(str(summary["reference_lighting"]))}</strong></div>
    <div class="metric"><span>Target lighting</span><strong>{html.escape(str(summary["target_lighting"]))}</strong></div>
    <div class="metric"><span>Risky frames</span><strong>{summary["risky_frame_count"]}</strong></div>
    <div class="metric"><span>Correction strength</span><strong>{export_settings["correction_strength_percent"]}%</strong></div>
    <div class="metric"><span>Lighting shift</span><strong>{lighting_shift["shift_percent"]}%</strong></div>
  </div>
  <section class="panel" style="padding:18px; margin-bottom:18px;">
    <h2>{safe_label}</h2>
    <p>Exposure {correction["exposure_stops"]:+.3f} stops, contrast {correction["contrast_multiplier"]:.3f}x, saturation {correction["saturation_multiplier"]:.3f}x.</p>
    <p>Lighting setup shift: {lighting_shift["shift_percent"]}% / threshold {lighting_shift["threshold_percent"]}%.</p>
    <p>Estimated clipping risk: {guardrails["clipping_risk_percent"]:.3f}%</p>
    <ul>{warning_items}</ul>
  </section>
  {preview_section}
  <section class="panel" style="padding:18px;">
    <h2>Downloads</h2>
    <p class="hint">The master retains the source codec family, resolution, timing, bit depth, color metadata, and original audio when supported.</p>
    <ul class="file-list">{file_links}</ul>
  </section>
</div>"""
    return page_shell("ColorCheck Results", body)
