"""
transcriber.py
Two entry points:
  transcribe_video(path)  — extracts audio via ffmpeg then runs Whisper
  transcribe_audio(path)  — feeds an existing audio file directly to Whisper
"""

import subprocess
import tempfile
from pathlib import Path

import whisper

from core.utils import log, log_warn, SUPPORTED_AUDIO_EXTS


# ── ffmpeg helpers ─────────────────────────────────────────────────────────────

def _extract_audio(video_path: Path, audio_path: Path) -> None:
    """Convert any video to a 16 kHz mono WAV (Whisper's optimal format)."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",                  # drop video stream
        "-acodec", "pcm_s16le", # raw PCM
        "-ar", "16000",         # 16 kHz
        "-ac", "1",             # mono
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed (exit {result.returncode}):\n{result.stderr[-1000:]}"
        )


def _convert_audio(audio_path: Path, out_path: Path) -> None:
    """
    Re-encode an audio file to 16 kHz mono WAV for Whisper.
    If the file is already a .wav we still normalise sample-rate / channels.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", str(audio_path),
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg audio conversion failed (exit {result.returncode}):\n{result.stderr[-1000:]}"
        )


# ── Whisper ────────────────────────────────────────────────────────────────────

def _whisper_transcribe(audio_path: Path, model_name: str) -> str:
    """Run Whisper on a WAV file and return a timestamped transcript."""
    log(f"  Loading Whisper '{model_name}' model…")
    model = whisper.load_model(model_name)

    log("  Running transcription…")
    result = model.transcribe(str(audio_path), task="transcribe", verbose=False)

    segments = result.get("segments", [])
    if not segments:
        log_warn("No segments found — returning raw text without timestamps.")
        return result.get("text", "").strip()

    lines = []
    for seg in segments:
        start = _fmt_time(seg["start"])
        end   = _fmt_time(seg["end"])
        text  = seg["text"].strip()
        lines.append(f"[{start} → {end}]  {text}")

    return "\n".join(lines)


def _fmt_time(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


# ── Public API ─────────────────────────────────────────────────────────────────

def transcribe_video(
    video_path: Path,
    whisper_model: str = "base",
    keep_audio: bool = False,
) -> str:
    """
    Extract audio from a video file, then transcribe with Whisper.

    Args:
        video_path:    Path to the source video.
        whisper_model: Whisper model size (tiny/base/small/medium/large).
        keep_audio:    If True, save the extracted WAV next to the video.

    Returns:
        Timestamped transcript string.
    """
    if keep_audio:
        audio_path = video_path.with_suffix(".wav")
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        audio_path = Path(tmp.name)

    try:
        log(f"  Extracting audio from '{video_path.name}'…")
        _extract_audio(video_path, audio_path)
        log(f"  Audio ready  →  {audio_path.name}")
        return _whisper_transcribe(audio_path, whisper_model)
    finally:
        if not keep_audio and audio_path.exists():
            audio_path.unlink()


def transcribe_audio(
    audio_path: Path,
    whisper_model: str = "base",
) -> str:
    """
    Transcribe an existing audio file directly (no video extraction step).

    Normalises the file to 16 kHz mono WAV via ffmpeg first (handles
    mp3, m4a, aac, ogg, flac, opus, etc.).

    Args:
        audio_path:    Path to the source audio file.
        whisper_model: Whisper model size.

    Returns:
        Timestamped transcript string.
    """
    # If the file is already a standard WAV we still normalise just in case
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    normalised = Path(tmp.name)

    try:
        log(f"  Normalising audio '{audio_path.name}' → 16 kHz WAV…")
        _convert_audio(audio_path, normalised)
        return _whisper_transcribe(normalised, whisper_model)
    finally:
        if normalised.exists():
            normalised.unlink()
