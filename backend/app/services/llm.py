"""Gemini wrapper — turns raw itinerary text into structured items + voiceover script."""
from __future__ import annotations

import json
import logging
import os
from datetime import date as date_type

import google.generativeai as genai

log = logging.getLogger(__name__)


_PROMPT = """You are a tour-operations assistant for Travel Seasons, an Indian senior-traveller (age 60+) tour company.

The Tour Manager just wrote up the plan for ONE day of a guided tour. Your job is to:

1. EXTRACT a structured itinerary from the text
2. RANK the most filmable / emotional moments
3. WRITE a 30-second voiceover script for a daily recap video

Day date: {day_date}

Raw text from the Tour Manager:
---
{raw_text}
---

Return your response as STRICT JSON matching this schema:

{{
  "theme": "short tagline for the day, e.g. 'Old & New Singapore'",
  "weather": "brief weather note if mentioned, else null",
  "tour_manager": "TM name if mentioned, else null",
  "items": [
    {{
      "start_time": "HH:MM (24h)",
      "end_time": "HH:MM (24h)",
      "title": "short activity name, descriptive — admin sees this, e.g. 'Chinatown walking tour'",
      "description": "1-2 sentence summary of what happened",
      "caption": "diary-style one-liner shown over the photos in the recap video. 10-15 words, first-person plural ('we'), past tense, conversational, warm. Mention specifics from the description (places, food, names). NO exclamation marks. e.g. 'Walked Chinatown's red lanterns — the temple looked like home.'",
      "importance": 1-10
    }}
  ],
  "filmable_moments": [
    {{
      "title": "short moment name",
      "why": "why it's emotionally important",
      "importance": 1-10
    }}
  ],
  "voiceover_script": "55-65 word script delivered at gentle pace in 30 seconds. WARM, PERSONAL, no exclamation marks, no promotional energy. End with a one-sentence teaser for tomorrow if known."
}}

Rules:
- start_time and end_time MUST be 24-hour HH:MM strings (e.g. "09:30", "14:32").
- **CRITICAL: end_time MUST be strictly LATER than start_time.** Never repeat
  start_time as end_time. Every activity must have a non-zero duration.
- If the input describes a single moment (e.g. "2:32 PM — First Frame"),
  set end_time to the NEXT activity's start_time (so the windows tile cleanly).
  For the LAST activity in the day, set end_time to start_time + 15 minutes.
- If the input gives an explicit range (e.g. "2:30 – 4:00 PM"), use both.
- Order items in chronological order by start_time. position MUST be 0, 1, 2…
- Activities should TILE the day — no gaps where possible. If two moments are
  close ("2:32 PM" and "2:33 PM"), end the first activity at the second's start.
- importance: 1 = filler/transition, 10 = the absolute hero shot.
- Filmable moments are the 3-5 most emotionally weighted moments (e.g. surprise birthday cake, group laughter, sunset, tears).
- voiceover_script tone: warm and gentle, suitable for a 65+ Indian audience. No "amazing!" / "incredible!" / exclamation marks.
- Output ONLY the JSON object — no markdown fences, no commentary."""


class LLMError(Exception):
    pass


def _client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise LLMError("GEMINI_API_KEY not set in .env")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.0-flash")


def structure_itinerary(raw_text: str, day_date: date_type) -> dict:
    """Sends raw TM text to Gemini, returns a dict matching the schema in _PROMPT."""
    if not raw_text.strip():
        raise LLMError("raw_text is empty")
    model = _client()
    prompt = _PROMPT.format(day_date=day_date.isoformat(), raw_text=raw_text.strip())
    resp = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.7,
            "response_mime_type": "application/json",
        },
    )
    text = resp.text or ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        # Strip possible code fences
        cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            log.error("Gemini returned non-JSON: %s", text[:500])
            raise LLMError(f"Gemini returned non-JSON output: {e}") from e

    # Light validation
    if not isinstance(data.get("items"), list):
        raise LLMError(f"Gemini response missing 'items' list: {data}")
    return data
