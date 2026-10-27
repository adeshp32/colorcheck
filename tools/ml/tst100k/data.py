"""Select and stage a small, scene-disjoint TST100K triplet experiment.

The upstream manifest is the pairing authority. Scene IDs, rather than rows,
determine the split: a photograph used as either content or reference cannot
appear in a different split. Images are downloaded only inside Kaggle scratch.
"""

from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from urllib.parse import quote
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

import torch
import numpy as np
from PIL import Image, ImageOps
from torch.utils.data import Dataset

DATASET_REVISION = "63bf13833b75407c862d608c3d81281d0a35b61f"
BASE_URL = f"https://huggingface.co/datasets/ToneStyle/TST100K/resolve/{DATASET_REVISION}"
SPLITS = ("train", "validation", "test")


class RequestPacer:
    """Space image requests and share server backoff across worker threads."""

    def __init__(self, interval_seconds: float = 0.75):
        self.interval_seconds = interval_seconds
        self.next_request_at = 0.0
        self.lock = Lock()

    def wait(self) -> None:
        while True:
            with self.lock:
                remaining = self.next_request_at - time.monotonic()
                if remaining <= 0:
                    self.next_request_at = time.monotonic() + self.interval_seconds
                    return
            time.sleep(remaining)

    def pause_for(self, seconds: float) -> None:
        with self.lock:
            self.next_request_at = max(self.next_request_at, time.monotonic() + seconds)


def scene_id(path: str) -> str:
    """Map source and preset-rendered copies to one original photograph."""
    return Path(path).stem.split("_")[0]


def scene_split(identifier: str, seed: int) -> str:
    """Hash each photograph once; references cannot cross a split boundary."""
    digest = hashlib.sha256(f"{seed}:{identifier}".encode()).digest()
    bucket = int.from_bytes(digest[:8], "big") % 10
    return "train" if bucket < 8 else "validation" if bucket == 8 else "test"


def select_triplets(
    records: list[dict[str, str]], counts: tuple[int, int, int], seed: int
) -> dict[str, list[dict[str, str]]]:
    """Select a reproducible sample with distinct target scenes in each split.

    Triplets whose content and reference belong to different partitions are
    omitted. This costs data but prevents direct scene reuse across evaluation.
    """
    selected = {split: [] for split in SPLITS}
    used_content = {split: set() for split in SPLITS}
    ranked = sorted(
        records,
        key=lambda row: hashlib.sha256(
            f"{seed}:{row['content']}:{row['reference']}:{row['gt']}".encode()
        ).digest(),
    )
    for row in ranked:
        if set(row) != {"content", "reference", "gt"}:
            raise ValueError("Each TST100K record must have content, reference, and gt")
        content_id = scene_id(row["content"])
        reference_id = scene_id(row["reference"])
        if content_id == reference_id or scene_id(row["gt"]) != content_id:
            continue
        split = scene_split(content_id, seed)
        if scene_split(reference_id, seed) != split:
            continue
        if content_id in used_content[split] or len(selected[split]) >= counts[SPLITS.index(split)]:
            continue
        selected[split].append(row)
        used_content[split].add(content_id)
        if all(len(selected[name]) == counts[index] for index, name in enumerate(SPLITS)):
            break
    actual = tuple(len(selected[name]) for name in SPLITS)
    if actual != counts:
        raise ValueError(f"Insufficient disjoint triplets: requested {counts}, found {actual}")
    return selected


def fetch_manifest() -> list[dict[str, str]]:
    """Read the pinned upstream pairing manifest without storing it in Git."""
    with urlopen(f"{BASE_URL}/triplet.json", timeout=120) as response:
        return json.load(response)


def _download_one(root: Path, relative: str, max_bytes: int, pacer: RequestPacer) -> int:
    """Stream one image to Kaggle scratch, with bounded size and retries."""
    destination = root / relative
    if destination.is_file():
        return destination.stat().st_size
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = f"{BASE_URL}/{quote(relative, safe='/')}"
    for attempt in range(7):
        temporary = destination.with_name(destination.name + ".part")
        try:
            pacer.wait()
            with urlopen(url, timeout=90) as response:
                size = 0
                with temporary.open("wb") as output:
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > max_bytes:
                            raise ValueError(f"Image exceeds {max_bytes} bytes: {relative}")
                        output.write(chunk)
            with Image.open(temporary) as image:
                image.verify()
            temporary.replace(destination)
            return size
        except HTTPError as error:
            temporary.unlink(missing_ok=True)
            if error.code not in (429, 502, 503, 504) or attempt == 6:
                raise
            retry_after = error.headers.get("Retry-After")
            try:
                delay = max(1.0, float(retry_after)) if retry_after else 0.0
            except ValueError:
                delay = 0.0
            delay = min(300.0, max(delay, 20.0 * 2**attempt))
            pacer.pause_for(delay)
            print(f"Data host HTTP {error.code}; pausing image requests for {delay:.0f}s", flush=True)
        except (URLError, OSError, ValueError) as error:
            temporary.unlink(missing_ok=True)
            if attempt == 6 or isinstance(error, ValueError):
                raise
            time.sleep(min(30, 2**attempt))
    raise RuntimeError("Unreachable download retry state")


def stage_images(
    selected: dict[str, list[dict[str, str]]], root: Path, workers: int = 2
) -> dict[str, int]:
    """Download only selected files; the full 94 GB collection is never staged."""
    paths = sorted({path for rows in selected.values() for row in rows for path in row.values()})
    total_bytes = 0
    pacer = RequestPacer()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(_download_one, root, path, 40_000_000, pacer): path for path in paths}
        for completed, task in enumerate(as_completed(pending), 1):
            total_bytes += task.result()
            if completed % 250 == 0 or completed == len(paths):
                print(json.dumps({"downloadedFiles": completed, "totalFiles": len(paths)}), flush=True)
    return {"files": len(paths), "bytes": total_bytes}


class TripletDataset(Dataset):
    """Decode aligned source/answer pixels and an independent style reference."""

    def __init__(self, rows: list[dict[str, str]], root: Path, size: int = 128):
        self.rows = rows
        self.root = root
        self.size = size

    def __len__(self) -> int:
        return len(self.rows)

    def _image(self, path: str) -> torch.Tensor:
        with Image.open(self.root / path) as loaded:
            image = ImageOps.exif_transpose(loaded).convert("RGB")
            image = image.resize((self.size, self.size), Image.Resampling.BILINEAR)
            pixels = torch.from_numpy(np.array(image, copy=True))
        return pixels.permute(2, 0, 1).float().div_(255)

    def __getitem__(self, index: int) -> dict:
        row = self.rows[index]
        return {
            "source": self._image(row["content"]),
            "reference": self._image(row["reference"]),
            "expected": self._image(row["gt"]),
            "scene": scene_id(row["content"]),
        }


def save_split_manifest(selected: dict, path: Path, seed: int) -> None:
    """Record every pairing and revision needed to reproduce the experiment."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"datasetRevision": DATASET_REVISION, "seed": seed, "splits": selected}, indent=2)
    )
