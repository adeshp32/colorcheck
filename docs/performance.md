# Export Performance

ColorCheck applies color corrections through a 33-point 3D LUT in FFmpeg. The quality-preserved master is encoded first, and the browser preview is derived from that completed master. This removes the former Python frame loop, MPEG-4 intermediate, redundant H.264 transcode, and second application of the correction.

## Encoder Selection

- Native macOS runs use VideoToolbox automatically for supported H.264 and HEVC sources.
- HEVC Main 10 sources remain HEVC Main 10 with their 10-bit pixel format and HDR color tags.
- H.264 sources remain H.264 when their pixel format is supported.
- Linux containers, including the planned Oracle deployment, and unsupported formats use the
  optimized high-quality `libx265` or `libx264` software path.
- The browser preview is H.264 and is bounded to 1080p. It is not the archival output.

If a hardware encoder is advertised but cannot open the requested source profile, ColorCheck removes the partial file and retries through the software path.

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
