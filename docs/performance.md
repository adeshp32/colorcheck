# Export Performance

ColorCheck uses local browser decoding to choose visually diverse analysis frames, caches reference features, and applies final edits through FFmpeg. Trim regions, crop, text, lighting mode, color-wheel tint, B&W, and the 33-point correction LUT share one filter graph and one encode. Requested video streams directly to the browser instead of being rendered to server storage first.

## Encoder Selection

- Legacy CLI exports on macOS use VideoToolbox automatically for supported H.264 and HEVC sources.
- HEVC Main 10 sources remain HEVC Main 10 with their 10-bit pixel format and HDR color tags.
- H.264 sources remain H.264 when their pixel format is supported.
- Linux containers, including the Oracle deployment, and unsupported formats use the
  optimized high-quality `libx265` or `libx264` software path.
- The browser preview is H.264 and is bounded to 1080p. It is not the archival output.

On-demand web masters retain full source resolution, supported codec family, pixel format, and color metadata. Audio is copied bit-for-bit when the timeline is unchanged; temporal edits require an audio re-encode to build the new timeline.

## Reference Benchmark

Measured on an Apple M4 MacBook Air with 16 GB RAM using a six-second segment of 3840x2160, 30 fps, HEVC Main 10, BT.2020/HLG footage with AAC audio.

| Pipeline | Wall time |
| --- | ---: |
| Previous Python/OpenCV preview | 58.88 s |
| Previous `libx265` master | 85.68 s |
| Previous total | 144.56 s |
| Optimized master and preview | 20.80 s |

The optimized end-to-end path is approximately 6.9 times faster for this case.

Run the optimized benchmark against local footage with:

```bash
python scripts/benchmark_exports.py path/to/video.mov --seconds 6
```

## Fidelity Checks

The optimized master retained:

- HEVC Main 10 codec and profile
- 3840x2160 resolution
- `yuv420p10le` pixel format
- limited range, BT.2020 non-constant luminance, BT.2020 primaries, and HLG transfer metadata
- source frame rate and timing within one frame interval
- a bit-identical copied AAC audio stream

Against the former high-quality software master, the optimized master measured 99.98 VMAF after decoding and matched resolution. The hardware output used a higher bitrate than the software reference; the speed gain does not come from reducing resolution, bit depth, or the master quality target.

Color correction necessarily changes pixels and therefore requires a new encode. "Quality-preserved" means avoiding perceptible or unnecessary generational loss while retaining supported source characteristics; it does not mean that the corrected compressed bytes can equal the uncorrected source bytes.
