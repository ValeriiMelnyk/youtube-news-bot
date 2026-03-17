# CLAUDE.md — YouTube News Bot

This file provides guidance for AI assistants working in this codebase.

## Project Overview

An automated YouTube Shorts bot that:
1. Finds trending news/podcast videos on YouTube (Ukrainian region)
2. Downloads, clips, and crops them to vertical 9:16 format
3. Adds word-by-word Ukrainian subtitles and a hook overlay
4. Uploads the result as a YouTube Short
5. Tracks published video IDs to prevent duplicates

Runs daily via GitHub Actions at 07:00 UTC (10:00 Kyiv time).

---

## Repository Structure

```
youtube-news-bot/
├── main.py                 # Orchestration entrypoint — runs the 5-step pipeline
├── video_finder.py         # Step 1: Discover trending videos via YouTube Data API + yt-dlp fallback
├── video_processor.py      # Step 2: Download, clip, crop, translate, subtitle
├── script_generator.py     # Step 3: Generate Ukrainian metadata via Gemini
├── youtube_uploader.py     # Step 4: Upload to YouTube via OAuth 2.0
├── used_videos.txt         # Step 5: Tracks published video IDs (committed by the bot)
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
├── .github/workflows/
│   └── daily.yml           # GitHub Actions workflow (daily schedule + manual trigger)
└── *.md / *.txt            # Documentation files
```

---

## Pipeline Architecture

```
main.py
  │
  ├─ video_finder.find_trending_news_video_list()   → list of candidate video dicts
  │     ├─ Primary:  YouTube Data API (chart=mostPopular, categories 25 & 22)
  │     └─ Fallback: yt-dlp scraping (no API key needed)
  │
  ├─ video_processor.process_video_pipeline()        → final MP4 path
  │     ├─ download_video()          yt-dlp → 720p MP4
  │     ├─ download_captions()       yt-dlp → VTT
  │     ├─ parse_vtt_to_word_segments()
  │     ├─ find_best_clip_start()    most speech-dense 45s window
  │     ├─ clip_video()              ffmpeg
  │     ├─ crop_to_vertical()        ffmpeg → 1080x1920 center crop
  │     ├─ translate_word_segments_to_ukrainian()  Gemini
  │     ├─ generate_hook_text()      Gemini
  │     ├─ create_word_by_word_ass_subtitles()     ASS format
  │     └─ burn_subtitles_and_hook() ffmpeg → final MP4
  │
  ├─ script_generator.generate_youtube_metadata()  → title, description, tags (Ukrainian)
  │
  ├─ youtube_uploader.upload_to_youtube()           → YouTube video ID
  │
  └─ save_used_video()  → appends to used_videos.txt, git commit + push
```

---

## Environment Variables

**Required:**
| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API (translation, metadata, hook text) |
| `YOUTUBE_API_KEY` | YouTube Data API v3 (video search/discovery) |
| `YOUTUBE_CLIENT_ID` | OAuth 2.0 client ID for upload |
| `YOUTUBE_CLIENT_SECRET` | OAuth 2.0 client secret for upload |
| `YOUTUBE_REFRESH_TOKEN` | Long-lived OAuth refresh token for upload |

**Optional:**
| Variable | Purpose |
|---|---|
| `YOUTUBE_COOKIES_FILE` | Path to Netscape cookies file (bypass yt-dlp bot detection) |
| `YOUTUBE_COOKIES` | Base64-encoded cookies (used in GitHub Actions) |

These are stored as GitHub Actions Secrets and injected during workflow runs. For local development, copy `.env.example` to `.env` and fill in values.

---

## Key Conventions

### Module Responsibilities
- **`main.py`** — only orchestration; no business logic
- **`video_finder.py`** — only discovery/filtering; no downloading
- **`video_processor.py`** — only media processing; returns a path to the final MP4
- **`script_generator.py`** — only metadata generation; returns a dict
- **`youtube_uploader.py`** — only upload; returns a video ID string

Keep modules single-responsibility. Do not add YouTube upload logic to the processor, etc.

### Error Handling Strategy
- `video_finder` returns a **list** of candidates (up to 5); `main.py` iterates through them
- If `process_video_pipeline()` fails for a candidate, `main.py` tries the next one
- If all candidates fail, the pipeline logs the error and exits non-zero
- `script_generator` has a `_fallback_metadata()` for when Gemini is unavailable
- No silent failures — always log the exception before continuing

### Duplicate Prevention
- `used_videos.txt` stores one video ID per line
- Read at startup in `video_finder._load_used_videos()`
- After successful upload, the ID is appended and committed via `save_used_video()`
- Do not remove or restructure this file; the bot depends on its line-by-line format

### Video Specs (do not change without updating ffmpeg commands)
- Output resolution: **1080x1920** (9:16 vertical)
- Clip duration: **45–50 seconds**
- Format: **MP4** (H.264 video, AAC audio)
- Input: up to **720p** (yt-dlp format selector: `best[height<=720][ext=mp4]`)

### Subtitle Format (ASS)
- Font: **DejaVu Sans Bold** (required for Cyrillic; installed via `fonts-dejavu` in CI)
- Size: 56pt (inactive words), 66pt (active word)
- Color: Yellow (`&H00FFFF00`) with black border
- Animation: word-by-word, each word highlighted exactly when spoken
- Alignment: bottom-center (ASS alignment 2)

### Gemini Model
- Current model: **`gemini-2.0-flash-lite`** (free tier)
- Used in both `video_processor.py` and `script_generator.py`
- If switching models, update both files

### YouTube Upload Settings
- Category: **25** (News & Politics)
- Privacy: **public**
- Language tag: **`uk`** (Ukrainian)
- Auto-appended hashtags: `#Shorts #Новини #Ukraine #BreakingNews`
- Max title length: 100 chars (enforced before upload)
- Max tags: 30 items (enforced before upload)

---

## Development Workflow

### Local Testing
```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt-get install ffmpeg fonts-dejavu-core fonts-dejavu

# Install Python dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with real credentials

# Run the full pipeline
python main.py
```

### There are no automated tests. Manual verification steps:
1. Run `python main.py` locally with real credentials
2. Check the generated MP4 in the temp directory before upload
3. Trigger the GitHub Actions workflow manually via `workflow_dispatch`
4. Verify the video appears on the target YouTube channel

### Modifying the Pipeline
- To change clip duration: modify `clip_duration` parameter in `video_processor.find_best_clip_start()` and the `clip_video()` call
- To change search filters (view count, duration): edit `_is_good_duration()` and view count checks in `video_finder.py`
- To change subtitle style: edit `create_word_by_word_ass_subtitles()` in `video_processor.py`
- To change metadata style: edit the system prompt in `script_generator.generate_youtube_metadata()`

---

## GitHub Actions Workflow

File: `.github/workflows/daily.yml`

- **Trigger:** Daily cron `0 7 * * *` + manual `workflow_dispatch`
- **Runner:** `ubuntu-latest`, timeout 25 minutes
- **System packages installed:** `ffmpeg`, `fonts-dejavu-core`, `fonts-dejavu`, `fonts-liberation`
- **Python version:** 3.11
- **Secrets required:** `GEMINI_API_KEY`, `YOUTUBE_API_KEY`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`
- **Optional secret:** `YOUTUBE_COOKIES` (base64-encoded Netscape cookies file)
- **Git config:** `bot@github.com` / `YouTube News Bot` (for committing `used_videos.txt`)

The workflow pushes changes back to the repository after a successful run. This requires the Actions token to have write permissions.

---

## Common Issues & Solutions

| Issue | Cause | Fix |
|---|---|---|
| `HTTP Error 429` from yt-dlp | YouTube bot detection | Add/rotate `YOUTUBE_COOKIES` secret |
| `No captions found` | Video has no auto-captions | The pipeline skips that candidate and tries the next |
| `Gemini API error` | Quota exceeded or model unavailable | `script_generator` falls back to template metadata automatically |
| `OAuth token expired` | Refresh token revoked | Re-run the OAuth flow and update `YOUTUBE_REFRESH_TOKEN` secret |
| `Font not found` for subtitles | DejaVu fonts not installed | `sudo apt-get install fonts-dejavu` |
| Pipeline skips all candidates | All 5 candidates already in `used_videos.txt` or all fail | Clear/trim `used_videos.txt` or investigate logs |

---

## Files to Ignore

Do not modify or commit:
- `.env` (not tracked; use `.env.example` as template)
- `*.mp4`, `*.mp3`, `*.png` (temporary media files)
- `tmp/`, `temp/`, `output/` directories
- `youtube_credentials.json`, `client_secrets.json`
- `__pycache__/`, `*.pyc`

The only data file the bot writes to and commits is **`used_videos.txt`**.
