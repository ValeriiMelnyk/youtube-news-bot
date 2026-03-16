"""
tts_generator.py — Генерація голосу через Microsoft Edge TTS
Безкоштовно. Голос: uk-UA-OstapNeural (чоловічий, авторитетний, Ukrainian)
Не потребує API-ключа.
"""

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def _synthesize(script: str, output_path: Path) -> None:
    """Асинхронна генерація аудіо через Edge TTS"""
    import edge_tts

    # uk-UA-OstapNeural — чоловічий нейронний голос українською
    communicate = edge_tts.Communicate(
        text=script,
        voice="uk-UA-OstapNeural",
        rate="-5%",    # трохи повільніше для кращої розбірливості
        volume="+0%"
    )
    await communicate.save(str(output_path))


def generate_audio(script: str, output_path: Path) -> Path:
    """
    Перетворити текст сценарію на голосовий MP3 файл.
    Використовує Microsoft Edge TTS — безкоштовно, без API-ключа.
    """
    logger.info(f"Edge TTS: {len(script)} символів → {output_path.name}")

    clean_script = (
        script
        .replace("━", "—")
        .replace("…", "...")
        .strip()
    )

    asyncio.run(_synthesize(clean_script, output_path))

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"Edge TTS не створив файл: {output_path}")

    duration_estimate = len(clean_script.split()) / 2.5
    logger.info(f"Аудіо збережено. ~{duration_estimate:.0f} сек (uk-UA-OstapNeural)")

    return output_path
