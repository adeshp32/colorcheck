from __future__ import annotations

from pathlib import Path

from colorcheck.web.jobs import JobStore


def test_job_store_recovers_interrupted_processing(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    job_id = store.new_job_id()
    input_dir = store.input_dir(job_id)
    input_dir.mkdir(parents=True)
    reference = input_dir / "reference.png"
    video = input_dir / "video.mp4"
    reference.write_bytes(b"reference")
    video.write_bytes(b"video")
    store.create(
        job_id,
        reference_path=reference,
        video_path=video,
        samples=24,
        strength=50,
        lighting_threshold=60,
    )
    store.update(job_id, status="processing", stage="Rendering", progress=70)

    assert store.recoverable() == [job_id]
    recovered = store.get(job_id)
    assert recovered["status"] == "queued"
    assert recovered["progress"] == 5
    assert store.active_count() == 1
