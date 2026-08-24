from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np

from video_color_checker.correction import apply_correction_array
from video_color_checker.models import CorrectionPlan


def write_cube_lut(path: str | Path, correction: CorrectionPlan, size: int = 17) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    levels = np.linspace(0.0, 1.0, size, dtype=np.float32)

    with output_path.open("w", encoding="utf-8") as handle:
        handle.write('TITLE "Video Color Checker Recommended Correction"\n')
        handle.write(f"LUT_3D_SIZE {size}\n")
        handle.write("DOMAIN_MIN 0.0 0.0 0.0\n")
        handle.write("DOMAIN_MAX 1.0 1.0 1.0\n")
        for blue in levels:
            for green in levels:
                for red in levels:
                    rgb = np.array([[[red, green, blue]]], dtype=np.float32)
                    corrected = apply_correction_array(rgb, correction)[0, 0]
                    handle.write(
                        f"{corrected[0]:.6f} {corrected[1]:.6f} {corrected[2]:.6f}\n"
                    )
    return output_path


def write_cdl(path: str | Path, correction: CorrectionPlan, identifier: str = "vcc-recommendation") -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    exposure_gain = 2.0 ** correction.exposure_stops
    slope = tuple(exposure_gain * channel for channel in correction.channel_gains)
    offset = correction.lift_offset
    power = (1.0, 1.0, 1.0)

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<ColorCorrectionCollection xmlns="urn:ASC:CDL:v1.2">
  <ColorCorrection id="{escape(identifier)}">
    <SOPNode>
      <Slope>{slope[0]:.6f} {slope[1]:.6f} {slope[2]:.6f}</Slope>
      <Offset>{offset[0]:.6f} {offset[1]:.6f} {offset[2]:.6f}</Offset>
      <Power>{power[0]:.6f} {power[1]:.6f} {power[2]:.6f}</Power>
    </SOPNode>
    <SatNode>
      <Saturation>{correction.saturation_multiplier:.6f}</Saturation>
    </SatNode>
  </ColorCorrection>
</ColorCorrectionCollection>
"""
    output_path.write_text(xml, encoding="utf-8")
    return output_path
