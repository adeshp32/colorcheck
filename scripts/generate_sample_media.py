from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def main() -> int:
    output_dir = Path("sample-media")
    output_dir.mkdir(parents=True, exist_ok=True)
    width, height = 640, 360
    x = np.linspace(0, 1, width, dtype=np.float32)
    y = np.linspace(0, 1, height, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)
    base = np.zeros((height, width, 3), dtype=np.float32)
    base[:, :, 0] = 0.42 + 0.24 * xx
    base[:, :, 1] = 0.38 + 0.28 * yy
    base[:, :, 2] = 0.34 + 0.18 * (1 - xx)
    base = np.clip(base, 0, 1)

    reference = (base * 255).astype(np.uint8)
    cv2.imwrite(str(output_dir / "reference.png"), cv2.cvtColor(reference, cv2.COLOR_RGB2BGR))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_dir / "target.mp4"), fourcc, 24.0, (width, height))
    for index in range(72):
        drift = index / 71
        frame = base.copy()
        frame *= 0.92 + 0.08 * np.sin(drift * np.pi)
        frame[:, :, 0] *= 1.0 + 0.05 * drift
        frame[:, :, 2] *= 1.0 - 0.07 * drift
        frame = np.clip(frame, 0, 1)
        writer.write(cv2.cvtColor((frame * 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
    writer.release()
    print(f"Wrote {output_dir / 'reference.png'} and {output_dir / 'target.mp4'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
