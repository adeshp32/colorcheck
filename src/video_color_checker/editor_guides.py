from __future__ import annotations

from video_color_checker.models import AnalysisReport


def _shared_values(report: AnalysisReport) -> str:
    gains = report.correction.channel_gains
    return f"""Recommended bounded correction values:

- Exposure: {report.correction.exposure_stops:+.3f} stops
- Contrast multiplier: {report.correction.contrast_multiplier:.3f}
- Saturation multiplier: {report.correction.saturation_multiplier:.3f}
- Red gain: {gains[0]:.3f}
- Green gain: {gains[1]:.3f}
- Blue gain: {gains[2]:.3f}
- Estimated clipping risk: {report.guardrails.clipping_risk_percent:.3f}%
- Safe-to-apply flag: {report.guardrails.safe_to_apply}
"""


def davinci_resolve_guide(report: AnalysisReport) -> str:
    return f"""# DaVinci Resolve Instructions

Use `recommended_correction.cube` as the portable starting point.

1. Open the project in DaVinci Resolve.
2. Go to the Color page.
3. Add a node for the recommended correction.
4. Import or copy `recommended_correction.cube` into Resolve's LUT folder, then refresh LUTs.
5. Apply the LUT to the correction node.
6. Check the scopes before export. If highlights or shadows clip, reduce the node key output.

{_shared_values(report)}

Notes:

- This is a conservative technical match, not a creative final grade.
- Keep the original clip/node available so the recommendation can be bypassed.
"""


def premiere_pro_guide(report: AnalysisReport) -> str:
    return f"""# Adobe Premiere Pro Instructions

Use `recommended_correction.cube` through Lumetri Color.

1. Select the clip or adjustment layer.
2. Open Lumetri Color.
3. Apply `recommended_correction.cube` as an Input LUT or Creative Look.
4. Keep Intensity at or below 100%.
5. Watch the Lumetri scopes and reduce intensity if blacks or highlights clip.

{_shared_values(report)}

Notes:

- If the LUT feels too strong, place it on an adjustment layer and lower opacity.
- Use the values above as manual guidance if LUT import is unavailable.
"""


def avid_guide(report: AnalysisReport) -> str:
    return f"""# Avid Media Composer Instructions

Use `recommended_correction.cube` as a custom LUT when your Media Composer setup supports it.

1. Open the project and select the target clip.
2. Use Source Settings, Color Management, or the color workflow available in your version.
3. Import or apply `recommended_correction.cube`.
4. Validate with scopes before committing the grade.
5. If custom LUT import is unavailable, recreate the adjustment manually using the values below.

{_shared_values(report)}

Notes:

- Avid workflows vary by project color management settings.
- Treat the CDL file as a simpler interchange fallback where supported.
"""


def imovie_guide(report: AnalysisReport) -> str:
    exposure_direction = "increase" if report.correction.exposure_stops > 0 else "decrease"
    saturation_direction = (
        "increase" if report.correction.saturation_multiplier > 1.0 else "decrease"
    )
    contrast_direction = "increase" if report.correction.contrast_multiplier > 1.0 else "decrease"
    gains = report.correction.channel_gains
    warmth = "warmer" if gains[0] > gains[2] else "cooler"
    return f"""# iMovie Instructions

iMovie does not provide a normal custom LUT import workflow, so use these as manual instructions.

1. Select the target clip.
2. Try Match Color against the reference frame if available.
3. Fine-tune manually:
   - {exposure_direction.capitalize()} brightness/exposure slightly.
   - {contrast_direction.capitalize()} contrast slightly.
   - {saturation_direction.capitalize()} saturation slightly.
   - Nudge color temperature {warmth} only if the image still feels off.
4. Do not push sliders until shadows crush or highlights lose detail.

{_shared_values(report)}

Notes:

- Use iMovie for a visual approximation, not exact technical matching.
- If exact correction files matter, use DaVinci Resolve or Premiere Pro.
"""


def all_guides(report: AnalysisReport) -> dict[str, str]:
    return {
        "davinci_resolve_steps.md": davinci_resolve_guide(report),
        "premiere_pro_steps.md": premiere_pro_guide(report),
        "avid_media_composer_steps.md": avid_guide(report),
        "imovie_steps.md": imovie_guide(report),
    }
