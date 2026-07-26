"""
utils.py — shared constants, colours, logging helpers, UI primitives.
"""

import os
import sys

# ── Supported file types ──────────────────────────────────────────────────────

SUPPORTED_VIDEO_EXTS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm",
    ".flv", ".wmv", ".m4v", ".3gp", ".ts",
}

SUPPORTED_AUDIO_EXTS = {
    ".mp3", ".wav", ".m4a", ".aac", ".ogg",
    ".flac", ".opus", ".wma", ".aiff",
}

# ── ANSI colours ──────────────────────────────────────────────────────────────

class C:
    """Colour tokens — fall back to empty strings on non-TTY terminals."""
    _t = sys.stdout.isatty()
    BOLD   = "\033[1m"   if _t else ""
    DIM    = "\033[2m"   if _t else ""
    CYAN   = "\033[96m"  if _t else ""
    GREEN  = "\033[92m"  if _t else ""
    YELLOW = "\033[93m"  if _t else ""
    RED    = "\033[91m"  if _t else ""
    R      = "\033[0m"   if _t else ""   # reset


# ── Banner ────────────────────────────────────────────────────────────────────

def banner():
    print(f"""{C.BOLD}{C.CYAN}
  ██╗  ██╗ █████╗ ██╗███████╗███████╗███╗   ██╗
  ██║ ██╔╝██╔══██╗██║╚══███╔╝██╔════╝████╗  ██║
  █████╔╝ ███████║██║  ███╔╝ █████╗  ██╔██╗ ██║
  ██╔═██╗ ██╔══██║██║ ███╔╝  ██╔══╝  ██║╚██╗██║
  ██║  ██╗██║  ██║██║███████╗███████╗██║ ╚████║
  ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚══════╝╚══════╝╚═╝  ╚═══╝
  VIDEO ANALYST  ·  Whisper × Gemini{C.R}
""")


# ── UI primitives ─────────────────────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def divider(title: str = ""):
    width = 55
    if title:
        pad = max(0, width - len(title) - 4)
        print(f"\n  {C.DIM}── {title} {'─' * pad}{C.R}\n")
    else:
        print(f"\n  {C.DIM}{'─' * width}{C.R}\n")


def menu(prompt: str, options: list[str]) -> int:
    """
    Display a numbered menu and return the 1-based index the user chose.
    Loops until a valid choice is made.
    """
    print(f"  {C.BOLD}{prompt}{C.R}\n")
    for i, opt in enumerate(options, 1):
        print(f"    {C.DIM}{i}.{C.R}  {opt}")
    print()
    while True:
        raw = input(f"  {C.CYAN}Choose [1-{len(options)}]:{C.R}  ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw)
        log_warn(f"Please enter a number between 1 and {len(options)}.")


def prompt_path(label: str, allowed_exts: set[str]) -> "Path | None":
    """
    Ask the user to type a file path. Validates existence and extension.
    Returns a Path, or None if the user types 'q' to cancel.
    """
    from pathlib import Path
    ext_hint = "  ".join(sorted(allowed_exts))
    print(f"  {C.DIM}Allowed: {ext_hint}{C.R}")
    print(f"  {C.DIM}Type 'q' to cancel.{C.R}\n")
    while True:
        raw = input(f"  {C.CYAN}{label}:{C.R}  ").strip()
        if raw.lower() == "q":
            return None
        # Strip surrounding quotes (drag-and-drop on macOS/Windows)
        raw = raw.strip("'\"")
        p = Path(raw).expanduser()
        if not p.exists():
            log_warn(f"File not found: {p}")
            continue
        if p.suffix.lower() not in allowed_exts:
            log_warn(
                f"Extension '{p.suffix}' not in allowed list. "
                f"Expected one of: {', '.join(sorted(allowed_exts))}"
            )
            override = input(f"  {C.YELLOW}Use it anyway? [y/N]:{C.R}  ").strip().lower()
            if override != "y":
                continue
        return p


def status_bar(ok: int, fail: int):
    total = ok + fail
    print(f"\n  {'═'*55}")
    ok_col   = C.GREEN  if ok   > 0 else C.DIM
    fail_col = C.RED    if fail > 0 else C.DIM
    print(
        f"  {C.BOLD}Done.{C.R}  "
        f"{ok_col}✓ {ok} succeeded{C.R}   "
        f"{fail_col}✗ {fail} failed{C.R}   "
        f"{C.DIM}({total} total){C.R}"
    )
    print(f"  {'═'*55}")


# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str):
    print(f"  {C.CYAN}›{C.R} {msg}")

def log_success(msg: str):
    print(f"  {C.GREEN}✓{C.R} {msg}")

def log_warn(msg: str):
    print(f"  {C.YELLOW}⚠{C.R}  {msg}")

def log_error(msg: str):
    print(f"  {C.RED}✗{C.R}  {msg}", flush=True)
