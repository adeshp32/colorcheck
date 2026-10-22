# ColorCheck Reference Matcher Model Card

## Purpose

The model proposes a bounded global color treatment for one target photograph
from a separately chosen edited reference. It predicts a 33-by-33-by-33 3D LUT
that can be blended, masked, undone, and combined with ColorCheck's deterministic
tools. It does not generate pixels, invent scene content, or make irreversible
editing decisions.

## Architecture

- Framework: PyTorch training with ONNX Runtime Web inference.
- Inputs: 128-by-128 RGB target and reference analysis tensors.
- Encoder: shared depthwise-separable convolutional network.
- Conditioning: target/reference features, signed and absolute differences,
  feature interactions, and per-channel means and standard deviations.
- Output: a convex mixture of eight learned 33-cube LUT bases.
- Initialization: paired warm/cool, contrast, saturation, and gamma anchors with
  a near-neutral mean; all LUT values remain trainable.
- Size: 956,032 trainable parameters before quantization.
- Application: trilinear interpolation over the original-resolution photograph.

The 128-pixel inputs determine one global transform; they are not the exported
image. Full-resolution pixels remain local and pass through the existing editor.

## Supervision

Training balances two related objectives:

1. MIT-Adobe FiveK raw-to-expert pairs teach plausible professional treatment.
2. Deterministic shared-style pairs apply one known bounded recipe to unrelated
   raw scenes, providing exact supervision for reference-conditioned transfer.

A pairwise ranking loss compares the correct reference with a known-wrong style.
A second, same-style reference from another scene supplies a content-invariance
objective, while a training-only classifier teaches the shared encoder to retain
FiveK expert-treatment cues. Neither auxiliary path enters the exported graph.
Synthetic samples additionally supervise every point in their exact 33-cube LUT.
Balanced real and synthetic validation DeltaE76 plus held-out real-reference
discrimination selects the checkpoint. Test scenes are untouched until that
choice is complete.

## Evaluation

The final report retains per-photograph measurements and scene-clustered 95%
bootstrap confidence intervals for CIEDE2000, SSIM, PSNR, MAE, luminance, chroma,
edge agreement, and clipping. This prevents five edits of one source photograph
from being counted as five independent scenes. Controls include identity, the
current statistics matcher, incorrect references, reference sensitivity,
LUT-basis usage, runtime, and peak memory.

Separate real-expert and exact-synthetic reports must pass every evidence gate.
Each improvement gate combines scene-clustered statistical confidence with a
predeclared minimum practical effect, recorded in the evaluation summary.
PyTorch-to-ONNX and FP32-to-INT8 rendered pixels are compared independently.
The export manifest recommends no production artifact unless the checkpoint,
quality summary, and quantization evidence all agree.

## Intended Use

- A reversible starting point for reference-guided photographic color editing.
- Local browser inference followed by user-controlled strength and masking.
- Research, education, ablation studies, and documented portfolio demonstration.

## Out Of Scope

- Claiming a single objectively correct grade for every photograph.
- Local semantic relighting, restoration, super-resolution, or content creation.
- Replacing explicit crop, grain, sharpening, masking, or geometry controls.
- Automatic production promotion based only on successful training or low loss.

## Known Limitations

A global LUT cannot express spatially different edits without a user mask. FiveK
contains the aesthetic choices of five experts and cannot represent every camera,
skin tone, lighting condition, culture, or photographic genre. Synthetic recipes
cover declared controls, not all possible edits. Human visual review remains
mandatory even when numerical gates pass.

The first measured medium pilot improved real-photo color error over identity
but did not make the correct real reference outperform a shuffled one. That
checkpoint is not deployment-ready. The added conditioning objectives are a
measured response to this failure, not evidence that it has already been solved.

## Privacy And Delivery

Training photographs and checkpoints stay outside Git. Browser inference uses a
versioned, integrity-checked ONNX artifact; selected user images remain on the
user's device. If model loading or inference fails, deterministic editing remains
available and no photograph is uploaded as a fallback.
