# Learned Enhancement

## What is shipped

An optional pretrained Image-Adaptive-3DLUT enhancement model, developed in
PyTorch by Hui Zeng and collaborators, exported by ColorCheck to ONNX and run in
a browser worker using ONNX Runtime Web's single-thread WASM backend.

This is learned enhancement, not neural reference matching. ColorCheck has not
trained these weights. No photograph is uploaded and no GPU backend is required.
The existing manual editor still works when model loading or inference fails.
The integration milestone is complete for local technical testing. Demonstrated
perceptual improvement and broad real-device reliability are separate, pending gates.

## Provenance and reproducibility

- Upstream: https://github.com/HuiZeng/Image-Adaptive-3DLUT
- Revision: `b491f6df64a588864739a157db271e5c848e1805`
- License: Apache-2.0; license and attribution are included beside the model.
- Checkpoints: original paired `sRGB/classifier.pth` and `sRGB/LUTs.pth`.
- Export: `tools/ml/export_adaptive_lut.py`, with SHA-256 checkpoint validation
  and `torch.load(..., weights_only=True)`.
- Manifest: `web/assets/models/adaptive-lut/manifest.json`, recording checkpoint
  hashes, artifact hash, tensor layout, versions, and numerical comparison results.

Use a separate Python environment if rebuilding:

```sh
python -m venv .local/ml-environment
.local/ml-environment/bin/pip install -r tools/ml/requirements.txt
.local/ml-environment/bin/python tools/ml/export_adaptive_lut.py
npm ci
npm run prepare:ml
```

The runtime is pinned to ONNX Runtime Web 1.30.0. Its license and third-party
notices are included in `web/vendor/onnxruntime/`. Runtime files are served by the
same static host, not a third-party script CDN. No model training or dataset
download is needed for this integration.

## Browser flow

1. The user explicitly requests analysis in the Match panel.
2. A 256-by-256 sRGB sample is passed to a lazily created ML worker.
3. The worker loads the same-origin model, verifies its hash, and optionally
   caches the model using the browser Cache API.
4. The CNN predicts coefficients for three learned 33-by-33-by-33 color LUTs.
5. Their weighted combination is returned as one transform.
6. A sampled clipping assessment chooses an initial strength of 35%, 25%, 15%, or 0%.
7. The regular pixel worker applies that LUT before reference matching and manual edits.
8. Preview and export reuse the prediction; moving sliders does not rerun the model.

The ONNX model is approximately 2.41 MB. Initial ML use also loads approximately
14.8 MB of WASM/runtime files. Total download is larger than the model alone.
Cached availability is not guaranteed; browsers may evict storage. Clearing the
model cache does not delete the original photograph or the current transform.
The app is not a fully offline PWA.

## Safeguards and limitations

- Nonfinite or malformed LUTs are rejected.
- At full strength, the enhancement stage limits each channel's shift to 0.25
  in normalized sRGB. Lower strengths blend that bounded change.
- The initial suggestion is reduced when sampled clipping increases by more
  than one percentage point. Users can explicitly raise the strength afterward.
- Nearly flat images are excluded because normalization can become sensitive
  to floating-point differences and there is little useful tonal detail.
- Guards assess this enhancement stage, not the final result of every subsequent
  manual adjustment. They do not establish aesthetic correctness or skin protection.
- The model changes color and tone. It does not synthesize objects, restore
  missing detail, denoise, upscale, or develop camera RAW.

## Evaluation status

The export script compares full LUT output against PyTorch on black, white,
gradient, and seeded-noise fixtures. The white/gradient/noise tolerance is
`0.0001`. Entirely black input has a documented tolerance of `1/255` because
near-zero InstanceNorm variance amplifies floating-point differences. Its
measured maximum error was approximately `0.00295`; flat-image enhancement is
therefore not offered in the UI.

Browser checks additionally compare 54 sampled LUT entries on the same gradient
fixture against PyTorch, run real ML inference and image export, and verify the
manual fallback on model-unavailable responses. The first local Chrome run showed
a maximum sampled LUT error of approximately `0.00000024`. This is a numeric
comparison, not a perceptual-quality score or a promise for other devices.

Real-photo preference tests, held-out paired quality evaluation, broad device
latency/memory measurements, and tagged-color validation remain pending. No
claim of beating the existing matcher or professional editors is made.
