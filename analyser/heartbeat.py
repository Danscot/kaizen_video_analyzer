"""
analyser/heartbeat.py

Runs a blocking function in a background thread and yields periodic
"still alive" SSE-ready events while it runs. This solves the "looks
stuck with no feedback" problem for any long call (Whisper transcription,
OpenCV frame extraction, Gemini/Gemma API calls) regardless of how long
they legitimately take — the UI always gets an update at least every
`interval` seconds.

It also enforces a hard ceiling (`max_seconds`) so a genuinely hung call
(e.g. a network black hole with no timeout) is surfaced as an error
instead of blocking the request thread forever.
"""
import threading
import time


class HeartbeatTimeout(Exception):
    """Raised when a blocking call exceeds max_seconds without finishing."""
    pass


def run_with_heartbeat(fn, args=(), kwargs=None, interval=2.0, max_seconds=1200):
    """
    Generator. Runs fn(*args, **kwargs) on a background daemon thread.

    Yields ("heartbeat", elapsed_seconds) every `interval` seconds while
    the thread is alive.

    On completion yields exactly one of:
      ("result", return_value)
      ("exception", exception_instance)

    If the thread is still alive after `max_seconds`, yields
      ("exception", HeartbeatTimeout(...))
    and returns — the thread itself is a daemon so it will not block
    process shutdown, but note the underlying call (e.g. a stuck network
    request) may continue consuming resources until the process exits.
    """
    kwargs = kwargs or {}
    box = {}

    def target():
        try:
            box["value"] = fn(*args, **kwargs)
        except Exception as exc:                      # noqa: BLE001
            box["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    start = time.monotonic()
    thread.start()

    while thread.is_alive():
        elapsed = time.monotonic() - start
        if elapsed > max_seconds:
            yield ("exception", HeartbeatTimeout(
                f"Operation exceeded the {max_seconds}s limit and was abandoned. "
                f"This usually means a network call (model download or API request) "
                f"is hanging — check server connectivity."
            ))
            return
        thread.join(timeout=interval)
        if thread.is_alive():
            yield ("heartbeat", round(time.monotonic() - start, 1))

    if "error" in box:
        yield ("exception", box["error"])
    else:
        yield ("result", box.get("value"))
