from __future__ import annotations

import ipaddress
import json
import logging
import os
import shutil
import threading
import uuid
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from video_color_checker.analyzer import analyze_video
from video_color_checker.security import (
    FixedWindowRateLimiter,
    MediaLimits,
    PublicInputError,
    cleanup_expired_jobs,
    save_upload_limited,
    upload_destination,
    validate_job_id,
    validate_media,
)
from video_color_checker.ui import home_page, job_page

LOGGER = logging.getLogger(__name__)
STORAGE_ROOT = Path(os.environ.get("VCC_STORAGE_DIR", "storage")).resolve()
JOBS_ROOT = STORAGE_ROOT / "jobs"
MAX_UPLOAD_MB = max(10, int(os.environ.get("VCC_MAX_UPLOAD_MB", "250")))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_REQUEST_BYTES = (MAX_UPLOAD_MB * 2 + 4) * 1024 * 1024
JOB_TTL_HOURS = max(1, int(os.environ.get("VCC_JOB_TTL_HOURS", "6")))
MEDIA_LIMITS = MediaLimits(
    max_upload_bytes=MAX_UPLOAD_BYTES,
    max_video_seconds=max(10, int(os.environ.get("VCC_MAX_VIDEO_SECONDS", "120"))),
    max_video_pixels=max(
        1_000_000,
        round(float(os.environ.get("VCC_MAX_VIDEO_MEGAPIXELS", "8.3")) * 1_000_000),
    ),
    max_image_pixels=50_000_000,
)
RATE_LIMITER = FixedWindowRateLimiter(
    limit=max(1, int(os.environ.get("VCC_ANALYSES_PER_HOUR", "6"))),
    window_seconds=3600,
)
ANALYSIS_SLOT = threading.BoundedSemaphore(value=1)
ALLOWED_OUTPUT_FILES = {
    "report.json",
    "report.html",
    "recommended_correction.cube",
    "recommended_correction.cdl",
    "davinci_resolve_steps.md",
    "premiere_pro_steps.md",
    "avid_media_composer_steps.md",
    "imovie_steps.md",
    "corrected_preview.mp4",
    "corrected_master.mov",
}

app = FastAPI(
    title="Video Color Consistency Checker",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


class RequestBodyTooLarge(Exception):
    pass


def _client_key(request: Request) -> str:
    railway_ip = request.headers.get("x-real-ip", "").strip()
    if railway_ip:
        try:
            return ipaddress.ip_address(railway_ip).compressed
        except ValueError:
            pass
    return request.client.host[:64] if request.client else "unknown"


def _secure_response(response: Response, request: Request) -> Response:
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self'; img-src 'self' data:; media-src 'self' blob:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if request.url.path.startswith("/jobs/"):
        response.headers["Cache-Control"] = "no-store, private"
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    if forwarded_proto == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def public_safety_boundary(request: Request, call_next) -> Response:
    analysis_request = request.method == "POST" and request.url.path in {
        "/analyze",
        "/analyze-form",
    }
    acquired = False
    if analysis_request:
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > MAX_REQUEST_BYTES:
            return _secure_response(
                JSONResponse(
                    status_code=413,
                    content={"detail": f"Combined uploads must be under {MAX_UPLOAD_MB * 2} MB."},
                ),
                request,
            )
        original_receive = request._receive
        received_bytes = 0
        body_too_large = False

        async def receive_limited() -> dict[str, object]:
            nonlocal body_too_large, received_bytes
            message = await original_receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > MAX_REQUEST_BYTES:
                    body_too_large = True
                    raise RequestBodyTooLarge
            return message

        request._receive = receive_limited
        origin = request.headers.get("origin")
        request_host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
        if origin and urlsplit(origin).netloc.lower() != request_host.lower():
            return _secure_response(
                JSONResponse(status_code=403, content={"detail": "Cross-site upload blocked."}),
                request,
            )
        allowed, retry_after = RATE_LIMITER.allow(_client_key(request))
        if not allowed:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Upload limit reached. Please try again later."},
                headers={"Retry-After": str(retry_after)},
            )
            return _secure_response(response, request)
        acquired = ANALYSIS_SLOT.acquire(blocking=False)
        if not acquired:
            response = JSONResponse(
                status_code=503,
                content={"detail": "ColorCheck is processing another video. Please try again shortly."},
                headers={"Retry-After": "30"},
            )
            return _secure_response(response, request)
    try:
        response = await call_next(request)
        if analysis_request and body_too_large:
            response = JSONResponse(
                status_code=413,
                content={"detail": f"Combined uploads must be under {MAX_UPLOAD_MB * 2} MB."},
            )
    except RequestBodyTooLarge:
        response = JSONResponse(
            status_code=413,
            content={"detail": f"Combined uploads must be under {MAX_UPLOAD_MB * 2} MB."},
        )
    finally:
        if acquired:
            ANALYSIS_SLOT.release()
    return _secure_response(response, request)


def _ensure_storage() -> None:
    JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    cleanup_expired_jobs(JOBS_ROOT, ttl_seconds=JOB_TTL_HOURS * 3600)


def _save_upload(upload: UploadFile, destination: Path) -> None:
    save_upload_limited(upload.file, destination, MEDIA_LIMITS.max_upload_bytes)


def _run_analysis(
    reference: UploadFile,
    video: UploadFile,
    samples: int,
    strength: int,
    lighting_threshold: int,
) -> dict[str, object]:
    _ensure_storage()
    job_id = uuid.uuid4().hex
    job_dir = JOBS_ROOT / job_id
    input_dir = job_dir / "inputs"
    out_dir = job_dir / "outputs"
    reference_path = upload_destination(input_dir, reference.filename, "reference")
    video_path = upload_destination(input_dir, video.filename, "video")

    try:
        _save_upload(reference, reference_path)
        _save_upload(video, video_path)
        validate_media(reference_path, "reference", MEDIA_LIMITS)
        validate_media(video_path, "video", MEDIA_LIMITS)
        report, written = analyze_video(
            reference_path=reference_path,
            video_path=video_path,
            out_dir=out_dir,
            sample_count=max(4, min(samples, 96)),
            correction_strength_percent=strength,
            lighting_shift_threshold_percent=lighting_threshold,
        )
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(input_dir, ignore_errors=True)
    return {
        "job_id": job_id,
        "summary": report.summary.__dict__,
        "export_settings": report.export_settings.__dict__,
        "lighting_shift": report.lighting_shift.__dict__,
        "report_url": f"/jobs/{job_id}/report.html",
        "outputs": {
            key: f"/jobs/{job_id}/{path.name}"
            for key, path in written.items()
        },
    }


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    _ensure_storage()
    return home_page()


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


def _require_rights_confirmation(rights_confirmed: bool) -> None:
    if not rights_confirmed:
        raise PublicInputError("Confirm that you have permission to process the uploaded media.")


def _safe_analysis_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PublicInputError):
        return HTTPException(status_code=exc.status_code, detail=str(exc))
    LOGGER.exception("Analysis failed")
    return HTTPException(
        status_code=500,
        detail="Analysis could not be completed. Try a shorter clip or a different media file.",
    )


@app.post("/analyze")
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
        return _run_analysis(reference, video, samples, strength, lighting_threshold)
    except Exception as exc:
        raise _safe_analysis_error(exc) from exc


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
        result = _run_analysis(reference, video, samples, strength, lighting_threshold)
    except Exception as exc:
        raise _safe_analysis_error(exc) from exc
    return RedirectResponse(url=f"/jobs/{result['job_id']}", status_code=303)


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_summary(job_id: str) -> str:
    try:
        validate_job_id(job_id)
    except PublicInputError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    report_path = JOBS_ROOT / job_id / "outputs" / "report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Job not found.")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    return job_page(job_id, report)


@app.get("/jobs/{job_id}/{filename}")
def get_job_file(job_id: str, filename: str) -> FileResponse:
    try:
        validate_job_id(job_id)
    except PublicInputError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if filename not in ALLOWED_OUTPUT_FILES:
        raise HTTPException(status_code=404, detail="File not found.")
    output_dir = (JOBS_ROOT / job_id / "outputs").resolve()
    path = (output_dir / filename).resolve()
    if path.parent != output_dir:
        raise HTTPException(status_code=404, detail="File not found.")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path, content_disposition_type="inline")
