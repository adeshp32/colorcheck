from __future__ import annotations

import ipaddress
import json
import logging
import shutil
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from colorcheck.analysis.correction import scale_correction
from colorcheck.analysis.pipeline import analyze_sample_images, analyze_video
from colorcheck.config import AppSettings
from colorcheck.edits import EditPlanError, parse_edit_plan
from colorcheck.exports.video import probe_source_duration, stream_edited_video
from colorcheck.models import CorrectionPlan
from colorcheck.web.jobs import BackgroundJobWorker, JobStore
from colorcheck.web.pages import home_page, job_page, job_progress_page
from colorcheck.web.security import (
    IMAGE_EXTENSIONS,
    FixedWindowRateLimiter,
    MediaLimits,
    PublicInputError,
    cleanup_expired_jobs,
    save_upload_limited,
    upload_destination,
    upload_origin_allowed,
    validate_job_id,
    validate_media,
)
from colorcheck.web.uploads import UploadStore

LOGGER = logging.getLogger(__name__)
SETTINGS = AppSettings.from_environment()
JOBS_ROOT = SETTINGS.storage_root / "jobs"
UPLOADS_ROOT = SETTINGS.storage_root / "uploads"
RENDERS_ROOT = SETTINGS.storage_root / "renders"
MAX_SAMPLE_BYTES = 4 * 1024 * 1024
MAX_REFERENCE_SAMPLES = 12
MAX_TARGET_SAMPLES = 96

MEDIA_LIMITS = MediaLimits(
    max_upload_bytes=SETTINGS.max_upload_bytes,
    max_video_seconds=SETTINGS.max_video_seconds,
    max_video_pixels=SETTINGS.max_video_pixels,
    max_image_pixels=SETTINGS.max_image_pixels,
)
SOURCE_MEDIA_LIMITS = MediaLimits(
    max_upload_bytes=SETTINGS.max_source_upload_bytes,
    max_video_seconds=SETTINGS.max_video_seconds,
    max_video_pixels=SETTINGS.max_video_pixels,
    max_image_pixels=SETTINGS.max_image_pixels,
)
RATE_LIMITER = FixedWindowRateLimiter(limit=SETTINGS.analyses_per_hour, window_seconds=3600)
UPLOAD_RATE_LIMITER = FixedWindowRateLimiter(limit=12, window_seconds=3600)
RENDER_SLOT = threading.BoundedSemaphore(value=1)
JOB_STORE = JobStore(JOBS_ROOT)
UPLOAD_STORE = UploadStore(
    UPLOADS_ROOT,
    max_source_bytes=SETTINGS.max_source_upload_bytes,
    max_image_bytes=SETTINGS.max_upload_bytes,
    chunk_bytes=SETTINGS.upload_chunk_bytes,
    min_free_bytes=SETTINGS.min_free_disk_bytes,
    ttl_seconds=SETTINGS.upload_ttl_hours * 3600,
)

ALLOWED_OUTPUT_FILES = {
    "report.json",
    "report.html",
    "recommended_correction.cube",
    "recommended_correction.cdl",
    "davinci_resolve_steps.md",
    "premiere_pro_steps.md",
    "avid_media_composer_steps.md",
    "imovie_steps.md",
}


class RequestBodyTooLarge(Exception):
    pass


class UploadCreation(BaseModel):
    role: str
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0)


class UploadedFileReference(BaseModel):
    session_id: str = Field(min_length=32, max_length=32)
    token: str = Field(min_length=16, max_length=128)


class UploadedJobCreation(BaseModel):
    reference: UploadedFileReference
    video: UploadedFileReference
    samples: int = Field(default=24, ge=4, le=96)
    strength: int = Field(default=50, ge=0, le=100)
    lighting_threshold: int = Field(default=60, ge=5, le=100)
    rights_confirmed: bool
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    edit_plan: dict[str, Any] = Field(default_factory=dict)


def _client_key(request: Request) -> str:
    proxy_ip = (
        request.headers.get("cf-connecting-ip", "").strip()
        or request.headers.get("x-real-ip", "").strip()
    )
    if proxy_ip:
        try:
            return ipaddress.ip_address(proxy_ip).compressed
        except ValueError:
            pass
    return request.client.host[:64] if request.client else "unknown"


def _secure_response(response: Response, request: Request) -> Response:
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    if request.url.path.startswith(("/jobs/", "/api/")):
        response.headers["Cache-Control"] = "no-store, private"
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    if forwarded_proto == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def _expected_origins(request: Request) -> tuple[str, ...]:
    request_host = request.headers.get("host", "")
    forwarded_host = request.headers.get("x-forwarded-host", "").split(",", 1)[0].strip()
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    return tuple(
        candidate
        for candidate in (
            f"{request.url.scheme}://{request_host}" if request_host else "",
            f"{forwarded_proto or request.url.scheme}://{forwarded_host}" if forwarded_host else "",
        )
        if candidate
    )


def _is_job_creation(request: Request) -> bool:
    return request.method == "POST" and request.url.path in {
        "/analyze",
        "/analyze-form",
        "/api/jobs/samples",
        "/api/jobs/from-uploads",
    }


@asynccontextmanager
async def lifespan(_application: FastAPI):
    _ensure_storage()
    JOB_WORKER.start()
    try:
        yield
    finally:
        JOB_WORKER.stop()


app = FastAPI(
    title="Video Color Consistency Checker",
    version="0.2.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.mount("/assets", StaticFiles(directory=Path(__file__).with_name("assets")), name="assets")


@app.middleware("http")
async def public_safety_boundary(request: Request, call_next) -> Response:
    job_creation = _is_job_creation(request)
    limited_body = job_creation and request.url.path != "/api/jobs/from-uploads"
    if limited_body:
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > SETTINGS.max_request_bytes:
            return _secure_response(
                JSONResponse(
                    status_code=413,
                    content={"detail": f"This request must be under {SETTINGS.max_request_mb} MB."},
                ),
                request,
            )
        original_receive = request._receive
        received_bytes = 0

        async def receive_limited() -> dict[str, object]:
            nonlocal received_bytes
            message = await original_receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > SETTINGS.max_request_bytes:
                    raise RequestBodyTooLarge
            return message

        request._receive = receive_limited

    mutating = request.method in {"POST", "PUT", "PATCH", "DELETE"}
    if mutating and not upload_origin_allowed(
        request.headers.get("origin"),
        _expected_origins(request),
        request.headers.get("sec-fetch-site"),
    ):
        return _secure_response(
            JSONResponse(status_code=403, content={"detail": "Cross-site request blocked."}),
            request,
        )

    if job_creation:
        allowed, retry_after = RATE_LIMITER.allow(_client_key(request))
        if not allowed:
            return _secure_response(
                JSONResponse(
                    status_code=429,
                    content={"detail": "Analysis limit reached. Please try again later."},
                    headers={"Retry-After": str(retry_after)},
                ),
                request,
            )
    if request.method == "POST" and request.url.path == "/api/uploads":
        allowed, retry_after = UPLOAD_RATE_LIMITER.allow(_client_key(request))
        if not allowed:
            return _secure_response(
                JSONResponse(
                    status_code=429,
                    content={"detail": "Upload limit reached. Please try again later."},
                    headers={"Retry-After": str(retry_after)},
                ),
                request,
            )
    try:
        response = await call_next(request)
    except RequestBodyTooLarge:
        response = JSONResponse(
            status_code=413,
            content={"detail": f"This request must be under {SETTINGS.max_request_mb} MB."},
        )
    return _secure_response(response, request)


def _ensure_storage() -> None:
    for directory in (JOBS_ROOT, UPLOADS_ROOT, RENDERS_ROOT):
        directory.mkdir(parents=True, exist_ok=True)
    cleanup_expired_jobs(JOBS_ROOT, ttl_seconds=SETTINGS.job_ttl_hours * 3600)
    cleanup_expired_jobs(RENDERS_ROOT, ttl_seconds=SETTINGS.upload_ttl_hours * 3600)
    UPLOAD_STORE.cleanup_expired()


def _require_rights_confirmation(rights_confirmed: bool) -> None:
    if not rights_confirmed:
        raise PublicInputError("Confirm that you have permission to process the uploaded media.")


def _require_queue_capacity() -> None:
    if JOB_STORE.active_count() >= SETTINGS.max_queued_jobs:
        raise PublicInputError(
            "The analysis queue is full. Please try again after the current jobs finish.",
            status_code=503,
        )


def _safe_analysis_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PublicInputError):
        return HTTPException(status_code=exc.status_code, detail=str(exc))
    if isinstance(exc, (EditPlanError, json.JSONDecodeError)):
        return HTTPException(status_code=400, detail=str(exc))
    LOGGER.exception("Analysis request failed")
    return HTTPException(
        status_code=500,
        detail="The request could not be prepared. Try again with a different media file.",
    )


def _safe_relative(input_dir: Path, relative: object) -> Path:
    candidate = (input_dir / str(relative)).resolve()
    if input_dir.resolve() not in candidate.parents:
        raise ValueError("Invalid internal input path.")
    return candidate


def _process_job(job_id: str) -> None:
    input_dir = JOB_STORE.input_dir(job_id)
    output_dir = JOB_STORE.output_dir(job_id)
    try:
        state = JOB_STORE.update(job_id, status="processing", stage="Preparing samples", progress=12)
        settings = state.get("settings", {})
        if not isinstance(settings, dict):
            raise TypeError("Job settings are invalid.")
        inputs = state.get("inputs", {})
        if not isinstance(inputs, dict):
            raise TypeError("Job inputs are invalid.")

        JOB_STORE.update(job_id, stage="Comparing color and lighting", progress=38)
        if state.get("input_mode") == "client_samples":
            reference_names = inputs.get("reference", [])
            target_items = inputs.get("target", [])
            if not isinstance(reference_names, list) or not isinstance(target_items, list):
                raise ValueError("Sample manifest is invalid.")
            reference_paths = [_safe_relative(input_dir, name) for name in reference_names]
            target_samples = []
            for item in target_items:
                if not isinstance(item, dict):
                    raise TypeError("Target sample manifest is invalid.")
                target_samples.append(
                    (_safe_relative(input_dir, item.get("path")), float(item.get("timestamp", 0)))
                )
            report, written = analyze_sample_images(
                reference_paths,
                target_samples,
                output_dir,
                correction_strength_percent=int(settings.get("strength", 50)),
                lighting_shift_threshold_percent=int(settings.get("lighting_threshold", 60)),
            )
        else:
            reference_path = _safe_relative(input_dir, inputs.get("reference"))
            video_path = _safe_relative(input_dir, inputs.get("video"))
            report, written = analyze_video(
                reference_path,
                video_path,
                output_dir,
                sample_count=int(settings.get("samples", 24)),
                correction_strength_percent=int(settings.get("strength", 50)),
                lighting_shift_threshold_percent=int(settings.get("lighting_threshold", 60)),
                render_video_exports=False,
            )

        JOB_STORE.update(job_id, stage="Writing report and edit recipe", progress=88)
        output_names = sorted(
            path.name for path in written.values() if path.suffix not in {".mp4", ".mov"}
        )
        JOB_STORE.delete_processing_media(job_id)
        JOB_STORE.update(
            job_id,
            status="complete",
            stage="Ready",
            progress=100,
            outputs=output_names,
            summary=report.summary.__dict__,
            error=None,
        )
    except Exception:
        LOGGER.exception("Background analysis failed for job %s", job_id)
        JOB_STORE.delete_processing_media(job_id)
        JOB_STORE.update(
            job_id,
            status="failed",
            stage="Analysis failed",
            progress=100,
            error="Analysis could not be completed. Try different media or fewer samples.",
        )


JOB_WORKER = BackgroundJobWorker(JOB_STORE, _process_job)


def _create_source_job(
    reference: UploadFile,
    video: UploadFile,
    samples: int,
    strength: int,
    lighting_threshold: int,
    *,
    source_metadata: dict[str, object] | None = None,
    edit_plan: dict[str, object] | None = None,
) -> str:
    _ensure_storage()
    _require_queue_capacity()
    job_id = JOB_STORE.new_job_id()
    input_dir = JOB_STORE.input_dir(job_id)
    reference_path = upload_destination(input_dir, reference.filename, "reference")
    video_path = upload_destination(input_dir, video.filename, "video")
    try:
        save_upload_limited(reference.file, reference_path, SETTINGS.max_upload_bytes)
        save_upload_limited(video.file, video_path, SETTINGS.max_upload_bytes)
        validate_media(reference_path, "reference", MEDIA_LIMITS)
        validate_media(video_path, "video", MEDIA_LIMITS)
        JOB_STORE.create(
            job_id,
            reference_path=reference_path,
            video_path=video_path,
            samples=samples,
            strength=strength,
            lighting_threshold=lighting_threshold,
            source_metadata=source_metadata,
            edit_plan=edit_plan,
        )
    except Exception:
        JOB_STORE.remove(job_id)
        raise
    JOB_WORKER.submit(job_id)
    return job_id


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    _ensure_storage()
    return home_page(
        max_upload_mb=SETTINGS.max_upload_mb,
        max_source_upload_mb=SETTINGS.max_source_upload_mb,
        max_request_mb=SETTINGS.max_request_mb,
        max_video_seconds=SETTINGS.max_video_seconds,
        upload_chunk_mb=SETTINGS.upload_chunk_mb,
    )


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/robots.txt", include_in_schema=False)
def robots() -> Response:
    return Response("User-agent: *\nDisallow: /\n", media_type="text/plain")


@app.post("/analyze", status_code=202)
def analyze(
    reference: Annotated[UploadFile, File()],
    video: Annotated[UploadFile, File()],
    samples: Annotated[int, Form()] = 24,
    strength: Annotated[int, Form()] = 50,
    lighting_threshold: Annotated[int, Form()] = 60,
    rights_confirmed: Annotated[bool, Form()] = False,
) -> dict[str, object]:
    try:
        _require_rights_confirmation(rights_confirmed)
        job_id = _create_source_job(reference, video, samples, strength, lighting_threshold)
    except Exception as exc:
        raise _safe_analysis_error(exc) from exc
    return {"job_id": job_id, "status": "queued", "job_url": f"/jobs/{job_id}"}


@app.post("/analyze-form")
def analyze_form(
    reference: Annotated[UploadFile, File()],
    video: Annotated[UploadFile, File()],
    samples: Annotated[int, Form()] = 24,
    strength: Annotated[int, Form()] = 50,
    lighting_threshold: Annotated[int, Form()] = 60,
    rights_confirmed: Annotated[bool, Form()] = False,
) -> RedirectResponse:
    try:
        _require_rights_confirmation(rights_confirmed)
        job_id = _create_source_job(reference, video, samples, strength, lighting_threshold)
    except Exception as exc:
        raise _safe_analysis_error(exc) from exc
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


def _save_sample(upload: UploadFile, directory: Path, stem: str) -> Path:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise PublicInputError("Browser analysis samples must be images.")
    destination = directory / f"{stem}{suffix}"
    save_upload_limited(upload.file, destination, MAX_SAMPLE_BYTES)
    validate_media(destination, "reference", MEDIA_LIMITS)
    return destination


@app.post("/api/jobs/samples", status_code=202)
def create_sample_job(
    reference_samples: Annotated[list[UploadFile], File()],
    target_samples: Annotated[list[UploadFile], File()],
    sample_metadata: Annotated[str, Form()],
    edit_plan: Annotated[str, Form()] = "{}",
    samples: Annotated[int, Form()] = 24,
    strength: Annotated[int, Form()] = 50,
    lighting_threshold: Annotated[int, Form()] = 60,
    rights_confirmed: Annotated[bool, Form()] = False,
) -> dict[str, object]:
    job_id = JOB_STORE.new_job_id()
    try:
        _ensure_storage()
        _require_rights_confirmation(rights_confirmed)
        _require_queue_capacity()
        if not 1 <= len(reference_samples) <= MAX_REFERENCE_SAMPLES:
            raise PublicInputError(f"Use between 1 and {MAX_REFERENCE_SAMPLES} reference samples.")
        if not 4 <= len(target_samples) <= MAX_TARGET_SAMPLES:
            raise PublicInputError(f"Use between 4 and {MAX_TARGET_SAMPLES} target samples.")
        metadata = json.loads(sample_metadata)
        plan_payload = json.loads(edit_plan)
        timestamps = metadata.get("target_timestamps", []) if isinstance(metadata, dict) else []
        if not isinstance(timestamps, list) or len(timestamps) != len(target_samples):
            raise PublicInputError("Sample timestamps do not match the uploaded samples.")

        input_dir = JOB_STORE.input_dir(job_id)
        reference_dir = input_dir / "reference"
        target_dir = input_dir / "target"
        reference_paths = [
            _save_sample(upload, reference_dir, f"{index:03d}")
            for index, upload in enumerate(reference_samples)
        ]
        target_paths = [
            _save_sample(upload, target_dir, f"{index:03d}")
            for index, upload in enumerate(target_samples)
        ]
        input_manifest = {
            "reference": [str(path.relative_to(input_dir)) for path in reference_paths],
            "target": [
                {"path": str(path.relative_to(input_dir)), "timestamp": float(timestamp)}
                for path, timestamp in zip(target_paths, timestamps, strict=True)
            ],
        }
        source_metadata = metadata.get("source", {}) if isinstance(metadata, dict) else {}
        JOB_STORE.create(
            job_id,
            input_mode="client_samples",
            input_manifest=input_manifest,
            source_metadata=source_metadata if isinstance(source_metadata, dict) else {},
            edit_plan=plan_payload if isinstance(plan_payload, dict) else {},
            samples=samples,
            strength=strength,
            lighting_threshold=lighting_threshold,
        )
        JOB_WORKER.submit(job_id)
    except Exception as exc:
        JOB_STORE.remove(job_id)
        raise _safe_analysis_error(exc) from exc
    return {"job_id": job_id, "status": "queued", "job_url": f"/jobs/{job_id}"}


@app.post("/api/uploads", status_code=201)
def create_upload(payload: UploadCreation) -> dict[str, object]:
    try:
        _ensure_storage()
        session, token = UPLOAD_STORE.create(
            role=payload.role,
            filename=payload.filename,
            expected_bytes=payload.size,
        )
    except Exception as exc:
        raise _safe_analysis_error(exc) from exc
    return {
        "session_id": session.session_id,
        "token": token,
        "offset": session.received_bytes,
        "chunk_bytes": SETTINGS.upload_chunk_bytes,
    }


@app.get("/api/uploads/{session_id}")
def upload_status(
    session_id: str,
    x_upload_token: Annotated[str, Header(alias="X-Upload-Token")],
) -> dict[str, object]:
    try:
        session = UPLOAD_STORE.get(session_id, x_upload_token)
    except Exception as exc:
        raise _safe_analysis_error(exc) from exc
    return {"offset": session.received_bytes, "size": session.expected_bytes, "status": session.status}


@app.patch("/api/uploads/{session_id}")
async def upload_chunk(
    session_id: str,
    request: Request,
    x_upload_token: Annotated[str, Header(alias="X-Upload-Token")],
    upload_offset: Annotated[int, Header(alias="Upload-Offset")],
) -> dict[str, object]:
    temporary: Path | None = None
    try:
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > SETTINGS.upload_chunk_bytes:
            raise PublicInputError(
                f"Upload chunks must be {SETTINGS.upload_chunk_mb} MB or smaller.",
                status_code=413,
            )
        temporary = UPLOAD_STORE.temporary_chunk_path(session_id, x_upload_token)
        total = 0
        with temporary.open("wb") as handle:
            async for chunk in request.stream():
                total += len(chunk)
                if total > SETTINGS.upload_chunk_bytes:
                    raise PublicInputError(
                        f"Upload chunks must be {SETTINGS.upload_chunk_mb} MB or smaller.",
                        status_code=413,
                    )
                handle.write(chunk)
        session = UPLOAD_STORE.commit_chunk(
            session_id,
            x_upload_token,
            offset=upload_offset,
            chunk_path=temporary,
        )
    except Exception as exc:
        raise _safe_analysis_error(exc) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"offset": session.received_bytes, "size": session.expected_bytes}


@app.post("/api/uploads/{session_id}/complete")
def complete_upload(
    session_id: str,
    x_upload_token: Annotated[str, Header(alias="X-Upload-Token")],
) -> dict[str, object]:
    try:
        session = UPLOAD_STORE.complete(session_id, x_upload_token)
    except Exception as exc:
        raise _safe_analysis_error(exc) from exc
    return {"session_id": session.session_id, "status": session.status}


@app.delete("/api/uploads/{session_id}", status_code=204)
def cancel_upload(
    session_id: str,
    x_upload_token: Annotated[str, Header(alias="X-Upload-Token")],
) -> Response:
    try:
        UPLOAD_STORE.cancel(session_id, x_upload_token)
    except Exception as exc:
        raise _safe_analysis_error(exc) from exc
    return Response(status_code=204)


@app.post("/api/jobs/from-uploads", status_code=202)
def create_uploaded_job(payload: UploadedJobCreation) -> dict[str, object]:
    job_id = JOB_STORE.new_job_id()
    try:
        _ensure_storage()
        _require_rights_confirmation(payload.rights_confirmed)
        _require_queue_capacity()
        input_dir = JOB_STORE.input_dir(job_id)
        reference_path = UPLOAD_STORE.consume(
            payload.reference.session_id,
            payload.reference.token,
            role="reference",
            destination_dir=input_dir,
        )
        video_path = UPLOAD_STORE.consume(
            payload.video.session_id,
            payload.video.token,
            role="video",
            destination_dir=input_dir,
        )
        validate_media(reference_path, "reference", SOURCE_MEDIA_LIMITS)
        validate_media(video_path, "video", SOURCE_MEDIA_LIMITS)
        JOB_STORE.create(
            job_id,
            reference_path=reference_path,
            video_path=video_path,
            samples=payload.samples,
            strength=payload.strength,
            lighting_threshold=payload.lighting_threshold,
            source_metadata=payload.source_metadata,
            edit_plan=payload.edit_plan,
        )
        JOB_WORKER.submit(job_id)
    except Exception as exc:
        JOB_STORE.remove(job_id)
        raise _safe_analysis_error(exc) from exc
    return {"job_id": job_id, "status": "queued", "job_url": f"/jobs/{job_id}"}


def _public_job_state(state: dict[str, object]) -> dict[str, object]:
    return {
        key: state.get(key)
        for key in ("job_id", "status", "stage", "progress", "error", "summary")
    }


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, object]:
    try:
        state = JOB_STORE.get(job_id)
    except PublicInputError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return _public_job_state(state)


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_summary(job_id: str) -> str:
    try:
        state = JOB_STORE.get(job_id)
    except PublicInputError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if state.get("status") != "complete":
        return job_progress_page(job_id, state)
    report_path = JOB_STORE.output_dir(job_id) / "report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Job report not found.")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return job_page(
        job_id,
        report,
        edit_plan=state.get("edit_plan") if isinstance(state.get("edit_plan"), dict) else {},
        source_metadata=(
            state.get("source_metadata") if isinstance(state.get("source_metadata"), dict) else {}
        ),
        max_source_upload_mb=SETTINGS.max_source_upload_mb,
        upload_chunk_mb=SETTINGS.upload_chunk_mb,
    )


@app.get("/jobs/{job_id}/{filename}")
def get_job_file(job_id: str, filename: str) -> FileResponse:
    try:
        validate_job_id(job_id)
    except PublicInputError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if filename not in ALLOWED_OUTPUT_FILES:
        raise HTTPException(status_code=404, detail="File not found.")
    output_dir = JOB_STORE.output_dir(job_id).resolve()
    path = (output_dir / filename).resolve()
    if path.parent != output_dir or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path, content_disposition_type="inline")


def _remove_render_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


@app.post("/jobs/{job_id}/render/{kind}")
def render_job_video(
    job_id: str,
    kind: str,
    upload_session: Annotated[str, Form()],
    upload_token: Annotated[str, Form()],
    edit_plan: Annotated[str, Form()],
    apply_correction: Annotated[bool, Form()] = False,
    correction_strength: Annotated[int, Form()] = 50,
) -> StreamingResponse:
    render_dir = RENDERS_ROOT / uuid.uuid4().hex
    acquired = False
    try:
        if kind not in {"preview", "master"}:
            raise PublicInputError("Unknown render type.", status_code=404)
        state = JOB_STORE.get(job_id)
        if state.get("status") != "complete":
            raise PublicInputError("The report must finish before rendering.", status_code=409)
        if not RENDER_SLOT.acquire(blocking=False):
            raise PublicInputError(
                "Another export is rendering. Please try again shortly.",
                status_code=503,
            )
        acquired = True
        source = UPLOAD_STORE.consume(
            upload_session,
            upload_token,
            role="video",
            destination_dir=render_dir,
        )
        validate_media(source, "video", SOURCE_MEDIA_LIMITS)
        duration = probe_source_duration(source)
        plan = parse_edit_plan(json.loads(edit_plan), duration)

        report_path = JOB_STORE.output_dir(job_id) / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        correction_data = report.get("correction", {})
        correction = None
        if apply_correction:
            full_correction = CorrectionPlan(**correction_data)
            correction = scale_correction(
                full_correction,
                max(0, min(correction_strength, 100)),
            )
        export = stream_edited_video(
            source,
            render_dir,
            plan,
            correction,
            preview=kind == "preview",
        )

        def release_resources() -> None:
            nonlocal acquired
            _remove_render_dir(render_dir)
            if acquired:
                RENDER_SLOT.release()
                acquired = False

        def managed_chunks():
            try:
                yield from export.chunks
            finally:
                release_resources()

        return StreamingResponse(
            managed_chunks(),
            media_type=export.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{export.filename}"',
                "Cache-Control": "no-store, private",
            },
        )
    except Exception as exc:
        _remove_render_dir(render_dir)
        if acquired:
            RENDER_SLOT.release()
        raise _safe_analysis_error(exc) from exc
