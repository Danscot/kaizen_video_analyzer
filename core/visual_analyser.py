"""
visual_analyser.py
Sends batches of extracted frames to Gemma 4 vision and gets back
structured per-frame scene data: layout, typography, color palette,
animation state, mood, design notes.
"""

import json
import time
import os
from pathlib import Path

import PIL.Image
from google import genai
from google.genai import types
from google.genai.errors import APIError

from core.utils import log, log_warn, log_error, log_success


VISUAL_SYSTEM_PROMPT = """You are a professional motion design analyst specialising in TikTok and short-form video.
You will receive a batch of video frames. For each frame, analyse and return a JSON object with this exact structure:

{
  "frame_index": <number>,
  "layout": {
    "composition": "<description of overall spatial arrangement>",
    "zones": ["<zone description>"],
    "focal_point": "<where the eye is drawn>"
  },
  "typography": {
    "text_blocks": [
      {
        "content": "<text visible in frame>",
        "position": "<top/center/bottom + left/center/right>",
        "size": "<small/medium/large/hero>",
        "weight": "<thin/regular/bold/black>",
        "color": "<color description or hex if visible>",
        "alignment": "<left/center/right>"
      }
    ]
  },
  "color_palette": ["<hex or descriptive color name>"],
  "visual_elements": ["<named shapes, icons, illustrations, or motifs>"],
  "animation_state": "<enter|steady|exit|transition>",
  "mood": "<one-phrase emotional tone>",
  "design_notes": "<key observation about visual hierarchy, contrast, or spacing>"
}

Return ONLY a valid JSON array of scene objects, one per frame, in the order given.
No preamble, no explanation, no markdown fences."""


def _call_gemma_vision(
    client: genai.Client,
    batch_frames: list[tuple[int, PIL.Image.Image]],
    model: str,
    max_retries: int = 6,
    initial_delay: float = 4.0,
) -> list[dict]:
    """
    Send one batch of frames to Gemma vision with exponential backoff retry.
    Returns a list of scene dicts.
    """
    contents = [VISUAL_SYSTEM_PROMPT]
    for frame_idx, img in batch_frames:
        contents.append(f"[Frame {frame_idx}]:")
        contents.append(img)
    contents.append("Analyse each frame above and return the JSON array.")

    delay = initial_delay
    for attempt in range(1, max_retries + 1):
        try:
            log(f"    Gemma vision call (attempt {attempt}/{max_retries})…")
            response = client.models.generate_content(
                model=model,
                contents=contents,
            )
            raw = response.text.strip()
            # Strip accidental markdown fences
            raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
            result = json.loads(raw)
            return result if isinstance(result, list) else [result]

        except APIError as e:
            if e.code and 500 <= e.code < 600:
                log_warn(f"Server error ({e.code}). Retrying in {delay}s…")
                if attempt == max_retries:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 60)
            else:
                raise

        except json.JSONDecodeError as e:
            log_warn(f"JSON parse error: {e}. Retrying in {delay}s…")
            if attempt == max_retries:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 60)

        except Exception as e:
            log_warn(f"Unexpected error: {e}. Retrying in {delay}s…")
            if attempt == max_retries:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 60)

    return []


def analyse_frames_visually(
    frames: list[tuple[int, PIL.Image.Image]],
    gemini_model: str = "gemma-4-31b-it",
    batch_size: int = 8,
    max_retries: int = 6,
) -> dict:
    """
    Full visual analysis pipeline: batches frames → calls Gemma vision → returns raw results.

    Args:
        frames:        List of (frame_index, PIL.Image) from frame_extractor.
        gemini_model:  Gemma model to use for vision.
        batch_size:    Frames per API call (keep ≤10 to stay within context limits).
        max_retries:   Retry attempts per batch.

    Returns:
        Dict with keys: total_frames_extracted, batch_size, batches (list of batch results).
    """
    # Explicit timeout (120s) so a network stall surfaces as a clear error
    # instead of hanging the request thread indefinitely.
    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"],
        http_options=genai.types.HttpOptions(timeout=120_000),  # milliseconds
    )

    batches_input = [
        frames[i:i + batch_size]
        for i in range(0, len(frames), batch_size)
    ]
    log(f"  {len(frames)} frames → {len(batches_input)} batch(es) of up to {batch_size}")

    output_batches = []
    ok = fail = 0

    for i, batch in enumerate(batches_input, 1):
        frame_ids = [f[0] for f in batch]
        log(f"\n  Batch {i}/{len(batches_input)}  frames {frame_ids}")
        try:
            scenes = _call_gemma_vision(client, batch, gemini_model, max_retries)
            output_batches.append({
                "batch_index": i - 1,
                "frame_indices": frame_ids,
                "scenes": scenes,
            })
            log_success(f"{len(scenes)} scene(s) analysed")
            ok += 1
        except Exception as e:
            log_error(f"Batch {i} failed: {e}")
            output_batches.append({
                "batch_index": i - 1,
                "frame_indices": frame_ids,
                "scenes": [],
                "error": str(e),
            })
            fail += 1

    log(f"\n  Visual analysis: {ok} batches OK, {fail} failed")

    return {
        "total_frames_extracted": len(frames),
        "batch_size": batch_size,
        "batches": output_batches,
    }
