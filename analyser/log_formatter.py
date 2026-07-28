"""
analyser/log_formatter.py
Colour-coded console log formatter.

Levels map to ANSI colours:
  DEBUG    dim white
  INFO     bright white
  WARNING  yellow
  ERROR    red
  CRITICAL bold red + background

Falls back to plain text if the terminal doesn't support ANSI.
"""
import logging
import sys

_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"

_LEVEL_COLOURS = {
    "DEBUG":    "\033[2;37m",    # dim white
    "INFO":     "\033[97m",      # bright white
    "WARNING":  "\033[93m",      # yellow
    "ERROR":    "\033[91m",      # red
    "CRITICAL": "\033[1;41;97m", # bold white on red bg
}

_PREFIX_COLOURS = {
    "DEBUG":    "\033[2;37m",
    "INFO":     "\033[96m",      # cyan for the tag
    "WARNING":  "\033[93m",
    "ERROR":    "\033[91m",
    "CRITICAL": "\033[1;91m",
}


class ColourFormatter(logging.Formatter):
    """
    Produces lines like:
      [HH:MM:SS] INFO     kaizen.streaming — Transcription complete (12s, 432 words)
    with colour when writing to a real terminal, plain when piped/redirected.
    """
    _use_colour = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()

    def format(self, record: logging.LogRecord) -> str:
        ts     = self.formatTime(record, datefmt="%H:%M:%S")
        level  = record.levelname
        name   = record.name
        msg    = record.getMessage()

        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
        else:
            exc_text = None

        if self._use_colour:
            lc = _LEVEL_COLOURS.get(level, "")
            pc = _PREFIX_COLOURS.get(level, "")
            line = (
                f"{_DIM}[{ts}]{_RESET} "
                f"{pc}{_BOLD}{level:<8}{_RESET} "
                f"{_DIM}{name}{_RESET} "
                f"{lc}{msg}{_RESET}"
            )
        else:
            line = f"[{ts}] {level:<8} {name} — {msg}"

        if exc_text:
            line = f"{line}\n{exc_text}"

        return line
