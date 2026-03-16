"""
youtube_uploader.py — Публікація відео на YouTube
Використовує YouTube Data API v3 з OAuth 2.0 refresh token
"""

import os
import logging
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _get_client():
    """Створити авторизованого YouTube API клієнта"""
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=SCOPES
    )
    # Оновити токен
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def upload_to_youtube(
    video_path: Path,
    title: str,
    description: str,
    tags: list
) -> str:
    """
    Завантажити відео на YouTube як Short.

    Повертає: video_id (str)
    """
    youtube = _get_client()

    # YouTube Shorts алгоритм спрацьовує коли:
    # 1. Відео вертикальне (9:16) ≤ 60 сек
    # 2. В описі є #Shorts
    full_description = (
        f"{description}\n\n"
        "#Shorts #Новини #Ukraine #Україна #WorldNews #BreakingNews #Новини2025"
    )

    # Уникаємо дублювання тегів
    unique_tags = list(dict.fromkeys(tags + ["Shorts", "Новини", "Ukraine", "WorldNews"]))

    body = {
        "snippet": {
            "title": title[:100],               # YouTube обмежує 100 символів
            "description": full_description,
            "tags": unique_tags[:30],            # Максимум 30 тегів
            "categoryId": "25",                  # News & Politics
            "defaultLanguage": "uk",
            "defaultAudioLanguage": "uk"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=5 * 1024 * 1024  # 5 MB chunks
    )

    logger.info(f"Починаю завантаження: '{title}'")

    try:
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                logger.info(f"  Завантаження: {pct}%")

        video_id = response["id"]
        logger.info(f"✅ Відео опубліковано: https://youtube.com/shorts/{video_id}")
        return video_id

    except HttpError as e:
        error_info = e.error_details if hasattr(e, "error_details") else str(e)
        logger.error(f"YouTube API помилка {e.resp.status}: {error_info}")
        raise
