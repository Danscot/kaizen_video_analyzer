"""
kaizen/settings.py
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-insecure-change-this-in-production-please"
)

DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost 127.0.0.1").split()

# ── Apps ──────────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "whitenoise.runserver_nostatic",
    "analyser",
]

# ── Middleware ─────────────────────────────────────────────────────────────────
# IMPORTANT: CommonMiddleware and XFrameOptionsMiddleware are intentionally
# excluded — they wrap the response iterator and break SSE streaming.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "analyser.middleware.RequestLogMiddleware",
]

ROOT_URLCONF = "kaizen.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "kaizen.wsgi.application"

# ── Database ──────────────────────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "ATOMIC_REQUESTS": False,
        "CONN_MAX_AGE": 0,
    }
}

# ── Static & Media ────────────────────────────────────────────────────────────
STATIC_URL  = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL  = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ── File uploads ──────────────────────────────────────────────────────────────
DATA_UPLOAD_MAX_MEMORY_SIZE  = 640 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE  = 640 * 1024 * 1024
FILE_UPLOAD_TEMP_DIR         = BASE_DIR / "media" / "uploads"

# ── Misc ──────────────────────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE     = "UTC"
USE_TZ        = True

# ── Gemini API key ─────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ── Security (production only) ────────────────────────────────────────────────
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER   = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_PROXY_SSL_HEADER     = ("HTTP_X_FORWARDED_PROTO", "https")

# ── Logging ───────────────────────────────────────────────────────────────────
# Two handlers:
#   console  — always on, colour-coded by level (ANSI codes, safe on any terminal)
#   file     — rotating file at logs/kaizen.log, persists across restarts
#
# Three loggers:
#   kaizen   — our application code (streaming, views, startup checks)
#   django   — Django internals (request/response, ORM errors)
#   root     — catch-all for third-party libs

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

_IS_TTY = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    "formatters": {
        "console_colour": {
            "()": "analyser.log_formatter.ColourFormatter",
        },
        "file_plain": {
            "format": "[{asctime}] {levelname:<8} {name} — {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "console_colour",
            "level": "DEBUG",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "kaizen.log"),
            "maxBytes": 10 * 1024 * 1024,   # 10 MB per file
            "backupCount": 5,
            "formatter": "file_plain",
            "encoding": "utf-8",
            "level": "DEBUG",
        },
    },

    "loggers": {
        # Our application — everything DEBUG and above
        "kaizen": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
        # Django internals — INFO and above (avoids SQL noise)
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "file"],
            "level": "WARNING",
            "propagate": False,
        },
    },

    # Root logger — catches everything else (yt-dlp, google-genai, whisper…)
    "root": {
        "handlers": ["console", "file"],
        "level": "WARNING",
    },
}
