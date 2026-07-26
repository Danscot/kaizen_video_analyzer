"""
analyser/views.py
All HTTP views: index, SSE analysis streams, URL fetch, export downloads,
and the job history JSON API.

SSE STREAMING NOTE:
Django's StreamingHttpResponse with a sync Gunicorn worker will flush each
yielded chunk immediately as long as:
  1. No buffering middleware wraps the response (see settings.MIDDLEWARE).
  2. The generator yields frequently — we yield a status event before every
     blocking call so the client always gets a heartbeat.
  3. nginx has proxy_buffering off (see nginx.conf).
  4. Gunicorn has --timeout high enough (600s in gunicorn.conf.py).
"""
import json
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


def _check_api_key():
    if not settings.GEMINI_API_KEY:
        return JsonResponse(
            {"error": "GEMINI_API_KEY is not configured on the server."},
            status=500,
        )
    return None


def _streaming_response(generator):
    """
    Wrap a generator in a StreamingHttpResponse with the correct headers
    to prevent any intermediate buffering.
    """
    resp = StreamingHttpResponse(generator, content_type="text/event-stream")
    resp["Cache-Control"]     = "no-cache, no-transform"
    resp["X-Accel-Buffering"] = "no"           # tells nginx not to buffer
    # NOTE: 'Connection' and 'Transfer-Encoding' are hop-by-hop headers.
    # WSGI servers (gunicorn, wsgiref/runserver) manage these themselves —
    # setting them from the application raises AssertionError under wsgiref
    # and is silently stripped/rejected by most WSGI servers. Never set them here.
    return resp


# ── Index ─────────────────────────────────────────────────────────────────────

def index(request):
    return render(request, "analyser/index.html")


# ── Content analysis ──────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def analyse_content(request):
    err = _check_api_key()
    if err:
        return err

    tmp_path_str = request.POST.get("tmp_path", "").strip()
    if tmp_path_str:
        source_path = Path(tmp_path_str)
        source_name = request.POST.get("filename", source_path.name)
    else:
        if "file" not in request.FILES:
            return JsonResponse({"error": "No file provided."}, status=400)
        uploaded    = request.FILES["file"]
        source_name = uploaded.name
        source_path = _save_tmp(uploaded)

    is_audio = source_path.suffix.lower() in SUPPORTED_AUDIO

    os.environ["GEMINI_API_KEY"] = settings.GEMINI_API_KEY

    # Create job record BEFORE starting the stream so the DB write
    # completes while the connection is still open.
    job = AnalysisJob.objects.create(
        source_name   = source_name,
        source_url    = request.POST.get("source_url", ""),
        track         = "content",
        status        = "running",
        whisper_model = request.POST.get("whisper_model", "base"),
        gemini_model  = request.POST.get("gemini_model",  "gemini-2.5-flash"),
    )

    def event_stream():
        # Send job_id immediately so frontend can set up export links early
        yield sse("job_created", {"job_id": str(job.id)})
        yield from stream_content(job, source_path, is_audio)

    return _streaming_response(event_stream())


# ── Visual analysis ───────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def analyse_visual(request):
    err = _check_api_key()
    if err:
        return err

    tmp_path_str = request.POST.get("tmp_path", "").strip()
    if tmp_path_str:
        source_path = Path(tmp_path_str)
        source_name = request.POST.get("filename", source_path.name)
    else:
        if "file" not in request.FILES:
            return JsonResponse({"error": "No file provided."}, status=400)
        uploaded    = request.FILES["file"]
        source_name = uploaded.name
        source_path = _save_tmp(uploaded)

    os.environ["GEMINI_API_KEY"] = settings.GEMINI_API_KEY

    job = AnalysisJob.objects.create(
        source_name = source_name,
        source_url  = request.POST.get("source_url", ""),
        track       = "visual",
        status      = "running",
        gemma_model = request.POST.get("gemma_model", "gemma-4-31b-it"),
    )

    # Stash tuning params as transient attrs — not DB fields
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
    err = _check_api_key()
    if err:
        return err

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        body = {}

    url = (body.get("url") or request.POST.get("url", "")).strip()
    if not url:
        return JsonResponse({"error": "No URL provided."}, status=400)

    def event_stream():
        yield from stream_fetch_url(url)

    return _streaming_response(event_stream())


# ── Export: JSON ──────────────────────────────────────────────────────────────

def download_json(request, job_id):
    job      = get_object_or_404(AnalysisJob, id=job_id)
    data     = job.to_export_dict()
    stem     = Path(job.source_name).stem or "analysis"
    filename = f"{stem}_{job.track}_analysis.json"
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
        return JsonResponse({"error": f"PDF generation failed: {exc}"}, status=500)
    stem     = Path(job.source_name).stem or "analysis"
    filename = f"{stem}_{job.track}_brief.pdf"
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
    """Delete a single analysis job and its DB record."""
    job = get_object_or_404(AnalysisJob, id=job_id)
    job.delete()
    return JsonResponse({"deleted": True, "job_id": str(job_id)})
