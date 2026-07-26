"""
analyser/streaming.py
SSE generator pipelines for content and visual analysis.

KEY DESIGN DECISIONS FOR RELIABLE STREAMING:
- Every yield is a complete SSE message (event + data + double newline).
- We close the Django DB connection before long-running AI calls so SQLite
  is not held open across Whisper/Gemini/OpenCV (which can take minutes).
- Every blocking call (Whisper, ffmpeg, OpenCV, Gemini, Gemma) runs through
  _run_blocking(), which drives run_with_heartbeat() on a background thread
  and yields a "heartbeat" SSE event every 2 seconds while it's in flight.
  This guarantees the client sees continuous proof-of-life regardless of
  how long the real work takes, and a hard per-stage ceiling means a truly
  hung network call (e.g. Whisper's first-run model download with no
  internet access) surfaces as a clear error instead of freezing the UI.
- `yield from _run_blocking(...)` forwards heartbeat events to the caller
  AND captures the blocking call's return value via PEP 380 generator
  return semantics — no extra plumbing needed.
"""
import json
import os
import sys
import io
import tempfile
import uuid
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr

from django.conf import settings
from django.db import connection as db_connection

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.transcriber      import transcribe_video, transcribe_audio
from core.analyser         import analyse_transcript
from core.frame_extractor  import extract_changed_frames
from core.visual_analyser  import analyse_frames_visually
from core.design_context   import build_design_context, format_as_markdown

from .heartbeat import run_with_heartbeat

SUPPORTED_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp", ".ts"}
SUPPORTED_AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".wma"}

# Per-stage hard ceiling in seconds. Generous, but not infinite — a real
# network hang (e.g. no internet for Whisper's first-run model download,
# or a stalled Gemini/Gemma request) surfaces as a clear error rather than
# freezing the UI forever.
TRANSCRIBE_MAX_SECONDS = 20 * 60
ANALYSE_MAX_SECONDS    = 5  * 60
EXTRACT_MAX_SECONDS    = 10 * 60
VISION_MAX_SECONDS     = 15 * 60

HEARTBEAT_INTERVAL = 2.0   # seconds between "still working" pings


# ── SSE helpers ───────────────────────────────────────────────────────────────

def sse(event: str, data: dict) -> str:
    """Format one complete SSE message."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _close_db():
    """Close the DB connection before a long blocking call so SQLite isn't
    held open across it. Django reopens the connection automatically on the
    next ORM access."""
    try:
        db_connection.close()
    except Exception:
        pass


def _save_tmp(uploaded_file) -> Path:
    """Save a Django UploadedFile to the uploads temp directory."""
    upload_dir = Path(settings.MEDIA_ROOT) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(uploaded_file.name).suffix.lower()
    tmp = tempfile.NamedTemporaryFile(dir=upload_dir, suffix=suffix, delete=False)
    for chunk in uploaded_file.chunks():
        tmp.write(chunk)
    tmp.close()
    return Path(tmp.name)


def _run_blocking(fn, args, kwargs, step, base_message, max_seconds):
    """
    Generator wrapper around run_with_heartbeat():
      - yields sse("heartbeat", ...) every HEARTBEAT_INTERVAL seconds
      - raises the original exception if the blocking call failed
      - `return`s the blocking call's result (captured by the caller via
        `result = yield from _run_blocking(...)`)
    All stdout/stderr from third-party libraries (Whisper, OpenCV, yt-dlp)
    is suppressed during the call so it doesn't leak into server logs.
    """
    devnull = io.StringIO()
    with redirect_stdout(devnull), redirect_stderr(devnull):
        for kind, payload in run_with_heartbeat(
            fn, args=args, kwargs=kwargs,
            interval=HEARTBEAT_INTERVAL, max_seconds=max_seconds,
        ):
            if kind == "heartbeat":
                yield sse("heartbeat", {
                    "step": step,
                    "elapsed": payload,
                    "message": f"{base_message} ({payload}s elapsed)",
                })
            elif kind == "exception":
                raise payload
            elif kind == "result":
                return payload


# ── Content pipeline ──────────────────────────────────────────────────────────

def stream_content(job, source_path: Path, is_audio: bool):
    """
    Yields SSE strings for the content analysis pipeline:
      transcribe (heartbeat) -> Gemini content analysis (heartbeat) -> complete
    """
    from .models import AnalysisJob
    current_step = "transcribe"

    try:
        # ── Step 1: Transcribe ────────────────────────────────────────────────
        yield sse("status", {
            "step": "transcribe",
            "message": f"Transcribing with Whisper ({job.whisper_model})...",
        })

        _close_db()

        if is_audio:
            transcribe_kwargs = {"whisper_model": job.whisper_model}
            transcribe_fn = transcribe_audio
        else:
            transcribe_kwargs = {"whisper_model": job.whisper_model, "keep_audio": False}
            transcribe_fn = transcribe_video

        transcript = yield from _run_blocking(
            transcribe_fn, (source_path,), transcribe_kwargs,
            step="transcribe",
            base_message="Transcribing (first run may download the Whisper model)",
            max_seconds=TRANSCRIBE_MAX_SECONDS,
        )

        if not transcript:
            raise ValueError("Transcription returned no text. The audio may be silent or unreadable.")

        word_count = len(transcript.split())
        AnalysisJob.objects.filter(pk=job.pk).update(
            transcript=transcript,
            word_count=word_count,
        )

        yield sse("transcript", {"text": transcript, "word_count": word_count})

        # ── Step 2: Gemini content analysis ───────────────────────────────────
        current_step = "analyse"
        yield sse("status", {
            "step": "analyse",
            "message": f"Analysing with Gemini ({job.gemini_model})...",
        })

        _close_db()

        analysis = yield from _run_blocking(
            analyse_transcript,
            (),
            {"transcript": transcript, "video_name": job.source_name, "gemini_model": job.gemini_model},
            step="analyse",
            base_message="Analysing with Gemini",
            max_seconds=ANALYSE_MAX_SECONDS,
        )

        AnalysisJob.objects.filter(pk=job.pk).update(
            analysis_json=json.dumps(analysis, ensure_ascii=False),
            status="complete",
        )

        yield sse("complete", {
            "job_id":     str(job.id),
            "analysis":   analysis,
            "transcript": transcript,
        })

    except Exception as exc:
        try:
            AnalysisJob.objects.filter(pk=job.pk).update(
                status="error", error_message=str(exc),
            )
        except Exception:
            pass
        yield sse("error", {"message": str(exc), "step": current_step})

    finally:
        try:
            source_path.unlink(missing_ok=True)
        except Exception:
            pass


# ── Visual pipeline ───────────────────────────────────────────────────────────

def stream_visual(job, source_path: Path):
    """
    Yields SSE strings for the visual analysis pipeline:
      frame extraction (heartbeat) -> Gemma vision (heartbeat) -> design context -> complete
    """
    from .models import AnalysisJob
    current_step = "extract"

    try:
        threshold  = float(getattr(job, "_threshold",  5.0))
        min_gap    = int(getattr(job,   "_min_gap",    30))
        batch_size = int(getattr(job,   "_batch_size", 8))

        # ── Step 1: Frame extraction ──────────────────────────────────────────
        yield sse("status", {
            "step": "extract",
            "message": f"Extracting key frames (sensitivity={threshold})...",
        })

        _close_db()

        frames = yield from _run_blocking(
            extract_changed_frames,
            (source_path,),
            {"threshold": threshold, "min_frame_gap": min_gap},
            step="extract",
            base_message="Extracting key frames",
            max_seconds=EXTRACT_MAX_SECONDS,
        )

        if not frames:
            raise ValueError("No frames extracted. Try lowering the frame sensitivity.")

        yield sse("frames_extracted", {
            "count":         len(frames),
            "frame_indices": [f[0] for f in frames],
        })

        # ── Step 2: Gemma vision ──────────────────────────────────────────────
        current_step = "vision"
        yield sse("status", {
            "step": "vision",
            "message": f"Sending {len(frames)} frames to Gemma ({job.gemma_model})...",
        })

        _close_db()

        raw_visual = yield from _run_blocking(
            analyse_frames_visually,
            (frames,),
            {"gemini_model": job.gemma_model, "batch_size": batch_size},
            step="vision",
            base_message=f"Analysing {len(frames)} frames with Gemma",
            max_seconds=VISION_MAX_SECONDS,
        )

        total_scenes = sum(len(b["scenes"]) for b in raw_visual["batches"])

        # ── Step 3: Design context (fast, local — no heartbeat needed) ────────
        current_step = "context"
        yield sse("status", {
            "step": "context",
            "message": f"Building design context from {total_scenes} scenes...",
        })

        design_ctx = build_design_context(raw_visual, source_name=Path(job.source_name).stem)
        md_block   = format_as_markdown(design_ctx)

        AnalysisJob.objects.filter(pk=job.pk).update(
            visual_json=json.dumps(raw_visual, ensure_ascii=False),
            design_json=json.dumps(design_ctx, ensure_ascii=False),
            planner_markdown=md_block,
            frames_extracted=len(frames),
            scenes_analysed=total_scenes,
            status="complete",
        )

        yield sse("complete", {
            "job_id":           str(job.id),
            "design_context":   design_ctx,
            "planner_markdown": md_block,
            "frames_extracted": len(frames),
            "scenes_analysed":  total_scenes,
        })

    except Exception as exc:
        try:
            AnalysisJob.objects.filter(pk=job.pk).update(
                status="error", error_message=str(exc),
            )
        except Exception:
            pass
        yield sse("error", {"message": str(exc), "step": current_step})

    finally:
        try:
            source_path.unlink(missing_ok=True)
        except Exception:
            pass


# ── URL download pipeline ─────────────────────────────────────────────────────

def stream_fetch_url(url: str):
    """
    Downloads a video via yt-dlp (heartbeat-wrapped) and yields SSE events.
    The final 'ready' event carries tmp_path + filename for the analysis views.
    """
    try:
        import yt_dlp

        upload_dir = Path(settings.MEDIA_ROOT) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        tmp_stem = str(uuid.uuid4())[:8]
        tmp_path = upload_dir / tmp_stem

        yield sse("status", {"step": "download", "message": "Fetching video from URL..."})

        ydl_opts = {
            "format":       "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl":      str(tmp_path) + ".%(ext)s",
            "quiet":        True,
            "no_warnings":  True,
            "noplaylist":   True,
            "max_filesize": 640 * 1024 * 1024,
            "socket_timeout": 30,
        }

        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info.get("title", tmp_stem)

        title = yield from _run_blocking(
            _download, (), {},
            step="download",
            base_message="Downloading video",
            max_seconds=10 * 60,
        )

        candidates = list(upload_dir.glob(f"{tmp_stem}.*"))
        if not candidates:
            raise ValueError("Download failed: file not found after yt-dlp ran.")

        dl_path  = candidates[0]
        size_mb  = round(dl_path.stat().st_size / 1024 / 1024, 1)
        filename = f"{title}{dl_path.suffix}"

        yield sse("downloaded", {
            "filename": filename,
            "size_mb":  size_mb,
            "message":  f"Downloaded {size_mb} MB",
        })
        yield sse("ready", {"tmp_path": str(dl_path), "filename": filename})

    except Exception as exc:
        yield sse("error", {"message": str(exc)})
