from __future__ import annotations

import io
import os
import time

import pytest

from video_color_checker.security import (
    FixedWindowRateLimiter,
    PublicInputError,
    cleanup_expired_jobs,
    save_upload_limited,
    upload_destination,
    validate_job_id,
)


def test_upload_destination_uses_generic_name_and_validates_type(tmp_path) -> None:
    path = upload_destination(tmp_path, "private-client-name.MOV", "video")

    assert path == tmp_path / "video.mov"
    with pytest.raises(PublicInputError):
        upload_destination(tmp_path, "payload.exe", "video")


def test_limited_upload_removes_partial_file(tmp_path) -> None:
    destination = tmp_path / "video.mp4"

    with pytest.raises(PublicInputError) as exc_info:
        save_upload_limited(io.BytesIO(b"12345"), destination, max_bytes=4)

    assert exc_info.value.status_code == 413
    assert not destination.exists()


def test_rate_limiter_resets_after_window() -> None:
    limiter = FixedWindowRateLimiter(limit=2, window_seconds=60)

    assert limiter.allow("client", now=0) == (True, 0)
    assert limiter.allow("client", now=1) == (True, 0)
    allowed, retry_after = limiter.allow("client", now=2)
    assert not allowed
    assert retry_after == 58
    assert limiter.allow("client", now=61) == (True, 0)


def test_cleanup_only_removes_expired_job_directories(tmp_path) -> None:
    old_job = tmp_path / ("a" * 32)
    current_job = tmp_path / ("b" * 32)
    unrelated = tmp_path / "keep-me"
    old_job.mkdir()
    current_job.mkdir()
    unrelated.mkdir()
    old_timestamp = time.time() - 10_000
    os.utime(old_job, (old_timestamp, old_timestamp))

    removed = cleanup_expired_jobs(tmp_path, ttl_seconds=3600)

    assert removed == 1
    assert not old_job.exists()
    assert current_job.exists()
    assert unrelated.exists()


def test_job_ids_are_restricted() -> None:
    validate_job_id("a" * 32)
    with pytest.raises(PublicInputError):
        validate_job_id("../../private")
