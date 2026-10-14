# Capacity and a Small Training Pilot

These are proposed follow-up changes, not features deployed by the upload UI update.

## Larger Files and User Load

The current code permits source videos up to 1 GB, uses 16 MB resumable chunks,
samples representative frames in the browser, and limits rendering to one slot.
Actual throughput still depends on duration, resolution, codec, and CPU capacity.

Recommended order:

1. Benchmark representative 100 MB, 500 MB, and 1 GB inputs on the actual VM.
   Record peak memory, temporary disk usage, upload time, and render time.
2. Reserve temporary storage and queue capacity before accepting a large upload.
   Use a local SQLite database for job state, reserved bytes, expiry, and worker
   leases. Claim reservations in a transaction and release them on completion,
   failure, cancellation, or expiry. Store metadata in SQL; keep media out of it.
3. Retain browser sampling and reuse compact analysis results when users change
   an edit. Keep full-resolution rendering on demand and one render at a time.
4. Improve client-side clip selection before upload. Estimating a segment's size
   from average bitrate is approximate; enforce the actual prepared file size.
   Frame-accurate local trimming needs supported browser codecs and a fallback.
5. If temporary storage becomes the bottleneck, evaluate private object storage
   with signed multipart uploads. Enforce application quotas before issuing upload
   permissions, delete inputs after use, and clean up abandoned multipart uploads.

SQLite is free and included with Python. WAL permits concurrent readers and one
writer, suitable for short metadata transactions on this single-server setup.
It does not add storage, CPU power, or video encoding throughput.
Reference: https://www.sqlite.org/wal.html

Cloudflare R2 Standard currently includes 10 GB-month of storage, 1 million Class A
operations, and 10 million Class B operations monthly, with no direct egress fee.
Beyond that, Standard storage is $0.015 per GB-month, with separate operation fees.
For example, 50 GB-month total is approximately $0.60 in storage beyond the free
allowance, before operation charges. Free allowances are not a hard spending cap.
Moving inputs to R2 would require changes to upload, access control, cleanup, and
render input handling; it does not make the existing CPU encode faster.
Reference: https://developers.cloudflare.com/r2/pricing/

Do not raise the public 1 GB ceiling until VM benchmarks and aggregate storage
reservations demonstrate that larger inputs are practical.

## Training Within 50 GB

Start with a bounded correction regressor, using PyTorch training and lightweight
NumPy inference. No trained model has been
produced or enabled by this UI change.

First milestone:

- Curate 200-500 distinct owned or appropriately licensed photographs.
- Generate 8-16 controlled exposure, saturation, contrast, and color-gain
  perturbations per photo. Pair each variant with its original.
- Split by original photo and source group before augmentation to prevent leakage.
- Train a small model that predicts bounded adjustments from reference and target
  color statistics. Compare it with identity and the existing rule-based method.
- Evaluate held-out reconstruction/color error, clipping, unchanged-image behavior,
  and unfamiliar-image fallback. Inspect portrait, indoor, daylight, and low-light
  failures separately. Keep test images out of hyperparameter selection.
- Review real, independently edited examples before enabling any public model.

This learns recovery from the defined synthetic disturbances. It does not establish
expert taste, scene understanding, or reliable mixed-light correction by itself.
An image-first editor is a useful next application because it avoids temporal
flicker and video encoding during model evaluation.

Suggested storage ceilings, not minimum requirements:

| Item | Budget |
| --- | ---: |
| Curated original photos and provenance | 10 GB |
| Resized training/evaluation data | 4 GB |
| Environment and dependencies | 5 GB |
| Model checkpoints, metrics, and review examples | 3 GB |
| Unallocated workspace and operating-system headroom | 28 GB |

Train on the developer's computer, then deploy only the validated small model.
The public Oracle VM should remain dedicated to interactive jobs and rendering.
Training will not expand upload limits or speed up FFmpeg exports.

Research datasets can help evaluate white balance, but licenses must match the
intended public use. Rendered WB's official repository identifies both software
and dataset as research-only, requiring a license for commercial applications.
Do not assume public downloads permit deploying a derived model commercially.
Reference: https://github.com/mahmoudnafifi/WB_sRGB

Public uploads are not training data. Training sources, licenses, and explicit
permissions belong in a separate local manifest.
