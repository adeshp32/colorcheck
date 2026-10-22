"""Training objectives for faithful color transfer with structural guardrails."""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn


def rgb_to_lab(image: torch.Tensor) -> torch.Tensor:
    """Convert display RGB into perceptual CIE Lab values.

    Equal RGB errors do not always look equally different to a person. Lab is
    used here because Euclidean distance in this space is a more meaningful
    color-error signal than raw channel distance.
    """
    # Undo the nonlinear sRGB transfer curve before converting color spaces.
    linear = torch.where(
        image <= 0.04045,
        image / 12.92,
        ((image + 0.055) / 1.055).pow(2.4),
    )
    matrix = image.new_tensor(
        [[0.4124564, 0.3575761, 0.1804375],
         [0.2126729, 0.7151522, 0.0721750],
         [0.0193339, 0.1191920, 0.9503041]]
    )
    xyz = torch.einsum("ij,bjhw->bihw", matrix, linear)
    xyz = xyz / image.new_tensor([0.95047, 1.0, 1.08883])[None, :, None, None]
    delta = 6 / 29
    f = torch.where(xyz > delta**3, xyz.clamp_min(1e-8).pow(1 / 3), xyz / (3 * delta**2) + 4 / 29)
    lightness = 116 * f[:, 1] - 16
    a = 500 * (f[:, 0] - f[:, 1])
    b = 200 * (f[:, 1] - f[:, 2])
    return torch.stack((lightness, a, b), dim=1)


def image_gradients(image: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """Measure horizontal and vertical luminance edges in a batch of images."""
    luminance = (image * image.new_tensor([0.2126, 0.7152, 0.0722])[None, :, None, None]).sum(1, keepdim=True)
    return luminance[:, :, :, 1:] - luminance[:, :, :, :-1], luminance[:, :, 1:, :] - luminance[:, :, :-1, :]


def reference_ranking_loss(
    correct_output: torch.Tensor,
    wrong_output: torch.Tensor,
    expected: torch.Tensor,
    margin: float = 0.01,
) -> torch.Tensor:
    """Require the correct reference to beat a known-wrong style per image.

    Reconstruction alone can reward one broadly attractive enhancement. This
    pairwise hinge objective instead asks for the expected edit to be at least
    margin closer with its true reference. It is used only during training and
    adds no operation or model parameter to browser inference.
    """
    correct_error = (correct_output - expected).abs().mean(dim=(1, 2, 3))
    wrong_error = (wrong_output - expected).abs().mean(dim=(1, 2, 3))
    return (margin + correct_error - wrong_error).relu().mean()


def exact_lut_supervision_loss(
    predicted_lut: torch.Tensor,
    expected_lut: torch.Tensor,
    available: torch.Tensor,
) -> torch.Tensor:
    """Measure full-cube error only where an exact synthetic LUT is known."""
    per_sample = (predicted_lut.float() - expected_lut.float()).abs().flatten(1).mean(1)
    weights = available.to(device=per_sample.device, dtype=per_sample.dtype)
    return (per_sample * weights).sum() / weights.sum().clamp_min(1)


class ReferenceMatchLoss(nn.Module):
    """Combine visual accuracy with guardrails against destructive LUTs.

    No single number captures a good correction. Reconstruction and Lab error
    reward agreement with the expert edit; structure protects source edges;
    smoothness discourages color discontinuities; and monotonicity discourages
    inversions where a brighter input unexpectedly becomes darker.
    """
    def __init__(
        self,
        color_weight: float = 0.02,
        structure_weight: float = 2.0,
        smoothness_weight: float = 0.0005,
        monotonicity_weight: float = 0.002,
    ) -> None:
        super().__init__()
        self.color_weight = color_weight
        self.structure_weight = structure_weight
        self.smoothness_weight = smoothness_weight
        self.monotonicity_weight = monotonicity_weight

    def forward(self, output, expected, source, lut):
        # Charbonnier reconstruction behaves like L1 error while remaining
        # smooth around zero, which makes gradient-based optimization stable.
        reconstruction = torch.sqrt((output - expected).square() + 1e-6).mean()
        color = (rgb_to_lab(output) - rgb_to_lab(expected)).square().sum(1).add(1e-6).sqrt().mean()
        output_x, output_y = image_gradients(output)
        source_x, source_y = image_gradients(source)
        structure = F.l1_loss(output_x, source_x) + F.l1_loss(output_y, source_y)
        differences = [
            lut[:, :, 1:] - lut[:, :, :-1],
            lut[:, :, :, 1:] - lut[:, :, :, :-1],
            lut[:, :, :, :, 1:] - lut[:, :, :, :, :-1],
        ]
        smoothness = sum(diff.square().mean() for diff in differences)
        monotonicity = sum((-diff).relu().mean() for diff in differences)
        total = (
            reconstruction
            + self.color_weight * color
            + self.structure_weight * structure
            + self.smoothness_weight * smoothness
            + self.monotonicity_weight * monotonicity
        )
        return total, {
            "reconstruction": reconstruction.detach(),
            "delta_e76": color.detach(),
            "structure": structure.detach(),
            "lut_smoothness": smoothness.detach(),
            "lut_monotonicity": monotonicity.detach(),
        }
