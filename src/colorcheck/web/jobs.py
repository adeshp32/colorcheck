from __future__ import annotations

import json
import os
import queue
import shutil
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from colorcheck.web.security import JOB_ID_PATTERN, PublicInputError

JobProcessor = Callable[[str], None]


class JobStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._lock = threading.RLock()

    def new_job_id(self) -> str:
        return uuid.uuid4().hex

    def job_dir(self, job_id: str) -> Path:
        if JOB_ID_PATTERN.fullmatch(job_id) is None:
            raise PublicInputError("Job not found.", status_code=404)
        return self.root / job_id

    def input_dir(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "inputs"

    def output_dir(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "outputs"

    def _state_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.json"

    def _write(self, job_id: str, state: dict[str, object]) -> None:
        job_dir = self.job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        temporary = job_dir / f".job-{uuid.uuid4().hex}.tmp"
        temporary.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, self._state_path(job_id))

    def create(
        self,
        job_id: str,
        *,
        reference_path: Path | None = None,
        video_path: Path | None = None,
        input_mode: str = "source_media",
        input_manifest: dict[str, object] | None = None,
        source_metadata: dict[str, object] | None = None,
        edit_plan: dict[str, object] | None = None,
        samples: int,
        strength: int,
        lighting_threshold: int,
    ) -> dict[str, object]:
        if input_manifest is None:
            if reference_path is None or video_path is None:
                raise ValueError("Source-media jobs require reference and video paths.")
            input_manifest = {
                "reference": reference_path.name,
                "video": video_path.name,
            }
        now = time.time()
        state: dict[str, object] = {
            "job_id": job_id,
            "status": "queued",
            "stage": "Waiting for the processor",
            "progress": 0,
            "created_at": now,
            "updated_at": now,
            "input_mode": input_mode,
            "inputs": input_manifest,
            "source_metadata": source_metadata or {},
            "edit_plan": edit_plan or {},
            "settings": {
                "samples": max(4, min(samples, 96)),
                "strength": max(0, min(strength, 100)),
                "lighting_threshold": max(5, min(lighting_threshold, 100)),
            },
            "error": None,
            "outputs": [],
        }
        with self._lock:
            self._write(job_id, state)
        return state

    def get(self, job_id: str) -> dict[str, object]:
        with self._lock:
            try:
                state = json.loads(self._state_path(job_id).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise PublicInputError("Job not found.", status_code=404) from exc
        if not isinstance(state, dict):
            raise PublicInputError("Job not found.", status_code=404)
        return state

    def update(self, job_id: str, **changes: object) -> dict[str, object]:
        with self._lock:
            state = self.get(job_id)
            state.update(changes)
            state["updated_at"] = time.time()
            self._write(job_id, state)
            return state

    def recoverable(self) -> list[str]:
        if not self.root.exists():
            return []
        recovered: list[str] = []
        for job_dir in sorted(self.root.iterdir()):
            if not job_dir.is_dir() or JOB_ID_PATTERN.fullmatch(job_dir.name) is None:
                continue
            try:
                state = self.get(job_dir.name)
            except PublicInputError:
                continue
            if state.get("status") in {"queued", "processing"}:
                if not self.input_dir(job_dir.name).exists():
                    self.update(
                        job_dir.name,
                        status="failed",
                        stage="Processing inputs expired after an application restart",
                        error="The temporary inputs are no longer available. Start a new analysis.",
                    )
                    continue
                self.update(
                    job_dir.name,
                    status="queued",
                    stage="Recovered after an application restart",
                    progress=min(int(state.get("progress", 0)), 5),
                )
                recovered.append(job_dir.name)
        return recovered

    def active_count(self) -> int:
        if not self.root.exists():
            return 0
        total = 0
        for job_dir in self.root.iterdir():
            if not job_dir.is_dir() or JOB_ID_PATTERN.fullmatch(job_dir.name) is None:
                continue
            try:
                status = self.get(job_dir.name).get("status")
            except PublicInputError:
                continue
            if status in {"queued", "processing"}:
                total += 1
        return total

    def remove(self, job_id: str) -> None:
        shutil.rmtree(self.job_dir(job_id), ignore_errors=True)

    def delete_processing_media(self, job_id: str) -> None:
        shutil.rmtree(self.input_dir(job_id), ignore_errors=True)
        output_dir = self.output_dir(job_id)
        if not output_dir.exists():
            return
        for path in output_dir.iterdir():
            if path.is_file() and path.suffix.lower() in {".mp4", ".mov", ".m4v", ".mkv", ".webm"}:
                path.unlink(missing_ok=True)


class BackgroundJobWorker:
    def __init__(self, store: JobStore, processor: JobProcessor) -> None:
        self.store = store
        self.processor = processor
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._submitted: set[str] = set()
        self._submitted_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run,
            name="colorcheck-job-worker",
            daemon=True,
        )
        self._thread.start()
        for job_id in self.store.recoverable():
            self.submit(job_id)

    def stop(self) -> None:
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=2)

    def submit(self, job_id: str) -> None:
        with self._submitted_lock:
            if job_id in self._submitted:
                return
            self._submitted.add(job_id)
        self._queue.put(job_id)

    def _run(self) -> None:
        while True:
            job_id = self._queue.get()
            if job_id is None:
                self._queue.task_done()
                return
            try:
                self.processor(job_id)
            finally:
                with self._submitted_lock:
                    self._submitted.discard(job_id)
                self._queue.task_done()
