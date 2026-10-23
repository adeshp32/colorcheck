# TST100K Reference Matching Pilot

## Question

Can the lightweight browser-compatible LUT model use a supplied reference to
produce a better edit of an unseen photograph? V11 improved average color error
on FiveK, but its correct reference did not reliably outperform an incorrect
one. TST100K directly supplies source, reference, and desired result triplets,
making this a more relevant supervised test.

## Reproducible setup

- Upstream dataset: [ToneStyle/TST100K](https://huggingface.co/datasets/ToneStyle/TST100K),
  pinned to commit `63bf13833b75407c862d608c3d81281d0a35b61f`.
- Private Kaggle pilot: 512 training, 96 validation, and 96 test triplets;
  four epochs, 128-pixel training inputs, batch size eight, seed 42.
- The SHA-256 split applies to both content and reference source identities.
  Cross-split pairs are dropped. Each target photograph occurs at most once
  per partition. Validation chooses the checkpoint; test is opened once.
- The model predicts a convex mixture of eight learned 33-cube LUTs. Training
  uses reconstruction, correct-versus-wrong reference ranking, a neutral
  self-reference anchor, edge protection, and LUT smoothness. The browser would
  apply the LUT at full photo resolution if the model later passes its gates.
- Only selected images are downloaded to Kaggle scratch. Split paths, metrics,
  and the best checkpoint are saved as private Kaggle outputs.

## Predeclared comparisons

All color results are measured as CIEDE2000 against the triplet target. The
report includes an unchanged-source baseline, the current bounded statistics
matcher, the trained model with the correct reference, and the same model with
another triplet's reference. Each difference has a target-photo bootstrap 95%
interval. The correct-reference, current-matcher, and unchanged-source
advantages must each have an interval entirely above zero before the pilot is
considered promising. A model that changes output but ignores the reference
does not pass.

The pilot is an early experiment, not a deployment decision. If these gates
pass, a broader sample, output review across portraits/food/general scenes,
browser ONNX parity, phone latency, memory, and quantization tests still remain.

## Interpretation limits

TST100K combines images from PPR10K, MIT-Adobe FiveK, and Food-101 and includes
preset-rendered targets. Its target is a dataset-specific definition of a
successful style transfer, not a unique professional edit. A global LUT cannot
recreate local retouching, selective masks, or every camera rendering choice.
The dataset and its underlying sources have research-use terms; photographs
and checkpoints remain outside this public repository.
