from pathlib import Path

from colorcheck.config import AppSettings


def test_settings_apply_public_resource_bounds(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VCC_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("VCC_MAX_UPLOAD_MB", "5")
    monkeypatch.setenv("VCC_MAX_SOURCE_UPLOAD_MB", "8")
    monkeypatch.setenv("VCC_UPLOAD_CHUNK_MB", "99")
    monkeypatch.setenv("VCC_UPLOAD_TTL_HOURS", "0")
    monkeypatch.setenv("VCC_MIN_FREE_DISK_MB", "4")
    monkeypatch.setenv("VCC_MAX_QUEUED_JOBS", "99")
    monkeypatch.setenv("VCC_MAX_REQUEST_MB", "12")
    monkeypatch.setenv("VCC_MAX_VIDEO_SECONDS", "5")
    monkeypatch.setenv("VCC_MAX_VIDEO_MEGAPIXELS", "0.5")
    monkeypatch.setenv("VCC_JOB_TTL_HOURS", "0")
    monkeypatch.setenv("VCC_ANALYSES_PER_HOUR", "0")

    settings = AppSettings.from_environment()

    assert settings.storage_root == tmp_path.resolve()
    assert settings.max_upload_mb == 10
    assert settings.max_source_upload_mb == 10
    assert settings.upload_chunk_mb == 32
    assert settings.upload_ttl_hours == 1
    assert settings.min_free_disk_mb == 512
    assert settings.max_queued_jobs == 5
    assert settings.max_request_mb == 14
    assert settings.max_video_seconds == 10
    assert settings.max_video_pixels == 1_000_000
    assert settings.job_ttl_hours == 1
    assert settings.analyses_per_hour == 1
    assert settings.max_upload_bytes == 10 * 1024 * 1024
    assert settings.max_source_upload_bytes == 10 * 1024 * 1024
    assert settings.upload_chunk_bytes == 32 * 1024 * 1024
    assert settings.min_free_disk_bytes == 512 * 1024 * 1024
    assert settings.max_request_bytes == 14 * 1024 * 1024
