"""
kaizen/settings.py
"""
import os
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
# excluded — they wrap the response iterator and break SSE streaming by
# buffering chunks before flushing them to the client.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
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
# ATOMIC_REQUESTS=False and CONN_MAX_AGE=0 are critical for SSE:
# ATOMIC_REQUESTS wraps every request in a transaction that holds the DB
# connection open for the full stream duration, which deadlocks on SQLite.
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
