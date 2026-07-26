"""
gunicorn.conf.py — production configuration for Kaizen Video Analyst

CRITICAL SSE SETTINGS:
- worker_class = "gthread"   : threaded worker — each request runs in its own
                               thread so long SSE streams don't block other requests.
- threads = 4                : allows up to 4 concurrent streams per worker.
- timeout = 0                : DISABLED — SSE streams have no fixed end time.
                               Gunicorn's timeout kills the worker if a request
                               takes longer than N seconds with no response.
                               For SSE we yield frequently so this isn't needed,
                               but setting it to 0 (infinite) is the safe default.
- keepalive = 65             : must be > nginx keepalive_timeout (default 65s).
"""

bind             = "127.0.0.1:5000"
workers          = 1          # 1 worker — Whisper/OpenCV are CPU-heavy
worker_class     = "gthread"  # threaded: SSE doesn't block other requests
threads          = 4          # up to 4 concurrent streams
timeout          = 0          # no timeout — SSE streams run until complete
graceful_timeout = 30
keepalive        = 65

accesslog        = "/var/log/kaizen/access.log"
errorlog         = "/var/log/kaizen/error.log"
loglevel         = "info"
proc_name        = "kaizen_video_analyst"
daemon           = False
