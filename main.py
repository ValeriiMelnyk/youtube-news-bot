#!/usr/bin/env python3
"""
=============================================================
  YouTube Shorts News Bot (Rewritten)
  Автономний бот для публікації трендових новин у YouTube Shorts
=============================================================
Щодня автоматично:
  1. Знаходить трендові новинні відео на YouTube (YouTube Data API)
  2. Завантажує відео (yt-dlp)
  3. Обрізає 45-секундний клип, крощує до 9:16 (вертикаль)
  4. Завантажує субтитри YouTube та перекладає на українську (Gemini)
  5. Записує українські субтитри на відео
  6. Генерує українські заголовок, опис, теги (Gemini)
  7. Публікує як YouTube Short
"""

import os
import logging
import tempfile
import subprocess
from pathlib import Path

# ─── Логування ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


def validate_env():
    """Validate required environment variables"""
    required = [
        "GEMINI_API_KEY",
        "YOUTUBE_CLIENT_ID",
        "YOUTUBE_CLIENT_SECRET",
        "YOUTUBE_REFRESH_TOKEN",
    ]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(
            f"Missing required env vars: {', '.join(missing)}\n"
            "Check GitHub Secrets or .env file"
        )


def save_used_video(video_id: str):
    """Save video ID to used_videos.txt and git commit"""
    try:
        used_file = Path(__file__).parent / "used_videos.txt"

        # Append video ID
        with open(used_file, "a") as f:
            f.write(f"{video_id}\n")

        logger.info(f"Saved video ID to used_videos.txt: {video_id}")

        # Git commit and push
        repo_dir = Path(__file__).parent
        os.chdir(repo_dir)

        # Configure git if needed
        subprocess.run(
            ["git", "config", "user.email", "bot@github.com"],
            capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "YouTube News Bot"],
            capture_output=True
        )

        # Add and commit
        subprocess.run(
            ["git", "add", "used_videos.txt"],
            capture_output=True,
            check=True
        )
        result = subprocess.run(
            ["git", "commit", "-m", f"Add used video: {video_id}"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            logger.info(f"Git commit successful")

            # Push
            push_result = subprocess.run(
                ["git", "push"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if push_result.returncode == 0:
                logger.info("Git push successful")
            else:
                logger.warning(f"Git push failed: {push_result.stderr}")
        else:
            logger.warning(f"Git commit failed (nothing to commit or error)")

    except Exception as e:
        logger.error(f"Error saving used video to git: {e}")


def main():
    validate_env()

    from video_finder import find_trending_news_video
    from video_processor import process_video_pipeline
    from script_generator import generate_youtube_metadata
    from youtube_uploader import upload_to_youtube

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        # ── Step 1: Find trending news video ──────────────────
        logger.info("🔍 Step 1/5 — Finding trending news video...")
        video_info = find_trending_news_video()
        if not video_info:
            raise RuntimeError("Could not find suitable trending video. Exiting.")

        video_id = video_info["video_id"]
        logger.info(f"   Found: {video_info['title'][:70]}")
        logger.info(f"   Duration: {video_info['duration_seconds']}s, Views: {video_info['view_count']:,}")

        # ── Step 2: Download and process video ────────────────
        logger.info("📥 Step 2/5 — Downloading and processing video...")
        video_path = process_video_pipeline(
            video_id,
            video_title=video_info["title"],
            video_description=video_info["description"],
            output_dir=tmp,
        )
        if not video_path:
            raise RuntimeError("Failed to process video. Exiting.")

        size_mb = video_path.stat().st_size / (1024 * 1024)
        logger.info(f"   Processed video ready ({size_mb:.1f} MB)")

        # ── Step 3: Generate Ukrainian metadata ────────────────
        logger.info("✍️  Step 3/5 — Generating Ukrainian metadata...")
        metadata = generate_youtube_metadata(
            original_title=video_info["title"],
            original_description=video_info["description"],
            channel_name=video_info["channel_name"],
        )
        logger.info(f"   Title: {metadata['yt_title']}")
        logger.info(f"   Tags: {len(metadata['tags'])} items")

        # ── Step 4: Upload to YouTube ────────────────────────
        logger.info("🚀 Step 4/5 — Uploading to YouTube...")
        uploaded_id = upload_to_youtube(
            video_path=video_path,
            title=metadata.get("yt_title", "Новини"),
            description=metadata.get("description", "Новинний клип"),
            tags=metadata.get("tags", ["новини", "Shorts"])
        )

        # ── Step 5: Save video ID and commit ─────────────────
        logger.info("💾 Step 5/5 — Saving used video ID...")
        save_used_video(video_id)

        logger.info("=" * 60)
        logger.info("✅ Video successfully published!")
        logger.info(f"🔗 https://youtube.com/shorts/{uploaded_id}")
        logger.info(f"Source: {video_info['channel_name']}")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
