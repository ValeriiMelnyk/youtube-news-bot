"""
video_finder.py — Find trending news / podcast videos on YouTube.

Strategy (no search.list — it requires special quota):
  1. PRIMARY: videos.list(chart="mostPopular") by category
       - Category 25 = News & Politics
       - Category 22 = People & Blogs  (podcasts, interviews)
  2. FALLBACK: yt-dlp scrapes YouTube trending page directly (no API key needed)

Both paths merge results, sort by view count, return the most-viral unused video.
"""

import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Video category IDs we care about
CATEGORY_NEWS       = "25"   # News & Politics
CATEGORY_BLOGS      = "22"   # People & Blogs  (podcasts / interviews)
CATEGORY_ENTERTAIN  = "24"   # Entertainment

# YouTube trending feed URLs (scraped by yt-dlp, no API key needed)
YT_TRENDING_NEWS = (
    "https://www.youtube.com/feed/trending"
    "?bp=4gINGgt5dFBfZ3duX25ld3M%3D"          # News tab
)
YT_TRENDING_DEFAULT = "https://www.youtube.com/feed/trending"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_used_videos() -> set:
    used_file = Path(__file__).parent / "used_videos.txt"
    if used_file.exists():
        return set(
            line.strip()
            for line in used_file.read_text().splitlines()
            if line.strip()
        )
    return set()


def _parse_iso_duration(duration_str: str) -> int:
    """PT1H23M45S → seconds"""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_str)
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def _is_good_duration(seconds: int) -> bool:
    """3 min – 90 min"""
    return 180 <= seconds <= 5400


def _build_candidate(item: dict, source: str) -> Optional[Dict]:
    """Build a candidate dict from a videos.list item, or None if it fails filters."""
    vid_id   = item.get("id") or item.get("video_id", "")
    if not vid_id:
        return None

    stats    = item.get("statistics", {})
    content  = item.get("contentDetails", {})
    snippet  = item.get("snippet", {})

    view_count = int(stats.get("viewCount", 0))
    if view_count < 5_000:
        return None

    duration_s = _parse_iso_duration(content.get("duration", "PT0S"))
    if not _is_good_duration(duration_s):
        return None

    return {
        "video_id":         vid_id,
        "title":            snippet.get("title", ""),
        "description":      snippet.get("description", "")[:500],
        "channel_name":     snippet.get("channelTitle", ""),
        "duration_seconds": duration_s,
        "view_count":       view_count,
        "source_type":      source,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Primary path — YouTube Data API  videos.list(chart=mostPopular)
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_most_popular(youtube, category_id: str, region: str = "UA", max_results: int = 50) -> List[Dict]:
    """Use videos.list with chart=mostPopular — does NOT need search quota."""
    try:
        resp = youtube.videos().list(
            part="contentDetails,snippet,statistics",
            chart="mostPopular",
            videoCategoryId=category_id,
            regionCode=region,
            maxResults=max_results,
            hl="uk",
        ).execute()
        candidates = []
        for item in resp.get("items", []):
            c = _build_candidate(item, f"trending_cat{category_id}")
            if c:
                candidates.append(c)
        logger.info(f"  category {category_id}: {len(candidates)} candidates")
        return candidates
    except Exception as e:
        logger.warning(f"videos.list(chart=mostPopular, cat={category_id}) failed: {e}")
        return []


def _candidates_via_api(used_videos: set) -> List[Dict]:
    """Try YouTube Data API first."""
    api_key = os.environ.get("YOUTUBE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("No API key available for YouTube Data API")
        return []
    try:
        from googleapiclient.discovery import build
        youtube = build("youtube", "v3", developerKey=api_key)

        all_candidates: List[Dict] = []
        # News & Politics
        all_candidates += _fetch_most_popular(youtube, CATEGORY_NEWS)
        # People & Blogs (podcasts)
        all_candidates += _fetch_most_popular(youtube, CATEGORY_BLOGS)

        # Filter already-used
        return [c for c in all_candidates if c["video_id"] not in used_videos]
    except Exception as e:
        logger.warning(f"YouTube Data API path failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Fallback path — yt-dlp scraping (no API key needed)
# ─────────────────────────────────────────────────────────────────────────────

def _candidates_via_ytdlp(used_videos: set) -> List[Dict]:
    """Scrape YouTube trending page with yt-dlp — zero API keys required."""
    try:
        import yt_dlp

        candidates: List[Dict] = []

        for url, source in [
            (YT_TRENDING_NEWS,    "trending_news"),
            (YT_TRENDING_DEFAULT, "trending_default"),
        ]:
            try:
                ydl_opts = {
                    "extract_flat": "in_playlist",
                    "quiet": True,
                    "no_warnings": True,
                    "playlist_items": "1-30",
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)

                entries = info.get("entries", []) if info else []
                logger.info(f"yt-dlp {source}: {len(entries)} entries from trending")

                for entry in entries:
                    vid_id = entry.get("id") or entry.get("url", "").split("v=")[-1].split("&")[0]
                    if not vid_id or vid_id in used_videos:
                        continue

                    duration_s = entry.get("duration", 0) or 0
                    view_count = entry.get("view_count", 0) or 0

                    if not _is_good_duration(duration_s):
                        continue
                    if view_count < 5_000:
                        # yt-dlp flat extract often doesn't have view_count — keep anyway
                        if view_count != 0:
                            continue

                    candidates.append({
                        "video_id":         vid_id,
                        "title":            entry.get("title", ""),
                        "description":      entry.get("description", "")[:500] if entry.get("description") else "",
                        "channel_name":     entry.get("uploader", "") or entry.get("channel", ""),
                        "duration_seconds": duration_s,
                        "view_count":       view_count,
                        "source_type":      source,
                    })
            except Exception as e:
                logger.warning(f"yt-dlp scrape failed for {source}: {e}")

        return candidates
    except Exception as e:
        logger.warning(f"yt-dlp path failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Public function
# ─────────────────────────────────────────────────────────────────────────────

def find_trending_news_video() -> Optional[Dict]:
    """
    Find the most-viewed trending news / podcast video not yet published.

    Returns dict with: video_id, title, description, channel_name,
                       duration_seconds, view_count, source_type
    or None if nothing found.
    """
    used_videos = _load_used_videos()

    # 1. Try YouTube Data API (videos.list / mostPopular — no search quota needed)
    candidates = _candidates_via_api(used_videos)
    logger.info(f"API path returned {len(candidates)} candidates")

    # 2. Fallback: yt-dlp scraping
    if not candidates:
        logger.info("API returned nothing — trying yt-dlp trending scrape...")
        candidates = _candidates_via_ytdlp(used_videos)
        logger.info(f"yt-dlp path returned {len(candidates)} candidates")

    if not candidates:
        logger.error("No candidates found from any source")
        return None

    # Sort by view count — most viral first
    candidates.sort(key=lambda x: x["view_count"], reverse=True)

    # Log top 5 candidates
    for i, c in enumerate(candidates[:5]):
        logger.info(
            f"  #{i+1} [{c['source_type']}] {c['title'][:60]}"
            f"  |  {c['view_count']:,} views  |  {c['duration_seconds']//60}m"
        )

    return candidates[0]


def find_trending_news_video_list(top_n: int = 5) -> List[Dict]:
    """
    Return up to top_n trending video candidates sorted by view count.
    Used by main.py to try multiple candidates if one fails to download.
    """
    used_videos = _load_used_videos()

    candidates = _candidates_via_api(used_videos)
    logger.info(f"API path returned {len(candidates)} candidates")

    if not candidates:
        logger.info("API returned nothing — trying yt-dlp trending scrape...")
        candidates = _candidates_via_ytdlp(used_videos)
        logger.info(f"yt-dlp path returned {len(candidates)} candidates")

    if not candidates:
        logger.error("No candidates found from any source")
        return []

    candidates.sort(key=lambda x: x["view_count"], reverse=True)
    return candidates[:top_n]
