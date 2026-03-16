"""
video_finder.py — Find trending news videos and podcast clips on YouTube.
Searches BOTH news and podcast niches simultaneously, returns the most-viewed
unused video from the combined results.
"""

import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# ── Search query pools ────────────────────────────────────────────────────────
NEWS_QUERIES = [
    "breaking news world politics 2025",
    "world news today latest",
    "war conflict geopolitics news",
    "ukraine russia war latest",
    "middle east news today",
    "US politics news today",
    "global news breaking",
]

PODCAST_QUERIES = [
    "Joe Rogan Experience clip 2025",
    "Lex Fridman podcast clip",
    "Tucker Carlson interview 2025",
    "podcast viral moment 2025",
    "interview shocking moment",
    "podcast highlights this week",
    "talk show viral clip 2025",
]


def _get_youtube_client():
    """Create YouTube API client using API key (read-only, no OAuth needed)"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set (used as YouTube Data API key)")
    return build("youtube", "v3", developerKey=api_key)


def _load_used_videos() -> set:
    """Load set of already-used video IDs from file"""
    used_file = Path(__file__).parent / "used_videos.txt"
    if used_file.exists():
        return set(line.strip() for line in used_file.read_text().splitlines() if line.strip())
    return set()


def _search_videos(youtube, query: str, published_after: str, max_results: int = 25) -> List[str]:
    """Execute a single YouTube search and return list of video IDs."""
    try:
        resp = youtube.search().list(
            part="id",
            q=query,
            type="video",
            order="viewCount",
            publishedAfter=published_after,
            maxResults=max_results,
            videoCaption="closedCaption",
        ).execute()
        return [item["id"]["videoId"] for item in resp.get("items", [])]
    except Exception as e:
        logger.warning(f"Search failed for '{query}': {e}")
        return []


def _get_video_details(youtube, video_ids: List[str]) -> List[Dict]:
    """Fetch content details + statistics for a list of video IDs."""
    if not video_ids:
        return []
    try:
        resp = youtube.videos().list(
            part="contentDetails,snippet,statistics",
            id=",".join(video_ids[:50]),
        ).execute()
        return resp.get("items", [])
    except Exception as e:
        logger.warning(f"Failed to fetch video details: {e}")
        return []


def _parse_iso_duration(duration_str: str) -> int:
    """Parse ISO 8601 duration string (e.g. PT45M30S) to seconds."""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_str)
    if not match:
        return 0
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return h * 3600 + m * 60 + s


def find_trending_news_video() -> Optional[Dict]:
    """
    Search for the most-viewed trending news video OR podcast clip.
    Searches BOTH categories simultaneously, merges results, and returns
    the highest-view-count video that hasn't been used yet.

    Duration filter: 3–90 minutes (180–5400 s) — wide range to include full podcasts.
    View filter: >5 000 views (lowered to catch fresher content).

    Returns:
        Dict with: video_id, title, description, channel_name,
                   duration_seconds, view_count, source_type
        or None if nothing suitable found.
    """
    try:
        import random

        youtube = _get_youtube_client()
        used_videos = _load_used_videos()

        # Search window: last 72 hours (wider = more variety)
        since = (datetime.utcnow() - timedelta(hours=72)).isoformat() + "Z"

        # ── Collect candidates from BOTH niches ──────────────────────────────
        all_ids: List[tuple] = []   # (video_id, source_type)

        # Pick one news query and one podcast query at random for variety
        news_q = random.choice(NEWS_QUERIES)
        pod_q  = random.choice(PODCAST_QUERIES)

        logger.info(f"🔍 News query:    {news_q}")
        logger.info(f"🎙️  Podcast query: {pod_q}")

        news_ids    = _search_videos(youtube, news_q,  since, max_results=25)
        podcast_ids = _search_videos(youtube, pod_q,   since, max_results=25)

        all_ids = [(vid, "news")    for vid in news_ids] + \
                  [(vid, "podcast") for vid in podcast_ids]

        logger.info(f"Found {len(news_ids)} news + {len(podcast_ids)} podcast candidates")

        if not all_ids:
            logger.error("No candidates found from any query")
            return None

        # ── Fetch details in one batch (up to 50) ────────────────────────────
        unique_ids = list(dict.fromkeys(vid for vid, _ in all_ids))  # deduplicate, preserve order
        source_map = {vid: src for vid, src in all_ids}

        details = _get_video_details(youtube, unique_ids[:50])

        # ── Score each video (sort by view count desc) ────────────────────────
        scored: List[Dict] = []
        for item in details:
            vid_id = item["id"]

            if vid_id in used_videos:
                continue

            duration_s = _parse_iso_duration(item["contentDetails"]["duration"])
            if not (180 <= duration_s <= 5400):        # 3 min – 90 min
                continue

            view_count = int(item["statistics"].get("viewCount", 0))
            if view_count < 5000:
                continue

            snippet = item["snippet"]
            scored.append({
                "video_id":        vid_id,
                "title":           snippet["title"],
                "description":     snippet.get("description", ""),
                "channel_name":    snippet["channelTitle"],
                "duration_seconds": duration_s,
                "view_count":      view_count,
                "source_type":     source_map.get(vid_id, "news"),
            })

        if not scored:
            logger.warning("No suitable video found after filtering")
            return None

        # Sort by views — most viral first
        scored.sort(key=lambda x: x["view_count"], reverse=True)
        best = scored[0]

        logger.info(
            f"✅ Best video: [{best['source_type'].upper()}] {best['title'][:70]}"
            f"  |  {best['view_count']:,} views  |  {best['duration_seconds']//60}m"
        )
        return best

    except Exception as e:
        logger.error(f"Error finding trending video: {e}")
        return None
