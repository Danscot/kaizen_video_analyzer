"""
analyser/middleware.py
Lightweight request/response logger — logs every request with method,
path, status code, and response time. Errors (4xx, 5xx) are logged at
WARNING/ERROR so they're always visible in the terminal.
"""
import logging
import time

logger = logging.getLogger("kaizen.request")


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        t0       = time.monotonic()
        response = self.get_response(request)
        elapsed  = round((time.monotonic() - t0) * 1000)  # ms

        status  = response.status_code
        method  = request.method
        path    = request.get_full_path()
        content = getattr(response, "content_type", "")

        # Don't spam logs for SSE streams — they're long-lived by design
        is_sse = "text/event-stream" in content

        msg = f"{method} {path} {status} ({elapsed}ms)"

        if status >= 500:
            logger.error(msg)
        elif status >= 400:
            logger.warning(msg)
        elif not is_sse:
            logger.debug(msg)
        # SSE streams: only log the initial open at DEBUG
        else:
            logger.debug(f"{msg} [SSE stream opened]")

        return response
