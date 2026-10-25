"""Small, browser-portable signals for choosing a reference matcher.

Every feature is computed from images available when a user edits a photo.
The expert edit is deliberately absent from this module's interface.
"""

from __future__ import annotations

import torch

FEATURE_NAMES = (
    *(f"source_mean_{channel}" for channel in "rgb"),
    *(f"source_std_{channel}" for channel in "rgb"),
    *(f"reference_mean_{channel}" for channel in "rgb"),
    *(f"reference_std_{channel}" for channel in "rgb"),
    *(f"reference_minus_source_mean_{channel}" for channel in "rgb"),
    *(f"reference_minus_source_std_{channel}" for channel in "rgb"),
    *(f"lut_minus_source_mean_{channel}" for channel in "rgb"),
    *(f"statistics_minus_source_mean_{channel}" for channel in "rgb"),
    "lut_shift_mae", "statistics_shift_mae", "lut_clipping_fraction",
    "statistics_clipping_fraction", "candidate_disagreement_mae",
    "source_luminance_mean", "source_luminance_std",
    "reference_luminance_mean", "reference_luminance_std",
)


def _channel_mean(image: torch.Tensor) -> torch.Tensor:
    return image.mean(dim=(2, 3))


def _channel_std(image: torch.Tensor) -> torch.Tensor:
    return image.std(dim=(2, 3), correction=0)


def _luminance_summary(image: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    weights = image.new_tensor((0.2126, 0.7152, 0.0722))
    luminance = (image * weights[None, :, None, None]).sum(dim=1)
    return luminance.mean(dim=(1, 2)), luminance.std(dim=(1, 2), correction=0)


def _clipping(image: torch.Tensor) -> torch.Tensor:
    return ((image <= 1 / 255) | (image >= 254 / 255)).any(dim=1).float().mean(dim=(1, 2))


def selector_features(source: torch.Tensor, reference: torch.Tensor,
                      lut_output: torch.Tensor, statistics_output: torch.Tensor) -> torch.Tensor:
    """Return one fixed-schema feature row per photo, without ground truth."""
    if not all(image.shape == source.shape for image in (reference, lut_output, statistics_output)):
        raise ValueError("Source, reference, and candidate images must have the same shape")
    if source.ndim != 4 or source.shape[1] != 3:
        raise ValueError("Expected Bx3xHxW RGB tensors")
    source, reference = source.float(), reference.float()
    lut_output, statistics_output = lut_output.float(), statistics_output.float()
    source_luma, source_luma_std = _luminance_summary(source)
    reference_luma, reference_luma_std = _luminance_summary(reference)
    columns = (
        _channel_mean(source), _channel_std(source),
        _channel_mean(reference), _channel_std(reference),
        _channel_mean(reference) - _channel_mean(source),
        _channel_std(reference) - _channel_std(source),
        _channel_mean(lut_output - source),
        _channel_mean(statistics_output - source),
        (lut_output - source).abs().mean(dim=(1, 2, 3), keepdim=False)[:, None],
        (statistics_output - source).abs().mean(dim=(1, 2, 3))[:, None],
        _clipping(lut_output)[:, None], _clipping(statistics_output)[:, None],
        (lut_output - statistics_output).abs().mean(dim=(1, 2, 3))[:, None],
        source_luma[:, None], source_luma_std[:, None],
        reference_luma[:, None], reference_luma_std[:, None],
    )
    result = torch.cat(columns, dim=1)
    if result.shape[1] != len(FEATURE_NAMES) or not torch.isfinite(result).all():
        raise RuntimeError("Selector feature schema changed or produced nonfinite values")
    return result
