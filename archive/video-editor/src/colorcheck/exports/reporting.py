from __future__ import annotations

import html
import json
from pathlib import Path

from colorcheck.exports.guides import all_guides
from colorcheck.exports.lut import write_cdl, write_cube_lut
from colorcheck.models import AnalysisReport


def _frame_rows(report: AnalysisReport) -> str:
    rows: list[str] = []
    for frame in report.frames:
        notes = "; ".join(frame.notes) if frame.notes else "within expected drift"
        rows.append(
            "<tr>"
            f"<td>{frame.frame_index}</td>"
            f"<td>{frame.timestamp_sec:.2f}s</td>"
            f"<td>{frame.match_score:.2f}</td>"
            f"<td>{frame.ssim:.3f}</td>"
            f"<td>{frame.delta_e_mean:.2f}</td>"
            f"<td>{html.escape(notes)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_html_report(report: AnalysisReport) -> str:
    warnings = report.guardrails.warnings or ["No guardrail warnings."]
    warning_items = "\n".join(f"<li>{html.escape(warning)}</li>" for warning in warnings)
    shift_warnings = report.lighting_shift.warnings or ["Selected strength preserves the lighting setup."]
    shift_warning_items = "\n".join(
        f"<li>{html.escape(warning)}</li>" for warning in shift_warnings
    )
    rationale = "\n".join(
        f"<li>{html.escape(item)}</li>" for item in report.correction.rationale
    )
    gains = report.correction.channel_gains
    corrected_link = ""
    audio_messages = {
        "preserved": "The source video's audio is included in the corrected preview.",
        "source_has_no_audio": "The source video has no audio track; the preview is silent.",
        "unavailable": "Audio could not be included in the corrected preview.",
        "not_exported": "No corrected preview was requested.",
    }
    audio_message = audio_messages.get(
        report.export_settings.audio_status,
        "Audio status is unavailable for this export.",
    )
    if report.corrected_video_filename:
        corrected_link = (
            f'<p><a href="{html.escape(report.corrected_video_filename)}">'
            "Open corrected preview video</a></p>"
        )
    if report.corrected_master_filename:
        corrected_link += (
            f'<p><a href="{html.escape(report.corrected_master_filename)}">'
            "Download quality-preserved corrected master</a></p>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Video Color Consistency Report</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
      color: #18202a;
      background: #f4f6f8;
    }}
    body {{ margin: 0; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 32px 20px 48px; }}
    h1, h2 {{ line-height: 1.1; margin: 0 0 12px; }}
    section {{ margin-top: 24px; }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
    }}
    .metric, table, pre {{
      background: #ffffff;
      border: 1px solid #d8dee6;
      border-radius: 8px;
    }}
    .metric {{ padding: 16px; }}
    .metric span {{ color: #647082; font-size: 13px; display: block; }}
    .metric strong {{ font-size: 24px; }}
    table {{ width: 100%; border-collapse: collapse; overflow: hidden; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #e6ebf0; text-align: left; }}
    th {{ background: #eef2f5; font-size: 13px; }}
    pre {{ padding: 16px; overflow: auto; }}
  </style>
</head>
<body>
<main>
  <h1>Video Color Consistency Report</h1>
  <p>{html.escape(report.summary.recommendation)}</p>

  <section class="summary">
    <div class="metric"><span>Overall Match</span><strong>{report.summary.overall_score:.2f}/100</strong></div>
    <div class="metric"><span>Drift Level</span><strong>{html.escape(report.summary.drift_level)}</strong></div>
    <div class="metric"><span>Reference Lighting</span><strong>{html.escape(report.summary.reference_lighting)}</strong></div>
    <div class="metric"><span>Target Lighting</span><strong>{html.escape(report.summary.target_lighting)}</strong></div>
  </section>

  <section>
    <h2>Recommended Correction</h2>
    <pre>Exposure: {report.correction.exposure_stops:+.3f} stops
Contrast: {report.correction.contrast_multiplier:.3f}x
Saturation: {report.correction.saturation_multiplier:.3f}x
Channel gains: R {gains[0]:.3f}, G {gains[1]:.3f}, B {gains[2]:.3f}
Confidence: {report.correction.confidence:.3f}</pre>
  </section>

  <section>
    <h2>Preview Export</h2>
    <p>Correction strength: <strong>{report.export_settings.correction_strength_percent}%</strong></p>
    <p>Lighting setup shift: <strong>{report.lighting_shift.shift_percent:.2f}%</strong> / threshold <strong>{report.lighting_shift.threshold_percent}%</strong></p>
    <p>Preserves original lighting setup: <strong>{report.lighting_shift.preserves_lighting_setup}</strong></p>
    <p>{html.escape(audio_message)}</p>
    <ul>{shift_warning_items}</ul>
    {corrected_link}
  </section>

  <section>
    <h2>Guardrails</h2>
    <p>Safe to apply: <strong>{report.guardrails.safe_to_apply}</strong></p>
    <p>Estimated clipping risk: <strong>{report.guardrails.clipping_risk_percent:.3f}%</strong></p>
    <ul>{warning_items}</ul>
  </section>

  <section>
    <h2>Rationale</h2>
    <ul>{rationale}</ul>
  </section>

  <section>
    <h2>Sampled Frames</h2>
    <table>
      <thead>
        <tr>
          <th>Frame</th>
          <th>Time</th>
          <th>Match</th>
          <th>SSIM</th>
          <th>Delta E</th>
          <th>Notes</th>
        </tr>
      </thead>
      <tbody>
        {_frame_rows(report)}
      </tbody>
    </table>
  </section>
</main>
</body>
</html>
"""


def write_report_outputs(report: AnalysisReport, out_dir: str | Path) -> dict[str, Path]:
    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    report_json = output_dir / "report.json"
    report_html = output_dir / "report.html"
    cube_path = output_dir / "recommended_correction.cube"
    cdl_path = output_dir / "recommended_correction.cdl"
    report_json.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    report_html.write_text(render_html_report(report), encoding="utf-8")
    write_cube_lut(cube_path, report.correction)
    write_cdl(cdl_path, report.correction)

    written = {
        "report_json": report_json,
        "report_html": report_html,
        "cube_lut": cube_path,
        "asc_cdl": cdl_path,
    }

    for filename, content in all_guides(report).items():
        path = output_dir / filename
        path.write_text(content, encoding="utf-8")
        written[filename] = path

    return written
