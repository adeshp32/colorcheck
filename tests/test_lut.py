from pathlib import Path

from video_color_checker.lut import write_cdl, write_cube_lut
from video_color_checker.models import CorrectionPlan


def correction() -> CorrectionPlan:
    return CorrectionPlan(
        exposure_stops=0.1,
        contrast_multiplier=1.05,
        saturation_multiplier=0.95,
        channel_gains=(1.02, 1.0, 0.98),
        lift_offset=(0.0, 0.0, 0.0),
        confidence=0.7,
        rationale=[],
    )


def test_cube_lut_has_expected_grid_lines(tmp_path: Path) -> None:
    path = write_cube_lut(tmp_path / "test.cube", correction(), size=3)
    lines = path.read_text(encoding="utf-8").splitlines()
    data_lines = [line for line in lines if line and line[0].isdigit()]

    assert "LUT_3D_SIZE 3" in lines
    assert len(data_lines) == 27


def test_cdl_contains_expected_nodes(tmp_path: Path) -> None:
    path = write_cdl(tmp_path / "test.cdl", correction())
    text = path.read_text(encoding="utf-8")

    assert "<Slope>" in text
    assert "<Offset>" in text
    assert "<Saturation>" in text
