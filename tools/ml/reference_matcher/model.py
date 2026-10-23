"""Small reference-conditioned model that predicts a browser-applicable 3D LUT."""

from __future__ import annotations

import torch
from torch import nn


class ConvBlock(nn.Sequential):
    """Downsample an image while learning increasingly abstract visual features."""

    def __init__(self, incoming: int, outgoing: int) -> None:
        super().__init__(
            # Depthwise convolution examines spatial neighborhoods separately in
            # each channel; the 1x1 convolution then mixes channels efficiently.
            nn.Conv2d(incoming, incoming, 3, stride=2, padding=1, groups=incoming),
            nn.Conv2d(incoming, outgoing, 1),
            nn.GroupNorm(min(8, outgoing), outgoing),
            nn.SiLU(),
        )


class ImageEncoder(nn.Module):
    """Summarize a photograph as a compact 96-number feature vector."""

    def __init__(self, feature_size: int = 96) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 16, 5, stride=2, padding=2),
            nn.SiLU(),
            ConvBlock(16, 24),
            ConvBlock(24, 40),
            ConvBlock(40, 64),
            ConvBlock(64, feature_size),
            nn.AdaptiveAvgPool2d(1),
        )

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        # Adaptive pooling reduces any supported image size to one value per
        # feature channel. ``flatten(1)`` changes BxCx1x1 into BxC.
        return self.features(image).flatten(1)


class ExpertStyleClassifier(nn.Module):
    """Training-only head that asks encoder features to retain editing style.

    FiveK's A-E labels are supervision for representation learning, not product
    choices exposed to users. The head is saved for reproducibility but is never
    called by ``ReferenceLutModel.forward`` and therefore never enters ONNX.
    """

    def __init__(self, feature_size: int = 96, expert_count: int = 5) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(feature_size, 64),
            nn.SiLU(),
            nn.Linear(64, expert_count),
        )

    def forward(self, reference_features: torch.Tensor) -> torch.Tensor:
        return self.layers(reference_features)


def identity_lut(size: int) -> torch.Tensor:
    """Create a 3D lookup table that returns every RGB color unchanged."""
    values = torch.linspace(0, 1, size)
    blue, green, red = torch.meshgrid(values, values, values, indexing="ij")
    return torch.stack((red, green, blue))


def initial_lut_bases(size: int, basis_count: int) -> torch.Tensor:
    """Create distinct, paired photographic anchors with a near-neutral mean.

    Identically initialized LUTs make mixture coefficients almost irrelevant and
    starve the reference predictor of useful gradients. These mild warm/cool,
    contrast, saturation, and gamma pairs break that symmetry without imposing
    an extreme look. Every value remains trainable after initialization.
    """
    identity = identity_lut(size)
    luminance = (
        identity * identity.new_tensor([0.2126, 0.7152, 0.0722])[:, None, None, None]
    ).sum(0, keepdim=True)
    anchors = [
        identity * identity.new_tensor([1.06, 1.0, 0.94])[:, None, None, None],
        identity * identity.new_tensor([0.94, 1.0, 1.06])[:, None, None, None],
        (identity - 0.5) * 1.08 + 0.5,
        (identity - 0.5) * 0.92 + 0.5,
        luminance + (identity - luminance) * 1.12,
        luminance + (identity - luminance) * 0.88,
        identity.clamp_min(0).pow(0.92),
        identity.clamp_min(0).pow(1.08),
    ]
    selected = [anchors[index % len(anchors)] for index in range(basis_count)]
    return torch.stack(selected).clamp(0, 1)


class ReferenceLutModel(nn.Module):
    """Predict a safe blend of learned LUTs from target and reference features.

    A 3D lookup table maps an input RGB triplet to a new RGB triplet. The model
    learns several reusable LUT bases, then predicts non-negative coefficients
    that sum to one. This convex blend is bounded and compact enough for browser
    inference, unlike a network that generates every full-resolution pixel.
    """

    def __init__(self, basis_count: int = 8, lut_size: int = 33) -> None:
        super().__init__()
        self.basis_count = basis_count
        self.lut_size = lut_size
        self.histogram_bins = 8
        self.encoder = ImageEncoder()
        self.predictor = nn.Sequential(
            # Five learned feature interactions, channel statistics, and two
            # four-channel soft histograms describe both scene and treatment.
            nn.Linear(96 * 5 + 12 + 2 * 4 * self.histogram_bins, 160),
            nn.SiLU(),
            nn.Dropout(0.1),
            nn.Linear(160, basis_count),
        )
        self.basis = nn.Parameter(initial_lut_bases(lut_size, basis_count))

    @staticmethod
    def statistics(image: torch.Tensor) -> torch.Tensor:
        """Describe each RGB channel with its mean and standard deviation."""
        mean = image.mean(dim=(2, 3))
        std = image.std(dim=(2, 3), correction=0)
        return torch.cat((mean, std), dim=1)

    def color_distribution(self, image: torch.Tensor) -> torch.Tensor:
        """Summarize RGB and luminance distributions with soft histogram bins.

        Means and standard deviations cannot distinguish, for example, an image
        concentrated in shadows and highlights from one concentrated in the
        midtones. Each pixel contributes linearly to its neighboring bins, so
        this descriptor retains more tonal information while remaining smooth,
        differentiable, and exportable through ordinary ONNX operations.
        """
        luminance = (
            image * image.new_tensor([0.2126, 0.7152, 0.0722])[None, :, None, None]
        ).sum(1, keepdim=True)
        channels = torch.cat((image, luminance), dim=1).unsqueeze(2)
        centers = torch.linspace(
            0,
            1,
            self.histogram_bins,
            device=image.device,
            dtype=image.dtype,
        ).view(1, 1, self.histogram_bins, 1, 1)
        membership = (1 - (channels - centers).abs() * (self.histogram_bins - 1)).relu()
        return membership.mean(dim=(3, 4)).flatten(1)

    def predict_coefficients(self, source: torch.Tensor, reference: torch.Tensor):
        """Decide how strongly each learned LUT basis should influence the result."""
        # One batched encoder call produces a smaller ONNX graph and reduces
        # browser runtime dispatch overhead compared with two duplicated calls.
        paired_features = self.encoder(torch.cat((source, reference), dim=0))
        source_features, reference_features = paired_features.chunk(2, dim=0)
        # The model sees each image, their feature difference, and simple color
        # statistics. Their combination answers both "what is present?" and
        # "how does the desired reference differ from this source?"
        features = torch.cat(
            (
                source_features,
                reference_features,
                reference_features - source_features,
                (reference_features - source_features).abs(),
                reference_features * source_features,
                self.statistics(source),
                self.statistics(reference),
                self.color_distribution(source),
                self.color_distribution(reference),
            ),
            dim=1,
        )
        scores = self.predictor(features)
        # This is a numerically stable softmax written as primitive operations.
        # ONNX Runtime 1.19's static quantizer cannot calibrate a Softmax node,
        # while ReduceMax/Exp/ReduceSum/Div preserve the same smooth convex
        # weights in PyTorch, native ONNX, and ONNX Runtime Web.
        shifted = scores - scores.amax(dim=1, keepdim=True)
        exponentials = shifted.exp()
        return exponentials / exponentials.sum(dim=1, keepdim=True)

    def forward(self, source: torch.Tensor, reference: torch.Tensor):
        coefficients = self.predict_coefficients(source, reference)
        bounded_basis = self.basis.clamp(0, 1)
        lut = torch.einsum("bk,kcxyz->bcxyz", coefficients, bounded_basis)
        return lut, coefficients


def apply_lut(image: torch.Tensor, lut: torch.Tensor) -> torch.Tensor:
    """Apply a 3D LUT with differentiable trilinear interpolation.

    An RGB color usually falls between LUT grid points. The eight surrounding
    colors are sampled and blended according to distance. Because PyTorch can
    differentiate through these blends, training can update both the LUT bases
    and the network that chooses their coefficients.
    """
    batch, channels, height, width = image.shape
    size = lut.shape[-1]
    scaled = image.clamp(0, 1) * (size - 1)
    lower = scaled.floor().long()
    upper = (lower + 1).clamp(max=size - 1)
    # Autocast may produce a BF16/FP16 LUT while the source image remains FP32.
    # ``lerp`` requires its interpolation weights to match the sampled LUT dtype.
    fraction = (scaled - lower).to(dtype=lut.dtype)
    red0, green0, blue0 = lower[:, 0], lower[:, 1], lower[:, 2]
    red1, green1, blue1 = upper[:, 0], upper[:, 1], upper[:, 2]
    red_weight, green_weight, blue_weight = (
        fraction[:, 0],
        fraction[:, 1],
        fraction[:, 2],
    )
    flattened = lut.reshape(batch, channels, -1)

    def sample(red, green, blue):
        # Flattening converts a 3D coordinate into one gather index. This avoids
        # a Python loop over pixels and keeps interpolation accelerator-friendly.
        index = (blue * size * size + green * size + red).reshape(batch, 1, -1)
        return flattened.gather(2, index.expand(-1, channels, -1)).reshape(
            batch, channels, height, width
        )

    c000 = sample(red0, green0, blue0)
    c100 = sample(red1, green0, blue0)
    c010 = sample(red0, green1, blue0)
    c110 = sample(red1, green1, blue0)
    c001 = sample(red0, green0, blue1)
    c101 = sample(red1, green0, blue1)
    c011 = sample(red0, green1, blue1)
    c111 = sample(red1, green1, blue1)
    rw, gw, bw = red_weight[:, None], green_weight[:, None], blue_weight[:, None]
    c00 = c000.lerp(c100, rw)
    c10 = c010.lerp(c110, rw)
    c01 = c001.lerp(c101, rw)
    c11 = c011.lerp(c111, rw)
    return c00.lerp(c10, gw).lerp(c01.lerp(c11, gw), bw)
