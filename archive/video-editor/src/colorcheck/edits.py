from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
LIGHTING_MODES = {
    "neutral",
    "warm",
    "cool",
    "golden_hour",
    "moonlight",
    "fluorescent",
    "candlelight",
}


class EditPlanError(ValueError):
    pass


@dataclass(frozen=True)
class TrimRegion:
    start: float
    end: float
    mode: str


@dataclass(frozen=True)
class Crop:
    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 1.0


@dataclass(frozen=True)
class ColorStyle:
    mode: str = "neutral"
    tint: str = "#ffffff"
    intensity: int = 0
    black_and_white: bool = False


@dataclass(frozen=True)
class TextOverlay:
    text: str
    start: float
    end: float
    x: float
    y: float
    size: float
    color: str
    background: bool


@dataclass(frozen=True)
class EditPlan:
    trims: tuple[TrimRegion, ...] = field(default_factory=tuple)
    crop: Crop = field(default_factory=Crop)
    color: ColorStyle = field(default_factory=ColorStyle)
    text_overlays: tuple[TextOverlay, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "version": 1,
            "trims": [
                {"start": region.start, "end": region.end, "mode": region.mode}
                for region in self.trims
            ],
            "crop": {
                "x": self.crop.x,
                "y": self.crop.y,
                "width": self.crop.width,
                "height": self.crop.height,
            },
            "color": {
                "mode": self.color.mode,
                "tint": self.color.tint,
                "intensity": self.color.intensity,
                "black_and_white": self.color.black_and_white,
            },
            "text_overlays": [
                {
                    "text": overlay.text,
                    "start": overlay.start,
                    "end": overlay.end,
                    "x": overlay.x,
                    "y": overlay.y,
                    "size": overlay.size,
                    "color": overlay.color,
                    "background": overlay.background,
                }
                for overlay in self.text_overlays
            ],
        }


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise EditPlanError(f"{name} must be a number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise EditPlanError(f"{name} must be a number.") from exc
    if not math.isfinite(number):
        raise EditPlanError(f"{name} must be finite.")
    return number


def _bounded(value: Any, name: str, low: float, high: float) -> float:
    number = _number(value, name)
    if number < low or number > high:
        raise EditPlanError(f"{name} must be between {low} and {high}.")
    return number


def _color(value: Any, name: str) -> str:
    candidate = str(value or "")
    if HEX_COLOR.fullmatch(candidate) is None:
        raise EditPlanError(f"{name} must be a six-digit hex color.")
    return candidate.lower()


def parse_edit_plan(payload: Any, duration: float) -> EditPlan:
    if not isinstance(payload, dict):
        raise EditPlanError("Edit plan must be an object.")
    if duration <= 0 or not math.isfinite(duration):
        raise EditPlanError("Source duration is invalid.")

    raw_trims = payload.get("trims", [])
    if not isinstance(raw_trims, list) or len(raw_trims) > 64:
        raise EditPlanError("Up to 64 trim regions are supported.")
    trims: list[TrimRegion] = []
    for index, item in enumerate(raw_trims):
        if not isinstance(item, dict):
            raise EditPlanError("Trim regions must be objects.")
        start = _bounded(item.get("start"), f"Trim {index + 1} start", 0.0, duration)
        end = _bounded(item.get("end"), f"Trim {index + 1} end", 0.0, duration)
        mode = str(item.get("mode", ""))
        if mode not in {"keep", "remove"}:
            raise EditPlanError("Trim mode must be keep or remove.")
        if end - start < 0.04:
            raise EditPlanError("Each trim region must be at least 0.04 seconds long.")
        trims.append(TrimRegion(round(start, 4), round(end, 4), mode))

    raw_crop = payload.get("crop", {})
    if not isinstance(raw_crop, dict):
        raise EditPlanError("Crop must be an object.")
    crop = Crop(
        x=_bounded(raw_crop.get("x", 0.0), "Crop x", 0.0, 1.0),
        y=_bounded(raw_crop.get("y", 0.0), "Crop y", 0.0, 1.0),
        width=_bounded(raw_crop.get("width", 1.0), "Crop width", 0.05, 1.0),
        height=_bounded(raw_crop.get("height", 1.0), "Crop height", 0.05, 1.0),
    )
    if crop.x + crop.width > 1.000001 or crop.y + crop.height > 1.000001:
        raise EditPlanError("Crop bounds must stay inside the source frame.")

    raw_style = payload.get("color", {})
    if not isinstance(raw_style, dict):
        raise EditPlanError("Color style must be an object.")
    mode = str(raw_style.get("mode", "neutral"))
    if mode not in LIGHTING_MODES:
        raise EditPlanError("Unknown lighting mode.")
    intensity = round(_bounded(raw_style.get("intensity", 0), "Color intensity", 0, 100))
    style = ColorStyle(
        mode=mode,
        tint=_color(raw_style.get("tint", "#ffffff"), "Tint"),
        intensity=intensity,
        black_and_white=bool(raw_style.get("black_and_white", False)),
    )

    raw_overlays = payload.get("text_overlays", [])
    if not isinstance(raw_overlays, list) or len(raw_overlays) > 24:
        raise EditPlanError("Up to 24 text overlays are supported.")
    overlays: list[TextOverlay] = []
    for index, item in enumerate(raw_overlays):
        if not isinstance(item, dict):
            raise EditPlanError("Text overlays must be objects.")
        text = str(item.get("text", "")).strip()
        if not text or len(text) > 200 or any(ord(character) < 32 for character in text):
            raise EditPlanError("Overlay text must contain 1 to 200 printable characters.")
        start = _bounded(item.get("start", 0), f"Text {index + 1} start", 0, duration)
        end = _bounded(item.get("end", duration), f"Text {index + 1} end", 0, duration)
        if end - start < 0.04:
            raise EditPlanError("Each text overlay must be visible for at least 0.04 seconds.")
        overlays.append(
            TextOverlay(
                text=text,
                start=round(start, 4),
                end=round(end, 4),
                x=_bounded(item.get("x", 0.5), f"Text {index + 1} x", 0.0, 1.0),
                y=_bounded(item.get("y", 0.85), f"Text {index + 1} y", 0.0, 1.0),
                size=_bounded(item.get("size", 5), f"Text {index + 1} size", 1.0, 20.0),
                color=_color(item.get("color", "#ffffff"), f"Text {index + 1} color"),
                background=bool(item.get("background", False)),
            )
        )

    plan = EditPlan(
        trims=tuple(trims),
        crop=crop,
        color=style,
        text_overlays=tuple(overlays),
    )
    if not retained_segments(plan, duration):
        raise EditPlanError("The trim plan removes the entire clip.")
    return plan


def _merge(segments: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for start, end in sorted(segments):
        if end - start < 0.04:
            continue
        if merged and start <= merged[-1][1] + 0.001:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(round(start, 4), round(end, 4)) for start, end in merged]


def _subtract(
    segments: list[tuple[float, float]],
    removal: tuple[float, float],
) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    remove_start, remove_end = removal
    for start, end in segments:
        if remove_end <= start or remove_start >= end:
            result.append((start, end))
            continue
        if remove_start > start:
            result.append((start, min(remove_start, end)))
        if remove_end < end:
            result.append((max(remove_end, start), end))
    return _merge(result)


def retained_segments(plan: EditPlan, duration: float) -> list[tuple[float, float]]:
    keep = [(region.start, region.end) for region in plan.trims if region.mode == "keep"]
    segments = _merge(keep) if keep else [(0.0, round(duration, 4))]
    for region in plan.trims:
        if region.mode == "remove":
            segments = _subtract(segments, (region.start, region.end))
    return segments
