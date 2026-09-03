from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import secrets
import shutil
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from colorcheck.web.security import (
    IMAGE_EXTENSIONS,
    JOB_ID_PATTERN,
    VIDEO_EXTENSIONS,
    PublicInputError,
)


@dataclass(frozen=True)
class UploadSession:
    session_id: str
    role: str
    suffix: str
    expected_bytes: int
    received_bytes: int
    status: str
    created_at: float
    updated_at: float


class UploadStore:
    def __init__(
        self,
        root: Path,
        *,
        max_source_bytes: int,
        max_image_bytes: int,
        chunk_bytes: int,
        min_free_bytes: int,
        ttl_seconds: int,
    ) -> None:
        self.root = root
        self.max_source_bytes = max_source_bytes
        self.max_image_bytes = max_image_bytes
        self.chunk_bytes = chunk_bytes
        self.min_free_bytes = min_free_bytes
        self.ttl_seconds = ttl_seconds

    def _session_dir(self, session_id: str) -> Path:
        if JOB_ID_PATTERN.fullmatch(session_id) is None:
            raise PublicInputError("Upload session not found.", status_code=404)
        return self.root / session_id

    @staticmethod
    def _metadata_path(session_dir: Path) -> Path:
        return session_dir / "upload.json"

    @staticmethod
    def _token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _public_session(metadata: dict[str, object]) -> UploadSession:
        return UploadSession(
            session_id=str(metadata["session_id"]),
            role=str(metadata["role"]),
            suffix=str(metadata["suffix"]),
            expected_bytes=int(metadata["expected_bytes"]),
            received_bytes=int(metadata["received_bytes"]),
            status=str(metadata["status"]),
            created_at=float(metadata["created_at"]),
            updated_at=float(metadata["updated_at"]),
        )

    def _read_metadata(self, session_dir: Path) -> dict[str, object]:
        try:
            payload = json.loads(self._metadata_path(session_dir).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PublicInputError("Upload session not found.", status_code=404) from exc
        if not isinstance(payload, dict):
            raise PublicInputError("Upload session not found.", status_code=404)
        return payload

    def _write_metadata(self, session_dir: Path, metadata: dict[str, object]) -> None:
        temporary = session_dir / f".upload-{uuid.uuid4().hex}.tmp"
        temporary.write_text(json.dumps(metadata, separators=(",", ":")), encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, self._metadata_path(session_dir))

    def _authorized_metadata(self, session_id: str, token: str) -> tuple[Path, dict[str, object]]:
        session_dir = self._session_dir(session_id)
        metadata = self._read_metadata(session_dir)
        submitted = self._token_digest(token)
        expected = str(metadata.get("token_digest", ""))
        if not token or not hmac.compare_digest(submitted, expected):
            raise PublicInputError("Upload session not found.", status_code=404)
        return session_dir, metadata

    @contextmanager
    def _session_lock(self, session_dir: Path) -> Iterator[None]:
        lock_path = session_dir / ".lock"
        try:
            with lock_path.open("a+", encoding="utf-8") as lock_file:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise PublicInputError(
                        "This upload is already receiving another chunk.", status_code=409
                    ) from exc
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except FileNotFoundError as exc:
            raise PublicInputError("Upload session not found.", status_code=404) from exc

    def create(self, *, role: str, filename: str, expected_bytes: int) -> tuple[UploadSession, str]:
        suffix = Path(filename).suffix.lower()
        if role not in {"reference", "video"}:
            raise PublicInputError("Upload role must be reference or video.")
        allowed = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS if role == "reference" else VIDEO_EXTENSIONS
        if suffix not in allowed:
            raise PublicInputError("Unsupported media file type.")
        if expected_bytes <= 0:
            raise PublicInputError("Uploaded files cannot be empty.")
        limit = self.max_image_bytes if suffix in IMAGE_EXTENSIONS else self.max_source_bytes
        if expected_bytes > limit:
            raise PublicInputError(
                f"This file must be {limit // (1024 * 1024)} MB or smaller.",
                status_code=413,
            )

        self.root.mkdir(parents=True, exist_ok=True)
        available = shutil.disk_usage(self.root).free
        required = expected_bytes * 3 + self.min_free_bytes
        if available < required:
            raise PublicInputError(
                "The server does not currently have enough temporary space for this file.",
                status_code=507,
            )

        session_id = uuid.uuid4().hex
        token = secrets.token_urlsafe(32)
        now = time.time()
        metadata: dict[str, object] = {
            "session_id": session_id,
            "token_digest": self._token_digest(token),
            "role": role,
            "suffix": suffix,
            "expected_bytes": expected_bytes,
            "received_bytes": 0,
            "status": "uploading",
            "created_at": now,
            "updated_at": now,
        }
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(mode=0o700)
        self._write_metadata(session_dir, metadata)
        return self._public_session(metadata), token

    def get(self, session_id: str, token: str) -> UploadSession:
        _session_dir, metadata = self._authorized_metadata(session_id, token)
        return self._public_session(metadata)

    def temporary_chunk_path(self, session_id: str, token: str) -> Path:
        session_dir, _metadata = self._authorized_metadata(session_id, token)
        return session_dir / f".chunk-{uuid.uuid4().hex}"

    def commit_chunk(
        self,
        session_id: str,
        token: str,
        *,
        offset: int,
        chunk_path: Path,
    ) -> UploadSession:
        session_dir, _metadata = self._authorized_metadata(session_id, token)
        chunk_size = chunk_path.stat().st_size
        if chunk_size <= 0:
            raise PublicInputError("Upload chunks cannot be empty.")
        if chunk_size > self.chunk_bytes:
            raise PublicInputError(
                f"Upload chunks must be {self.chunk_bytes // (1024 * 1024)} MB or smaller.",
                status_code=413,
            )

        with self._session_lock(session_dir):
            metadata = self._read_metadata(session_dir)
            if metadata.get("status") != "uploading":
                raise PublicInputError("This upload is already complete.", status_code=409)
            received = int(metadata["received_bytes"])
            expected = int(metadata["expected_bytes"])
            if offset != received:
                raise PublicInputError(
                    f"Upload offset mismatch; resume from byte {received}.", status_code=409
                )
            if received + chunk_size > expected:
                raise PublicInputError("Upload exceeds its declared size.", status_code=413)

            payload_path = session_dir / f"payload{metadata['suffix']}"
            with payload_path.open("ab") as destination, chunk_path.open("rb") as source:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
            metadata["received_bytes"] = received + chunk_size
            metadata["updated_at"] = time.time()
            self._write_metadata(session_dir, metadata)
            return self._public_session(metadata)

    def complete(self, session_id: str, token: str) -> UploadSession:
        session_dir, _metadata = self._authorized_metadata(session_id, token)
        with self._session_lock(session_dir):
            metadata = self._read_metadata(session_dir)
            if int(metadata["received_bytes"]) != int(metadata["expected_bytes"]):
                raise PublicInputError("Upload is incomplete.", status_code=409)
            metadata["status"] = "complete"
            metadata["updated_at"] = time.time()
            self._write_metadata(session_dir, metadata)
            return self._public_session(metadata)

    def consume(self, session_id: str, token: str, *, role: str, destination_dir: Path) -> Path:
        session_dir, _metadata = self._authorized_metadata(session_id, token)
        with self._session_lock(session_dir):
            metadata = self._read_metadata(session_dir)
            if metadata.get("status") != "complete" or metadata.get("role") != role:
                raise PublicInputError("Upload is not ready for processing.", status_code=409)
            source = session_dir / f"payload{metadata['suffix']}"
            if not source.is_file() or source.stat().st_size != int(metadata["expected_bytes"]):
                raise PublicInputError("Upload is incomplete.", status_code=409)
            destination_dir.mkdir(parents=True, exist_ok=True)
            destination = destination_dir / f"{role}{metadata['suffix']}"
            os.replace(source, destination)
        shutil.rmtree(session_dir, ignore_errors=True)
        return destination

    def cancel(self, session_id: str, token: str) -> None:
        session_dir, _metadata = self._authorized_metadata(session_id, token)
        shutil.rmtree(session_dir, ignore_errors=True)

    def cleanup_expired(self, now: float | None = None) -> int:
        if not self.root.exists():
            return 0
        current = time.time() if now is None else now
        removed = 0
        for session_dir in self.root.iterdir():
            if (
                not session_dir.is_dir()
                or session_dir.is_symlink()
                or JOB_ID_PATTERN.fullmatch(session_dir.name) is None
            ):
                continue
            try:
                metadata = self._read_metadata(session_dir)
                updated_at = float(metadata.get("updated_at", session_dir.stat().st_mtime))
            except (PublicInputError, OSError, TypeError, ValueError):
                updated_at = session_dir.stat().st_mtime
            if current - updated_at > self.ttl_seconds:
                shutil.rmtree(session_dir, ignore_errors=True)
                removed += 1
        return removed
