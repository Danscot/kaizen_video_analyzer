"""
analyser.py
Sends the transcript (+ metadata) to Gemini and gets back a structured
JSON description of the video for downstream reproduction pipelines.
"""

import json
import os
import re

from google import genai

from core.utils import log_warn


# ── Prompt ─────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert short-form video strategist and content analyst.
Your job is to analyse a video transcript and produce a machine-readable JSON object
that a production team can use to reproduce or re-create the video from scratch.

Return ONLY valid JSON — no markdown fences, no preamble, no commentary.
The JSON must strictly follow the schema below.

SCHEMA:
{
  "title": "Short catchy title inferred from the content",
  "niche": "The content niche (e.g. finance, fitness, comedy, education, lifestyle…)",
  "platform_style": "Detected platform style (TikTok, YouTube Shorts, Instagram Reel…)",
  "duration_estimate": "Estimated video duration in seconds (integer)",
  "language": "Language of the transcript",

  "summary": "2-4 sentence plain-English summary of what the video is about and what value it delivers to viewers.",

  "core_message": "The single most important takeaway or argument the video makes. One sentence.",

  "target_audience": "Who this video is aimed at. Be specific (e.g. 'beginner investors aged 18-30').",

  "hooks": [
    {
      "type": "opening_hook | pattern_interrupt | curiosity_hook | social_proof | pain_point | other",
      "timestamp_estimate": "e.g. 0-3s",
      "content": "Exact hook text or description",
      "technique": "Why this hook works (psychological trigger or persuasion technique)"
    }
  ],

  "scenes": [
    {
      "scene_number": 1,
      "timestamp_estimate": "e.g. 0-5s",
      "description": "What is happening visually / what the speaker is doing",
      "spoken_content": "Key things said in this scene (summarised or verbatim if short)",
      "purpose": "Role of this scene in the video (hook / setup / proof / CTA / transition…)",
      "tone": "Energy / emotional tone of this scene (excited, calm, urgent, humorous…)",
      "b_roll_suggestion": "Suggested B-roll or visual overlay for reproduction"
    }
  ],

  "cta": {
    "exists": true,
    "type": "follow | like | comment | visit_link | share | subscribe | other | none",
    "content": "Exact or paraphrased CTA text",
    "placement": "beginning | middle | end | throughout"
  },

  "content_structure": {
    "format": "e.g. talking-head, voiceover+broll, listicle, story, tutorial, skit, reaction…",
    "pacing": "fast | moderate | slow",
    "pattern": "Step-by-step description of the narrative arc (e.g. Hook → Problem → Solution → Proof → CTA)"
  },

  "emotional_journey": [
    {
      "phase": "e.g. curiosity, frustration, hope, excitement, satisfaction",
      "timestamp_estimate": "e.g. 0-5s",
      "trigger": "What creates this emotion in the viewer"
    }
  ],

  "keywords_and_topics": ["list", "of", "key", "topics", "and", "keywords"],

  "reproduction_notes": {
    "essential_elements": ["List of must-have elements to keep the video effective"],
    "tone_guide": "How the presenter should sound / feel",
    "visual_style": "Colour palette, text overlay style, transitions (inferred or suggested)",
    "music_suggestion": "Suggested music mood / genre",
    "estimated_complexity": "low | medium | high"
  }
}
"""


def _build_user_prompt(transcript: str, video_name: str) -> str:
    return (
        f"Video file: {video_name}\n\n"
        "TRANSCRIPT (with timestamps):\n"
        "────────────────────────────\n"
        f"{transcript}\n"
        "────────────────────────────\n\n"
        "Analyse this transcript thoroughly and return the structured JSON analysis."
    )


# ── Gemini call ────────────────────────────────────────────────────────────────

def analyse_transcript(
    transcript: str,
    video_name: str,
    gemini_model: str = "gemini-2.0-flash",
) -> dict:
    """
    Send the transcript to Gemini and parse the returned JSON analysis.

    Returns:
        A Python dict matching the schema defined in SYSTEM_PROMPT.
    Raises:
        RuntimeError if the API call fails or JSON cannot be parsed.
    """
    # Explicit timeout (120s) so a network stall surfaces as a clear error
    # instead of hanging the request thread indefinitely.
    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"],
        http_options=genai.types.HttpOptions(timeout=120_000),  # milliseconds
    )

    user_prompt = _build_user_prompt(transcript, video_name)

    response = client.models.generate_content(
        model=gemini_model,
        contents=user_prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.3,        # lower temp = more consistent structured output
            max_output_tokens=8192,
        ),
    )

    raw_text = response.text.strip()

    # Strip accidental markdown fences if the model added them
    raw_text = _strip_fences(raw_text)

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        # Attempt a lenient extraction as fallback
        extracted = _extract_json_block(raw_text)
        if extracted:
            return extracted
        raise RuntimeError(
            f"Gemini returned non-JSON output. Parse error: {exc}\n"
            f"Raw response (first 500 chars):\n{raw_text[:500]}"
        ) from exc


# ── Helpers ────────────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """Remove ```json … ``` or ``` … ``` wrappers."""
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    return text.strip()


def _extract_json_block(text: str) -> dict | None:
    """Try to pull the first { … } block out of messy text."""
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        log_warn("Could not extract JSON block from model output.")
        return None
