#!/usr/bin/env python3
"""
=============================================================
  Autonomous YouTube Shorts News Bot
  Автономний бот для генерації YouTube Shorts з новинами
=============================================================
Щодня автоматично:
  1. Збирає топ-новини зі світових джерел
  2. Вибирає найважливішу через GPT-4o-mini
  3. Генерує сценарій українською мовою
  4. Озвучує голосом onyx (авторитетний, чоловічий)
  5. Монтує вертикальне відео 1080x1920
  6. Публікує на YouTube як Short
"""

import os
import logging
import tempfile
from pathlib import Path

# ─── Логування ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


def validate_env():
    """Перевірка наявності обов'язкових змінних середовища"""
    required = [
        "OPENAI_API_KEY",
        "YOUTUBE_CLIENT_ID",
        "YOUTUBE_CLIENT_SECRET",
        "YOUTUBE_REFRESH_TOKEN",
    ]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(
            f"❌ Відсутні обов'язкові змінні: {', '.join(missing)}\n"
            "Перевір GitHub Secrets або .env файл"
        )


def main():
    validate_env()

    from news_fetcher import fetch_top_news
    from script_generator import generate_script
    from tts_generator import generate_audio
    from video_creator import create_video
    from youtube_uploader import upload_to_youtube

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        # ── Крок 1: Збір новин ──────────────────────────────
        logger.info("📰 Крок 1/5 — Завантаження новин...")
        articles = fetch_top_news()
        if not articles:
            raise RuntimeError("Не вдалось отримати новини. Перевір інтернет-з'єднання.")
        logger.info(f"   Знайдено {len(articles)} статей з {len(set(a['source'] for a in articles))} джерел")

        # ── Крок 2: Генерація сценарію ──────────────────────
        logger.info("✍️  Крок 2/5 — Генерація сценарію (GPT-4o-mini)...")
        script_data = generate_script(articles)
        logger.info(f"   Заголовок: {script_data.get('yt_title', '—')}")
        logger.info(f"   Ключових фактів: {len(script_data.get('key_facts', []))}")

        # ── Крок 3: Озвучення ───────────────────────────────
        logger.info("🎙️  Крок 3/5 — Генерація аудіо (голос onyx)...")
        audio_path = generate_audio(
            script=script_data["script"],
            output_path=tmp / "voice.mp3"
        )
        logger.info(f"   Аудіо збережено ({audio_path.stat().st_size // 1024} KB)")

        # ── Крок 4: Монтаж відео ────────────────────────────
        logger.info("🎬 Крок 4/5 — Монтаж відео (1080x1920)...")
        video_path = create_video(
            title=script_data.get("title_overlay", script_data.get("yt_title", "НОВИНИ")),
            key_facts=script_data.get("key_facts", []),
            audio_path=audio_path,
            topic_keywords=script_data.get("pexels_keywords", "world politics conflict"),
            tmp_dir=tmp,
            output_path=tmp / "short.mp4"
        )
        size_mb = video_path.stat().st_size / (1024 * 1024)
        logger.info(f"   Відео готове ({size_mb:.1f} MB)")

        # ── Крок 5: Публікація ──────────────────────────────
        logger.info("🚀 Крок 5/5 — Публікація на YouTube...")
        video_id = upload_to_youtube(
            video_path=video_path,
            title=script_data.get("yt_title", "Новини дня"),
            description=script_data.get("description", "Найважливіші новини сьогодні"),
            tags=script_data.get("tags", ["новини", "Україна", "world"])
        )

        logger.info("=" * 50)
        logger.info("✅ Відео успішно опубліковано!")
        logger.info(f"🔗 https://youtube.com/shorts/{video_id}")
        logger.info("=" * 50)


if __name__ == "__main__":
    main()
