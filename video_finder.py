"""
video_finder.py — Find trending news videos on YouTube using YouTube Data API
Searches for viral news content and filters by duration, view count, and recency.
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def _get_youtube_client():
    """Create authorized YouTube API client from OAuth refresh token"""
    creds = Credentials(
        token=None,
        refresh_token=os.environ.get("YOUTUBE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ.get("YOUTUBE_CLIENT_ID"),
        client_secret=os.environ.get("YOUTUBE_CLIENT_SECRET"),
        scopes=SCOPES
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def _load_used_videos() -> set:
    """Load set of already-used video IDs from file"""
    used_file = Path(__file__).parent / "used_videos.txt"
    if used_file.exists():
        return set(line.strip() for line in used_file.read_text().splitlines() if line.strip())
    return set()


def _save_video_id(video_id: str):
    """Append video ID to used_videos.txt"""
    used_file = Path(__file__).parent / "used_videos.txt"
    with open(used_file, "a") as f:
        f.write(f"{video_id}\n")
    logger.info(f"Saved video ID to used_videos.txt: {video_id}")


def find_trending_news_video() -> Optional[Dict]:
    """
    Search for trending news videos on YouTube.

    Returns:
        Dict with: video_id, title, description, channel_name, duration
        or None if no suitable video found
    """
    try:
        youtube = _get_youtube_client()
        used_videos = _load_used_videos()

        logger.info("Searching for trending news videos...")

        # Search for news videos from last 24 hours
        yesterday = (datetime.utcnow() - timedelta(days=1)).isoformat() + "Z"

        search_request = youtube.search().list(
            part="snippet",
            q="news breaking politics world",
            type="video",
            regionCode="UA",
            order="viewCount",  # Most viewed first
            publishedAfter=yesterday,
            maxResults=50,
            relevanceLanguage="uk",
            videoCaption="closedCaption",  # Must have captions
        )

        search_results = search_request.execute()
        videos = search_results.get("items", [])

        if not videos:
            logger.warning("No videos found in search results")
            return None

        logger.info(f"Found {len(videos)} candidate videos")

        # Get video details (duration, etc.)
        video_ids = [v["id"]["videoId"] for v in videos]

        # Fetch video details in chunks (API limits)
        for i in range(0, len(video_ids), 50):
            batch_ids = video_ids[i:i+50]
            details_request = youtube.videos().list(
                part="contentDetails,snippet,statistics",
                id=",".join(batch_ids)
            )
            details_results = details_request.execute()

            for video_data in details_results.get("items", []):
                video_id = video_data["id"]

                # Skip if already used
                if video_id in used_videos:
                    logger.debug(f"Skipping already-used video: {video_id}")
                    continue

                # Parse duration (ISO 8601)
                duration_str = video_data["contentDetails"]["duration"]  # PT45M30S format
                duration_seconds = _parse_iso_duration(duration_str)

                # Filter: 3-15 minutes (180-900 seconds)
                if not (180 <= duration_seconds <= 900):
                    logger.debug(
                        f"Skipping {video_id}: duration {duration_seconds}s "
                        f"(need 180-900s)"
                    )
                    continue

                # Filter: minimum view count (>10k views)
                view_count = int(video_data["statistics"].get("viewCount", 0))
                if view_count < 10000:
                    logger.debug(f"Skipping {video_id}: only {view_count} views")
                    continue

                # Passed all filters!
                snippet = video_data["snippet"]
                result = {
                    "video_id": video_id,
                    "title": snippet["title"],
                    "description": snippet.get("description", ""),
                    "channel_name": snippet["channelTitle"],
                    "duration_seconds": duration_seconds,
                    "view_count": view_count,
                }

                logger.info(f"Found suitable video: {result['title'][:60]}...")
                logger.info(f"  Duration: {duration_seconds}s, Views: {view_count}")
                return result

        logger.warning("No suitable videos found after filtering")
        return None

    except Exception as e:
        logger.error(f"Error finding trending videos: {e}")
        return None


def _parse_iso_duration(duration_str: str) -> int:
    """Parse ISO 8601 duration string (PT45M30S) to seconds"""
    import re

    match = re.match(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?",
        duration_str
    )
    if not match:
        return 0

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    return hours * 3600 + minutes * 60 + seconds
