"""
analyser/streaming.py
SSE generator pipelines with full logging at every stage.

Every stage logs to the `kaizen.streaming` logger which writes to both
the terminal (colour-coded) and logs/kaizen.log. Errors always log the
full traceback so you never have to guess what failed.
"""
import json
import logging
import os
import sys
import io
import tempfile
import traceback
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

logger = logging.getLogger("kaizen.streaming")

SUPPORTED_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp", ".ts"}
SUPPORTED_AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".wma"}

TRANSCRIBE_MAX_SECONDS = 20 * 60
ANALYSE_MAX_SECONDS    = 5  * 60
EXTRACT_MAX_SECONDS    = 10 * 60
VISION_MAX_SECONDS     = 15 * 60
HEARTBEAT_INTERVAL     = 2.0


# ── SSE helpers ───────────────────────────────────────────────────────────────

def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _close_db():
    try:
        db_connection.close()
    except Exception:
        pass


def _save_tmp(uploaded_file) -> Path:
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
    Runs a blocking call on a background thread. Yields SSE heartbeat
    events every HEARTBEAT_INTERVAL seconds and logs them to the terminal
    so the operator can see the pipeline is alive without opening a browser.
    """
    devnull = io.StringIO()
    with redirect_stdout(devnull), redirect_stderr(devnull):
        for kind, payload in run_with_heartbeat(
            fn, args=args, kwargs=kwargs,
            interval=HEARTBEAT_INTERVAL, max_seconds=max_seconds,
        ):
            if kind == "heartbeat":
                logger.debug(f"[{step}] still running — {payload}s elapsed")
                yield sse("heartbeat", {
                    "step":    step,
                    "elapsed": payload,
                    "message": f"{base_message} ({payload}s elapsed)",
                })
            elif kind == "exception":
                raise payload
            elif kind == "result":
                return payload


def _log_error(job_id: str, step: str, exc: Exception) -> None:
    """
    Log a pipeline error with full traceback to both the terminal and the
    log file. This is the single place that ensures no error is ever silent.
    """
    tb = traceback.format_exc()
    logger.error(
        f"Job {str(job_id)[:8]} FAILED at step '{step}': {exc}\n{tb}"
    )


# ── Content pipeline ──────────────────────────────────────────────────────────

def stream_content(job, source_path: Path, is_audio: bool):
    from .models import AnalysisJob
    current_step = "transcribe"

    logger.info(
        f"Job {job.short_id} START content — "
        f"file={source_path.name!r} audio={is_audio} "
        f"whisper={job.whisper_model} gemini={job.gemini_model}"
    )

    try:
        # ── Step 1: Transcribe ────────────────────────────────────────────────
        logger.info(f"Job {job.short_id} [transcribe] starting Whisper ({job.whisper_model})")
        yield sse("status", {
            "step":    "transcribe",
            "message": f"Transcribing with Whisper ({job.whisper_model})...",
        })

        _close_db()

        if is_audio:
            transcribe_fn     = transcribe_audio
            transcribe_kwargs = {"whisper_model": job.whisper_model}
        else:
            transcribe_fn     = transcribe_video
            transcribe_kwargs = {"whisper_model": job.whisper_model, "keep_audio": False}

        transcript = yield from _run_blocking(
            transcribe_fn, (source_path,), transcribe_kwargs,
            step="transcribe",
            base_message="Transcribing (first run downloads the Whisper model — may take a minute)",
            max_seconds=TRANSCRIBE_MAX_SECONDS,
        )

        if not transcript:
            raise ValueError(
                "Transcription returned empty text. "
                "The audio may be silent, corrupted, or in an unsupported format."
            )

        word_count = len(transcript.split())
        logger.info(f"Job {job.short_id} [transcribe] done — {word_count} words")

        AnalysisJob.objects.filter(pk=job.pk).update(
            transcript=transcript,
            word_count=word_count,
        )
        yield sse("transcript", {"text": transcript, "word_count": word_count})

        # ── Step 2: Gemini analysis ───────────────────────────────────────────
        current_step = "analyse"
        logger.info(f"Job {job.short_id} [analyse] sending to Gemini ({job.gemini_model})")
        yield sse("status", {
            "step":    "analyse",
            "message": f"Analysing with Gemini ({job.gemini_model})...",
        })

        _close_db()

        analysis = yield from _run_blocking(
            analyse_transcript, (),
            {"transcript": transcript, "video_name": job.source_name,
             "gemini_model": job.gemini_model},
            step="analyse",
            base_message="Analysing with Gemini",
            max_seconds=ANALYSE_MAX_SECONDS,
        )

        logger.info(
            f"Job {job.short_id} [analyse] done — "
            f"title={analysis.get('title','?')!r} "
            f"hooks={len(analysis.get('hooks',[]))} "
            f"scenes={len(analysis.get('scenes',[]))}"
        )

        AnalysisJob.objects.filter(pk=job.pk).update(
            analysis_json=json.dumps(analysis, ensure_ascii=False),
            status="complete",
        )

        logger.info(f"Job {job.short_id} COMPLETE content")
        yield sse("complete", {
            "job_id":     str(job.id),
            "analysis":   analysis,
            "transcript": transcript,
        })

    except Exception as exc:
        _log_error(job.id, current_step, exc)
        try:
            AnalysisJob.objects.filter(pk=job.pk).update(
                status="error",
                error_message=str(exc),
            )
        except Exception as db_exc:
            logger.error(f"Job {job.short_id} could not save error to DB: {db_exc}")
        yield sse("error", {
            "message": str(exc),
            "step":    current_step,
        })

    finally:
        try:
            source_path.unlink(missing_ok=True)
        except Exception:
            pass


# ── Visual pipeline ───────────────────────────────────────────────────────────

def stream_visual(job, source_path: Path):
    from .models import AnalysisJob
    current_step = "extract"

    threshold  = float(getattr(job, "_threshold",  5.0))
    min_gap    = int(getattr(job,   "_min_gap",    30))
    batch_size = int(getattr(job,   "_batch_size", 8))

    logger.info(
        f"Job {job.short_id} START visual — "
        f"file={source_path.name!r} gemma={job.gemma_model} "
        f"threshold={threshold} min_gap={min_gap} batch={batch_size}"
    )

    try:
        # ── Step 1: Frame extraction ──────────────────────────────────────────
        logger.info(f"Job {job.short_id} [extract] starting OpenCV frame extraction")
        yield sse("status", {
            "step":    "extract",
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
            raise ValueError(
                "No frames were extracted from this video. "
                "Try lowering the frame sensitivity slider, or check that "
                "the file is a valid video with visual content."
            )

        logger.info(f"Job {job.short_id} [extract] done — {len(frames)} frames extracted")
        yield sse("frames_extracted", {
            "count":         len(frames),
            "frame_indices": [f[0] for f in frames],
        })

        # ── Step 2: Gemma vision ──────────────────────────────────────────────
        current_step = "vision"
        logger.info(
            f"Job {job.short_id} [vision] sending {len(frames)} frames "
            f"to Gemma ({job.gemma_model}) in batches of {batch_size}"
        )
        yield sse("status", {
            "step":    "vision",
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
        failed_batches = sum(1 for b in raw_visual["batches"] if b.get("error"))
        logger.info(
            f"Job {job.short_id} [vision] done — "
            f"{total_scenes} scenes analysed, {failed_batches} batch error(s)"
        )
        if failed_batches:
            logger.warning(
                f"Job {job.short_id} [vision] {failed_batches} batch(es) failed — "
                "partial results will still be saved."
            )

        # ── Step 3: Design context ────────────────────────────────────────────
        current_step = "context"
        logger.info(f"Job {job.short_id} [context] building design context")
        yield sse("status", {
            "step":    "context",
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

        logger.info(f"Job {job.short_id} COMPLETE visual")
        yield sse("complete", {
            "job_id":           str(job.id),
            "design_context":   design_ctx,
            "planner_markdown": md_block,
            "frames_extracted": len(frames),
            "scenes_analysed":  total_scenes,
        })

    except Exception as exc:
        _log_error(job.id, current_step, exc)
        try:
            AnalysisJob.objects.filter(pk=job.pk).update(
                status="error",
                error_message=str(exc),
            )
        except Exception as db_exc:
            logger.error(f"Job {job.short_id} could not save error to DB: {db_exc}")
        yield sse("error", {
            "message": str(exc),
            "step":    current_step,
        })

    finally:
        try:
            source_path.unlink(missing_ok=True)
        except Exception:
            pass


# ── URL download pipeline ─────────────────────────────────────────────────────

def stream_fetch_url(url: str):
    logger.info(f"URL download START — {url!r}")
    try:
        import yt_dlp

        upload_dir = Path(settings.MEDIA_ROOT) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        tmp_stem = str(uuid.uuid4())[:8]
        tmp_path = upload_dir / tmp_stem

        yield sse("status", {"step": "download", "message": "Fetching video from URL..."})

        ydl_opts = {
            "format":         "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl":        str(tmp_path) + ".%(ext)s",
            "quiet":          True,
            "no_warnings":    True,
            "noplaylist":     True,
            "max_filesize":   640 * 1024 * 1024,
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

        logger.info(f"URL download DONE — {filename!r} ({size_mb} MB)")
        yield sse("downloaded", {
            "filename": filename,
            "size_mb":  size_mb,
            "message":  f"Downloaded {size_mb} MB",
        })
        yield sse("ready", {"tmp_path": str(dl_path), "filename": filename})

    except Exception as exc:
        tb = traceback.format_exc()
        logger.error(f"URL download FAILED — {url!r}: {exc}\n{tb}")
        yield sse("error", {"message": str(exc), "step": "download"})
