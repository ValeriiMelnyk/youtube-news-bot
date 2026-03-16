"""
tts_generator.py — Генерація голосу через OpenAI TTS
Голос: onyx (чоловічий, авторитетний)
"""

import os
import logging
from pathlib import Path
from openai import OpenAI

logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def generate_audio(script: str, output_path: Path) -> Path:
    """
    Перетворити текст сценарію на голосовий MP3 файл.

    Параметри:
        script      — текст сценарію (100–200 слів)
        output_path — куди зберегти MP3 файл

    Повертає: Path до збереженого MP3
    """
    logger.info(f"TTS: {len(script)} символів → {output_path.name}")

    # Очищення тексту від символів, що можуть порушити TTS
    clean_script = (
        script
        .replace("━", "—")
        .replace("…", "...")
        .strip()
    )

    response = client.audio.speech.create(
        model="tts-1",          # Стандартна якість — економніший варіант
        voice="onyx",           # Чоловічий, авторитетний голос
        input=clean_script,
        speed=0.95,             # Трохи повільніше для кращої розбірливості
        response_format="mp3"
    )

    response.stream_to_file(str(output_path))

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"TTS не створив файл: {output_path}")

    duration_estimate = len(clean_script.split()) / 2.5  # ~2.5 слова/сек
    logger.info(f"Аудіо збережено. Приблизна тривалість: {duration_estimate:.0f} сек")

    return output_path
