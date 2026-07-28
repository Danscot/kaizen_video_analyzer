"""
analyser/apps.py
The ready() method runs once at Django startup (after all apps are loaded).
It checks every external dependency and prints loud, actionable warnings
for anything that will cause silent failures later.
"""
import logging
import shutil
import sys

from django.apps import AppConfig

logger = logging.getLogger("kaizen.startup")


class AnalyserConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name               = "analyser"
    verbose_name       = "Kaizen Video Analyser"

    def ready(self):
        # Import here to avoid triggering Django setup before it's ready
        from django.conf import settings

        _sep  = "─" * 56
        _warn = []   # list of issues found
        _info = []   # list of OK confirmations

        # ── 1. GEMINI_API_KEY ─────────────────────────────────────────────────
        if not settings.GEMINI_API_KEY:
            _warn.append(
                "GEMINI_API_KEY is not set.\n"
                "  All analysis requests will fail with a 500 error.\n"
                "  Fix: export GEMINI_API_KEY=your_key_here\n"
                "       or add it to your systemd environment."
            )
        else:
            masked = settings.GEMINI_API_KEY[:6] + "..." + settings.GEMINI_API_KEY[-4:]
            _info.append(f"GEMINI_API_KEY  {masked}")

        # ── 2. ffmpeg ─────────────────────────────────────────────────────────
        if shutil.which("ffmpeg") is None:
            _warn.append(
                "ffmpeg is not installed or not on PATH.\n"
                "  Video transcription will fail.\n"
                "  Fix: sudo apt install ffmpeg"
            )
        else:
            _info.append(f"ffmpeg          {shutil.which('ffmpeg')}")

        # ── 3. Whisper ────────────────────────────────────────────────────────
        try:
            import whisper   # noqa: F401
            _info.append("openai-whisper  installed")
        except ImportError:
            _warn.append(
                "openai-whisper is not installed.\n"
                "  Fix: pip install openai-whisper"
            )

        # ── 4. OpenCV ─────────────────────────────────────────────────────────
        try:
            import cv2   # noqa: F401
            _info.append(f"opencv          {cv2.__version__}")
        except ImportError:
            _warn.append(
                "opencv-python-headless is not installed.\n"
                "  Visual analysis will fail.\n"
                "  Fix: pip install opencv-python-headless"
            )

        # ── 5. google-genai ───────────────────────────────────────────────────
        try:
            from google import genai   # noqa: F401
            _info.append("google-genai    installed")
        except ImportError:
            _warn.append(
                "google-genai is not installed.\n"
                "  Fix: pip install google-genai"
            )

        # ── 6. yt-dlp ─────────────────────────────────────────────────────────
        try:
            import yt_dlp   # noqa: F401
            _info.append("yt-dlp          installed")
        except ImportError:
            _warn.append(
                "yt-dlp is not installed.\n"
                "  URL video download will fail.\n"
                "  Fix: pip install yt-dlp"
            )

        # ── 7. ReportLab ─────────────────────────────────────────────────────
        try:
            import reportlab   # noqa: F401
            _info.append("reportlab       installed")
        except ImportError:
            _warn.append(
                "reportlab is not installed.\n"
                "  PDF export will fail.\n"
                "  Fix: pip install reportlab"
            )

        # ── 8. Media directories ──────────────────────────────────────────────
        from pathlib import Path
        upload_dir = Path(settings.MEDIA_ROOT) / "uploads"
        output_dir = Path(settings.MEDIA_ROOT) / "output"
        for d in [upload_dir, output_dir]:
            try:
                d.mkdir(parents=True, exist_ok=True)
                _info.append(f"directory       {d}  OK")
            except OSError as e:
                _warn.append(
                    f"Cannot create directory {d}: {e}\n"
                    "  Check permissions."
                )

        # ── 9. Secret key check ───────────────────────────────────────────────
        if settings.SECRET_KEY == "dev-insecure-change-this-in-production-please":
            if not settings.DEBUG:
                _warn.append(
                    "DJANGO_SECRET_KEY is using the insecure dev default in production.\n"
                    "  Fix: export DJANGO_SECRET_KEY=$(python3 -c \"import secrets; print(secrets.token_hex(48))\")"
                )

        # ── Print startup report ──────────────────────────────────────────────
        logger.info(_sep)
        logger.info("KAIZEN VIDEO ANALYST — startup check")
        logger.info(_sep)

        for item in _info:
            logger.info(f"  OK   {item}")

        if _warn:
            logger.info(_sep)
            for w in _warn:
                for i, line in enumerate(w.split("\n")):
                    if i == 0:
                        logger.warning(f"  WARN {line}")
                    else:
                        logger.warning(f"       {line}")

        logger.info(_sep)

        if _warn:
            logger.warning(
                f"{len(_warn)} configuration issue(s) found. "
                "See warnings above — fix these before running analyses."
            )
        else:
            logger.info("All dependencies OK. Ready to accept requests.")

        logger.info(_sep)
