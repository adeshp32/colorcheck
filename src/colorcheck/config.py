from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    storage_root: Path
    max_upload_mb: int
    max_source_upload_mb: int
    upload_chunk_mb: int
    upload_ttl_hours: int
    min_free_disk_mb: int
    max_queued_jobs: int
    max_request_mb: int
    max_video_seconds: int
    max_video_pixels: int
    max_image_pixels: int
    job_ttl_hours: int
    analyses_per_hour: int

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_request_bytes(self) -> int:
        return self.max_request_mb * 1024 * 1024

    @property
    def max_source_upload_bytes(self) -> int:
        return self.max_source_upload_mb * 1024 * 1024

    @property
    def upload_chunk_bytes(self) -> int:
        return self.upload_chunk_mb * 1024 * 1024

    @property
    def min_free_disk_bytes(self) -> int:
        return self.min_free_disk_mb * 1024 * 1024

    @classmethod
    def from_environment(cls) -> AppSettings:
        max_upload_mb = max(10, int(os.environ.get("VCC_MAX_UPLOAD_MB", "250")))
        default_request_mb = max_upload_mb * 2 + 4
        max_request_mb = max(
            max_upload_mb + 4,
            int(os.environ.get("VCC_MAX_REQUEST_MB", str(default_request_mb))),
        )
        max_source_upload_mb = max(
            max_upload_mb,
            int(os.environ.get("VCC_MAX_SOURCE_UPLOAD_MB", "1024")),
        )
        return cls(
            storage_root=Path(os.environ.get("VCC_STORAGE_DIR", "storage")).resolve(),
            max_upload_mb=max_upload_mb,
            max_source_upload_mb=max_source_upload_mb,
            upload_chunk_mb=max(
                1,
                min(32, int(os.environ.get("VCC_UPLOAD_CHUNK_MB", "16"))),
            ),
            upload_ttl_hours=max(1, int(os.environ.get("VCC_UPLOAD_TTL_HOURS", "2"))),
            min_free_disk_mb=max(512, int(os.environ.get("VCC_MIN_FREE_DISK_MB", "4096"))),
            max_queued_jobs=max(1, min(5, int(os.environ.get("VCC_MAX_QUEUED_JOBS", "2")))),
            max_request_mb=max_request_mb,
            max_video_seconds=max(10, int(os.environ.get("VCC_MAX_VIDEO_SECONDS", "1800"))),
            max_video_pixels=max(
                1_000_000,
                round(
                    float(os.environ.get("VCC_MAX_VIDEO_MEGAPIXELS", "8.3"))
                    * 1_000_000
                ),
            ),
            max_image_pixels=50_000_000,
            job_ttl_hours=max(1, int(os.environ.get("VCC_JOB_TTL_HOURS", "6"))),
            analyses_per_hour=max(1, int(os.environ.get("VCC_ANALYSES_PER_HOUR", "6"))),
        )
