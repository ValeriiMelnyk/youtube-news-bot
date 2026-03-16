"""
script_generator.py — Generate Ukrainian metadata for YouTube videos via Gemini
Creates titles, descriptions, and tags based on original video content.
"""

import os
import json
import logging
from typing import Dict

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

SYSTEM_PROMPT = (
    "Ти — провідний редактор авторитетного українського новинного YouTube-каналу. "
    "Твій стиль: стриманий, точний, авторитетний — як у BBC або DW. "
    "Ніякої паніки, ніякого сенсаціоналізму. Тільки факти, подані чітко й зрозуміло. "
    "Ти завжди відповідаєш ВИКЛЮЧНО коректним JSON без жодного тексту навколо."
)


def generate_youtube_metadata(
    original_title: str,
    original_description: str,
    channel_name: str,
) -> Dict:
    """
    Generate Ukrainian YouTube metadata for a clipped news video.

    Args:
        original_title: Original video title from YouTube
        original_description: Original video description
        channel_name: Original channel name (for credit)

    Returns:
        Dict with: yt_title, description, tags
    """

    user_prompt = f"""На основі оригінального відео згенеруй українські метадані для YouTube Short.

ОРИГІНАЛЬНЕ ВІДЕО:
Заголовок: {original_title}
Опис: {original_description[:300]}
Канал: {channel_name}

ТВОЄ ЗАВДАННЯ:
1. Створи привабливий YouTube заголовок українською (до 60 символів)
2. Напиши опис з кредитом оригінальному каналу (100-130 символів)
3. Вибери 6-8 релевантних тегів (суміш українських та англійських)

Поверни ТІЛЬКИ цей JSON (без markdown):

{{
  "yt_title": "<Привабливий заголовок українською, до 60 символів>",
  "description": "<Опис з кредитом оригінальному каналу. Початок інформативний, кінець: Оригінальне відео від {{channel_name}}>",
  "tags": ["новини", "Україна", "світ", "<тег4>", "<тег5>", "<тег6>", "Shorts", "BreakingNews"]
}}"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.5,
                max_output_tokens=600,
                response_mime_type="application/json",
            )
        )

        raw = response.text.strip()
        # Remove possible markdown wrappers
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw)

        required_fields = ["yt_title", "description", "tags"]
        for field in required_fields:
            if field not in result:
                raise ValueError(f"Gemini did not return field: {field}")

        logger.info(f"Generated metadata: {result['yt_title']}")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Gemini returned invalid JSON: {e}")
        return _fallback_metadata(original_title, channel_name)
    except Exception as e:
        logger.error(f"Error generating metadata: {e}")
        return _fallback_metadata(original_title, channel_name)


def _fallback_metadata(title: str, channel: str) -> Dict:
    """Fallback metadata if Gemini unavailable"""
    return {
        "yt_title": title[:60],
        "description": f"Хай-лайт новини. Оригінал від {channel}. Підписуйтеся!",
        "tags": ["новини", "Україна", "світ", "breaking", "news", "Shorts"]
    }
