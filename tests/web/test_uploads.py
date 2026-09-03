from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from colorcheck.web.security import PublicInputError
from colorcheck.web.uploads import UploadStore


def upload_store(tmp_path: Path) -> UploadStore:
    return UploadStore(
        tmp_path / "uploads",
        max_source_bytes=1024,
        max_image_bytes=512,
        chunk_bytes=4,
        min_free_bytes=0,
        ttl_seconds=60,
    )


def test_upload_session_resumes_and_is_consumed_without_original_name(tmp_path: Path) -> None:
    store = upload_store(tmp_path)
    session, token = store.create(role="video", filename="private-name.MOV", expected_bytes=6)

    first = tmp_path / "first.chunk"
    first.write_bytes(b"1234")
    updated = store.commit_chunk(session.session_id, token, offset=0, chunk_path=first)
    assert updated.received_bytes == 4
    assert store.get(session.session_id, token).received_bytes == 4

    second = tmp_path / "second.chunk"
    second.write_bytes(b"56")
    updated = store.commit_chunk(session.session_id, token, offset=4, chunk_path=second)
    assert updated.received_bytes == 6
    assert store.complete(session.session_id, token).status == "complete"

    destination = store.consume(
        session.session_id,
        token,
        role="video",
        destination_dir=tmp_path / "job" / "inputs",
    )
    assert destination == tmp_path / "job" / "inputs" / "video.mov"
    assert destination.read_bytes() == b"123456"
    assert not (store.root / session.session_id).exists()


def test_upload_session_rejects_wrong_token_offset_and_oversized_chunk(tmp_path: Path) -> None:
    store = upload_store(tmp_path)
    session, token = store.create(role="video", filename="clip.mp4", expected_bytes=6)
    chunk = tmp_path / "chunk"
    chunk.write_bytes(b"12345")

    with pytest.raises(PublicInputError) as wrong_token:
        store.get(session.session_id, "not-the-token")
    assert wrong_token.value.status_code == 404

    with pytest.raises(PublicInputError) as oversized:
        store.commit_chunk(session.session_id, token, offset=0, chunk_path=chunk)
    assert oversized.value.status_code == 413

    chunk.write_bytes(b"12")
    with pytest.raises(PublicInputError) as wrong_offset:
        store.commit_chunk(session.session_id, token, offset=1, chunk_path=chunk)
    assert wrong_offset.value.status_code == 409


def test_expired_upload_sessions_are_removed(tmp_path: Path) -> None:
    store = upload_store(tmp_path)
    session, _token = store.create(role="reference", filename="still.png", expected_bytes=4)
    metadata = store.root / session.session_id / "upload.json"
    old_timestamp = time.time() - 120
    payload = metadata.read_text(encoding="utf-8").replace(
        f'"updated_at":{session.updated_at}', f'"updated_at":{old_timestamp}'
    )
    metadata.write_text(payload, encoding="utf-8")
    os.utime(store.root / session.session_id, (old_timestamp, old_timestamp))

    assert store.cleanup_expired() == 1
    assert not (store.root / session.session_id).exists()


def test_upload_session_can_be_cancelled_immediately(tmp_path: Path) -> None:
    store = upload_store(tmp_path)
    session, token = store.create(role="video", filename="clip.mp4", expected_bytes=4)

    store.cancel(session.session_id, token)

    assert not (store.root / session.session_id).exists()
