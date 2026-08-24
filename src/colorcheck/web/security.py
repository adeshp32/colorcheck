from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
JOB_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


class PublicInputError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class MediaLimits:
    max_upload_bytes: int
    max_video_seconds: int
    max_video_pixels: int
    max_image_pixels: int


@dataclass
class _RateBucket:
    started_at: float
    count: int


class FixedWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = max(1, limit)
        self.window_seconds = max(1, window_seconds)
        self._buckets: dict[str, _RateBucket] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> tuple[bool, int]:
        current = time.monotonic() if now is None else now
        with self._lock:
            if len(self._buckets) >= 4096:
                stale_keys = [
                    bucket_key
                    for bucket_key, bucket in self._buckets.items()
                    if current - bucket.started_at >= self.window_seconds
                ]
                for bucket_key in stale_keys:
                    self._buckets.pop(bucket_key, None)
                if len(self._buckets) >= 4096:
                    self._buckets.pop(next(iter(self._buckets)))
            bucket = self._buckets.get(key)
            if bucket is None or current - bucket.started_at >= self.window_seconds:
                self._buckets[key] = _RateBucket(started_at=current, count=1)
                return True, 0
            if bucket.count >= self.limit:
                retry_after = max(1, round(self.window_seconds - (current - bucket.started_at)))
                return False, retry_after
            bucket.count += 1
            return True, 0


def _normalized_origin(value: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        default_port = 443 if parsed.scheme == "https" else 80
        return parsed.scheme, parsed.hostname.lower().rstrip("."), parsed.port or default_port
    except ValueError:
        return None


def upload_origin_allowed(
    origin: str | None,
    expected_origins: tuple[str, ...],
    fetch_site: str | None = None,
) -> bool:
    """Accept browser same-origin uploads while remaining proxy and localhost aware."""
    site = (fetch_site or "").strip().lower()
    if site == "cross-site":
        return False
    if site == "same-origin":
        return True
    if not origin:
        return True

    submitted = _normalized_origin(origin)
    if submitted is None:
        return False
    for candidate in expected_origins:
        expected = _normalized_origin(candidate)
        if submitted == expected:
            return True
        if expected is not None:
            same_local_origin = (
                submitted[0] == expected[0]
                and submitted[2] == expected[2]
                and submitted[1] in LOOPBACK_HOSTS
                and expected[1] in LOOPBACK_HOSTS
            )
            if same_local_origin:
                return True
    return False


def upload_destination(input_dir: Path, filename: str | None, role: str) -> Path:
    suffix = Path(filename or "").suffix.lower()
    allowed = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS if role == "reference" else VIDEO_EXTENSIONS
    if suffix not in allowed:
        allowed_names = ", ".join(sorted(allowed))
        raise PublicInputError(f"Unsupported {role} file type. Allowed extensions: {allowed_names}.")
    return input_dir / f"{role}{suffix}"


def save_upload_limited(file_object: BinaryIO, destination: Path, max_bytes: int) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with destination.open("wb") as handle:
            while chunk := file_object.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise PublicInputError(
                        f"Each upload must be {max_bytes // (1024 * 1024)} MB or smaller.",
                        status_code=413,
                    )
                handle.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    if total == 0:
        destination.unlink(missing_ok=True)
        raise PublicInputError("Uploaded files cannot be empty.")
    return total


def _probe_video(path: Path) -> dict[str, object]:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError("ffprobe is required to validate uploaded videos.")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,duration:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        raise PublicInputError("The uploaded video could not be decoded.")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PublicInputError("The uploaded video metadata is invalid.") from exc


def validate_video(path: Path, limits: MediaLimits) -> None:
    probe = _probe_video(path)
    streams = probe.get("streams", [])
    if not isinstance(streams, list) or not streams:
        raise PublicInputError("The uploaded file does not contain a video stream.")
    stream = streams[0]
    if not isinstance(stream, dict):
        raise PublicInputError("The uploaded video metadata is invalid.")
    width = int(stream.get("width", 0) or 0)
    height = int(stream.get("height", 0) or 0)
    format_data = probe.get("format", {})
    format_duration = format_data.get("duration") if isinstance(format_data, dict) else None
    duration = float(format_duration or stream.get("duration", 0) or 0)
    if width <= 0 or height <= 0 or duration <= 0:
        raise PublicInputError("The uploaded video is missing usable dimensions or duration.")
    if width * height > limits.max_video_pixels:
        raise PublicInputError("Video resolution exceeds this deployment's processing limit.")
    if duration > limits.max_video_seconds:
        raise PublicInputError(
            f"Videos must be {limits.max_video_seconds} seconds or shorter for this public demo."
        )


def validate_image(path: Path, limits: MediaLimits) -> None:
    try:
        with Image.open(path) as image:
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise PublicInputError("The reference image could not be decoded.") from exc
    if width <= 0 or height <= 0 or width * height > limits.max_image_pixels:
        raise PublicInputError("Reference image dimensions are too large.")


def validate_media(path: Path, role: str, limits: MediaLimits) -> None:
    if path.suffix.lower() in VIDEO_EXTENSIONS:
        validate_video(path, limits)
    elif role == "reference" and path.suffix.lower() in IMAGE_EXTENSIONS:
        validate_image(path, limits)
    else:
        raise PublicInputError(f"Unsupported {role} media file.")


def validate_job_id(job_id: str) -> None:
    if JOB_ID_PATTERN.fullmatch(job_id) is None:
        raise PublicInputError("Invalid job identifier.", status_code=404)


def cleanup_expired_jobs(jobs_root: Path, ttl_seconds: int, now: float | None = None) -> int:
    if not jobs_root.exists():
        return 0
    current = time.time() if now is None else now
    removed = 0
    for job_dir in jobs_root.iterdir():
        if not job_dir.is_dir() or job_dir.is_symlink() or JOB_ID_PATTERN.fullmatch(job_dir.name) is None:
            continue
        try:
            expired = current - job_dir.stat().st_mtime > ttl_seconds
        except OSError:
            continue
        if expired:
            shutil.rmtree(job_dir, ignore_errors=True)
            removed += 1
    return removed
