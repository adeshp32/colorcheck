from __future__ import annotations

import pytest

from colorcheck.edits import EditPlanError, parse_edit_plan, retained_segments


def test_keep_and_remove_regions_form_final_timeline() -> None:
    plan = parse_edit_plan(
        {
            "trims": [
                {"start": 1, "end": 9, "mode": "keep"},
                {"start": 3, "end": 4, "mode": "remove"},
                {"start": 7, "end": 8, "mode": "remove"},
            ]
        },
        duration=10,
    )

    assert retained_segments(plan, 10) == [(1.0, 3.0), (4.0, 7.0), (8.0, 9.0)]


def test_color_crop_and_text_recipe_is_validated() -> None:
    plan = parse_edit_plan(
        {
            "crop": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
            "color": {
                "mode": "moonlight",
                "tint": "#5c5cff",
                "intensity": 42,
                "black_and_white": True,
            },
            "text_overlays": [
                {
                    "text": "ColorCheck",
                    "start": 1,
                    "end": 3,
                    "x": 0.5,
                    "y": 0.85,
                    "size": 5,
                    "color": "#ffffff",
                    "background": True,
                }
            ],
        },
        duration=5,
    )

    assert plan.color.tint == "#5c5cff"
    assert plan.color.black_and_white is True
    assert plan.crop.width == 0.8
    assert plan.text_overlays[0].text == "ColorCheck"


def test_recipe_cannot_remove_the_entire_clip() -> None:
    with pytest.raises(EditPlanError, match="entire clip"):
        parse_edit_plan(
            {"trims": [{"start": 0, "end": 10, "mode": "remove"}]},
            duration=10,
        )
