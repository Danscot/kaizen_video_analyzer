"""
analyser/views.py
All HTTP views: index, SSE streams, exports, job history API.
"""
import json
import logging
import os
from pathlib import Path

from django.conf import settings
from django.http import (
    StreamingHttpResponse, JsonResponse,
    HttpResponse, Http404,
)
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import AnalysisJob
from .streaming import (
    stream_content, stream_visual, stream_fetch_url,
    _save_tmp, SUPPORTED_AUDIO, sse,
)

logger = logging.getLogger("kaizen.views")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _streaming_response(generator):
    """
    Wrap a generator in a StreamingHttpResponse.
    NOTE: 'Connection' and 'Transfer-Encoding' are hop-by-hop headers —
    the WSGI server manages them. Setting them here raises AssertionError
    under wsgiref (manage.py runserver). Never set them in app code.
    """
    resp = StreamingHttpResponse(generator, content_type="text/event-stream")
    resp["Cache-Control"]     = "no-cache, no-transform"
    resp["X-Accel-Buffering"] = "no"
    return resp


def _sse_error_stream(message: str, code: str = "config_error"):
    """
    Return a StreamingHttpResponse that immediately yields a single SSE
    error event. Use this instead of JsonResponse inside streaming endpoints
    so the frontend SSE parser actually receives and displays the error —
    JsonResponse bodies are silently ignored by the SSE client.
    """
    logger.error(f"Pre-stream error [{code}]: {message}")
    def _gen():
        yield sse("error", {"message": message, "code": code, "step": "init"})
    return _streaming_response(_gen())


def _api_key_missing_response():
    """
    Returns the appropriate error response for a missing GEMINI_API_KEY.
    For streaming endpoints this MUST be an SSE stream, not a JsonResponse.
    """
    msg = (
        "GEMINI_API_KEY is not configured on the server. "
        "Set the environment variable and restart the server."
    )
    return _sse_error_stream(msg, code="missing_api_key")


# ── Index ─────────────────────────────────────────────────────────────────────

def index(request):
    # Pass config state to template so the UI can show a persistent banner
    # if the API key is missing — visible immediately on page load, not only
    # after a user tries to run an analysis.
    ctx = {
        "api_key_missing": not bool(settings.GEMINI_API_KEY),
        "ffmpeg_missing":  not _check_ffmpeg(),
    }
    logger.debug(f"index loaded — config_ok={not ctx['api_key_missing']}")
    return render(request, "analyser/index.html", ctx)


def _check_ffmpeg() -> bool:
    import shutil
    return shutil.which("ffmpeg") is not None


# ── Content analysis ──────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def analyse_content(request):
    if not settings.GEMINI_API_KEY:
        return _api_key_missing_response()

    tmp_path_str = request.POST.get("tmp_path", "").strip()
    if tmp_path_str:
        source_path = Path(tmp_path_str)
        source_name = request.POST.get("filename", source_path.name)
    else:
        if "file" not in request.FILES:
            return _sse_error_stream("No file provided.", code="no_file")
        uploaded    = request.FILES["file"]
        source_name = uploaded.name
        source_path = _save_tmp(uploaded)

    is_audio = source_path.suffix.lower() in SUPPORTED_AUDIO

    os.environ["GEMINI_API_KEY"] = settings.GEMINI_API_KEY

    logger.info(
        f"Content request — file={source_name!r} is_audio={is_audio} "
        f"whisper={request.POST.get('whisper_model','base')} "
        f"gemini={request.POST.get('gemini_model','gemini-2.5-flash')}"
    )

    job = AnalysisJob.objects.create(
        source_name   = source_name,
        source_url    = request.POST.get("source_url", ""),
        track         = "content",
        status        = "running",
        whisper_model = request.POST.get("whisper_model", "base"),
        gemini_model  = request.POST.get("gemini_model",  "gemini-2.5-flash"),
    )

    def event_stream():
        yield sse("job_created", {"job_id": str(job.id)})
        yield from stream_content(job, source_path, is_audio)

    return _streaming_response(event_stream())


# ── Visual analysis ───────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def analyse_visual(request):
    if not settings.GEMINI_API_KEY:
        return _api_key_missing_response()

    tmp_path_str = request.POST.get("tmp_path", "").strip()
    if tmp_path_str:
        source_path = Path(tmp_path_str)
        source_name = request.POST.get("filename", source_path.name)
    else:
        if "file" not in request.FILES:
            return _sse_error_stream("No file provided.", code="no_file")
        uploaded    = request.FILES["file"]
        source_name = uploaded.name
        source_path = _save_tmp(uploaded)

    os.environ["GEMINI_API_KEY"] = settings.GEMINI_API_KEY

    logger.info(
        f"Visual request — file={source_name!r} "
        f"gemma={request.POST.get('gemma_model','gemma-4-31b-it')}"
    )

    job = AnalysisJob.objects.create(
        source_name = source_name,
        source_url  = request.POST.get("source_url", ""),
        track       = "visual",
        status      = "running",
        gemma_model = request.POST.get("gemma_model", "gemma-4-31b-it"),
    )

    job._threshold  = float(request.POST.get("threshold",  "5.0"))
    job._min_gap    = int(request.POST.get("min_gap",      "30"))
    job._batch_size = int(request.POST.get("batch_size",   "8"))

    def event_stream():
        yield sse("job_created", {"job_id": str(job.id)})
        yield from stream_visual(job, source_path)

    return _streaming_response(event_stream())


# ── URL fetch ─────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def fetch_url(request):
    if not settings.GEMINI_API_KEY:
        return _api_key_missing_response()

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        body = {}

    url = (body.get("url") or request.POST.get("url", "")).strip()
    if not url:
        return _sse_error_stream("No URL provided.", code="no_url")

    logger.info(f"URL fetch request — {url!r}")

    def event_stream():
        yield from stream_fetch_url(url)

    return _streaming_response(event_stream())


# ── Export: JSON ──────────────────────────────────────────────────────────────

def download_json(request, job_id):
    job      = get_object_or_404(AnalysisJob, id=job_id)
    data     = job.to_export_dict()
    stem     = Path(job.source_name).stem or "analysis"
    filename = f"{stem}_{job.track}_analysis.json"
    logger.info(f"JSON export — job={job.short_id} file={filename!r}")
    response = HttpResponse(
        json.dumps(data, indent=2, ensure_ascii=False),
        content_type="application/json",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# ── Export: PDF ───────────────────────────────────────────────────────────────

def download_pdf(request, job_id):
    job  = get_object_or_404(AnalysisJob, id=job_id)
    data = job.to_export_dict()
    try:
        from core.pdf_exporter import export_pdf
        pdf_bytes = export_pdf(data, track=job.track)
    except Exception as exc:
        logger.error(f"PDF export failed — job={job.short_id}: {exc}", exc_info=True)
        return JsonResponse({"error": f"PDF generation failed: {exc}"}, status=500)
    stem     = Path(job.source_name).stem or "analysis"
    filename = f"{stem}_{job.track}_brief.pdf"
    logger.info(f"PDF export — job={job.short_id} file={filename!r}")
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# ── Job history API ───────────────────────────────────────────────────────────

def job_list(request):
    jobs = AnalysisJob.objects.all()[:50]
    return JsonResponse({
        "jobs": [
            {
                "id":          str(j.id),
                "short_id":    j.short_id,
                "source_name": j.source_name,
                "track":       j.track,
                "status":      j.status,
                "created_at":  j.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "word_count":  j.word_count,
                "frames":      j.frames_extracted,
                "scenes":      j.scenes_analysed,
                "error":       j.error_message,
            }
            for j in jobs
        ]
    })


def job_detail(request, job_id):
    job  = get_object_or_404(AnalysisJob, id=job_id)
    data = job.to_export_dict()
    data["status"]     = job.status
    data["error"]      = job.error_message
    data["frames"]     = job.frames_extracted
    data["scenes"]     = job.scenes_analysed
    data["word_count"] = job.word_count
    return JsonResponse(data)


@csrf_exempt
@require_http_methods(["POST", "DELETE"])
def job_delete(request, job_id):
    job = get_object_or_404(AnalysisJob, id=job_id)
    logger.info(f"Delete job {job.short_id} ({job.source_name!r})")
    job.delete()
    return JsonResponse({"deleted": True, "job_id": str(job_id)})
