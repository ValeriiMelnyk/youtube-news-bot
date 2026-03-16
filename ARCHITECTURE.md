# YouTube Shorts News Bot - Architecture

## Overview

This bot autonomously finds trending news videos on YouTube, clips them, translates captions to Ukrainian, and uploads them as YouTube Shorts.

## Pipeline

```
┌─────────────────────┐
│  video_finder.py    │  Find trending news videos (YouTube Data API)
└──────────┬──────────┘
           │
           ▼
┌──────────────────────────┐
│  video_processor.py      │  Download → Clip → Crop → Add Subtitles
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  script_generator.py     │  Generate Ukrainian title, description, tags (Gemini)
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  youtube_uploader.py     │  Upload to YouTube Shorts (OAuth)
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  main.py                 │  Track used_videos.txt, git commit
└──────────────────────────┘
```

## Module Descriptions

### 1. `video_finder.py`
**Purpose:** Discover trending news videos on YouTube

**Key Functions:**
- `find_trending_news_video()` - Search YouTube for news videos
  - Uses YouTube Data API with OAuth
  - Filters by: region (UA), recency (last 24h), duration (3-15 min), view count (>10k)
  - Checks `used_videos.txt` to avoid duplicates
  - Returns: video_id, title, description, channel_name, duration, view_count

**Dependencies:** google-api-python-client, google-auth, google-auth-oauthlib

---

### 2. `video_processor.py`
**Purpose:** Download, clip, crop, and add Ukrainian subtitles

**Key Functions:**
- `download_video(video_id, output_dir)` - Download from YouTube (720p MP4)
- `download_captions(video_id, output_dir)` - Download auto-generated captions (VTT)
- `extract_caption_text(caption_path)` - Extract plain text from VTT
- `translate_captions_to_ukrainian(caption_text)` - Translate via Gemini
- `clip_video(video_path, output_path, duration=45)` - Extract first N seconds
- `crop_to_vertical(video_path, output_path)` - Center crop to 9:16 (1080x1920)
- `burn_subtitles_ass(video_path, subtitle_text, output_path)` - Burn Ukrainian subtitles (ASS format)
- `process_video_pipeline(video_id, output_dir)` - Complete workflow

**Subtitle Styling:**
- Large yellow text (#FFFF00) with black border
- 56pt font (DejaVu Sans Bold)
- Readable on mobile devices

**Dependencies:** yt-dlp, google-genai, subprocess, ffmpeg

---

### 3. `script_generator.py` (Rewritten)
**Purpose:** Generate Ukrainian YouTube metadata

**Key Functions:**
- `generate_youtube_metadata(original_title, original_description, channel_name)`
  - Inputs: Original video metadata
  - Uses Gemini 2.0 Flash to create Ukrainian content
  - Returns: yt_title (60 chars), description (100-130 chars), tags (6-8 items)
  - Always credits original channel

**Fallback:** If Gemini fails, returns basic metadata with original title

**Dependencies:** google-genai

---

### 4. `youtube_uploader.py`
**Status:** UNCHANGED (already working perfectly)

**Key Functions:**
- `upload_to_youtube(video_path, title, description, tags)`
  - Uses OAuth2 refresh token authentication
  - Uploads as YouTube Short (adds #Shorts hashtag automatically)
  - Returns: video_id

**OAuth Flow:**
```
YOUTUBE_REFRESH_TOKEN → Access Token → YouTube API v3 Upload
```

**Dependencies:** google-api-python-client, google-auth, google-auth-oauthlib

---

### 5. `main.py` (Rewritten)
**Purpose:** Orchestrate the complete pipeline

**Steps:**
1. Validate environment variables
2. Find trending video
3. Download and process (clip, crop, subtitles)
4. Generate Ukrainian metadata
5. Upload to YouTube
6. Save video ID to `used_videos.txt` and git commit/push

**Error Handling:** Each step has try-catch with detailed logging

**Dependencies:** All modules above

---

## File Structure

```
/tmp/bot/
├── main.py                           # Entry point
├── video_finder.py                   # YouTube discovery
├── video_processor.py                # Video processing pipeline
├── script_generator.py               # Metadata generation (Gemini)
├── youtube_uploader.py               # Upload to YouTube (unchanged)
├── used_videos.txt                   # Tracker of published videos
├── requirements.txt                  # Python dependencies
├── .github/workflows/daily.yml       # GitHub Actions scheduler
└── ARCHITECTURE.md                   # This file
```

---

## Environment Variables

Required (in GitHub Secrets):

```
GEMINI_API_KEY              # Google Gemini API key
YOUTUBE_CLIENT_ID           # YouTube OAuth client ID
YOUTUBE_CLIENT_SECRET       # YouTube OAuth client secret
YOUTUBE_REFRESH_TOKEN       # YouTube OAuth refresh token (long-lived)
```

---

## Dependencies

### Core
- **google-genai** >= 1.0.0 - Gemini API (translation, metadata)
- **yt-dlp** >= 2024.1.0 - Download videos with captions
- **google-api-python-client** >= 2.130.0 - YouTube API
- **google-auth** >= 2.29.0 - OAuth authentication

### System (installed via GitHub Actions)
- **ffmpeg** - Video processing (clip, crop, subtitle burning)
- **fonts-dejavu** - Cyrillic subtitle font

---

## Key Features

### 1. Duplicate Prevention
- Maintains `used_videos.txt` with published video IDs
- Checks before downloading to save bandwidth
- Auto-syncs to git repo

### 2. Caption Workflow
```
YouTube auto-captions (English)
    ↓
extract_caption_text (plain text)
    ↓
translate_captions_to_ukrainian (Gemini)
    ↓
burn_subtitles_ass (ffmpeg ASS format)
    ↓
Final video with Ukrainian subtitles
```

### 3. Video Specifications
- **Resolution:** 1080x1920 (YouTube Shorts standard)
- **Aspect Ratio:** 9:16 (vertical)
- **Duration:** ~45 seconds (under 60s YouTube Shorts limit)
- **Codec:** H.264 video, AAC audio
- **Format:** MP4

### 4. Subtitle Format
- **File Format:** ASS (Advanced SubStation Alpha)
- **Font:** DejaVu Sans Bold (supports Cyrillic)
- **Size:** 56pt
- **Color:** Yellow (#FFFF00) with black outline
- **Alignment:** Center, bottom area

### 5. GitHub Integration
```
Video published
    ↓
Save video_id to used_videos.txt
    ↓
git commit -m "Add used video: {video_id}"
    ↓
git push origin
```

---

## Error Handling

### Video Finding Fails
→ Raises RuntimeError, workflow stops (no retry)

### Video Download Fails
→ Logs warning, returns None, workflow stops

### Captions Unavailable
→ Logs warning, continues without subtitles (video-only)

### Gemini API Fails
→ Returns fallback metadata (basic title + tags)

### Upload Fails
→ Raises HttpError with details, workflow fails

### Git Push Fails
→ Logs warning but considers workflow successful (upload already done)

---

## GitHub Actions Workflow

**Schedule:** Daily at 07:00 UTC (10:00 Kyiv time)

**Manual Trigger:** Available via workflow_dispatch button

**Steps:**
1. Checkout code
2. Setup Python 3.11
3. Install system packages (ffmpeg, fonts)
4. Install Python dependencies
5. Configure git
6. Run bot (main.py)
7. Push used_videos.txt to repo
8. Report success/failure

**Timeout:** 25 minutes (accounts for video download/upload)

---

## Performance Notes

### Download Speed
- Depends on video size and internet speed
- Max 720p (~50-100 MB for ~5 min video)
- Usually 2-5 minutes per video

### Processing Time
- Clipping: ~30 seconds
- Cropping: ~30 seconds
- Subtitle burning: ~1-2 minutes
- **Total:** ~3-4 minutes per video

### Upload Speed
- YouTube API resumable upload
- Chunks: 5 MB (configurable)
- Usually 2-5 minutes depending on video size

### Total Runtime
- ~10-15 minutes per execution

---

## Limitations & Future Improvements

### Current Limitations
1. No automatic fallback if no captions available (uses video-only)
2. Subtitle translation limited to Ukrainian (hardcoded)
3. No video frame interpolation (uses fast preset)
4. Single video per run (no batching)

### Possible Future Improvements
1. Add multi-language support (configurable target language)
2. Generate Ukrainian voiceover if captions unavailable
3. Detect scene changes for better clipping
4. Add thumbnail generation
5. Support for multiple regions (not just UA)
6. Add Discord/Telegram notifications on success/failure

---

## Testing Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GEMINI_API_KEY="your-key"
export YOUTUBE_CLIENT_ID="your-id"
export YOUTUBE_CLIENT_SECRET="your-secret"
export YOUTUBE_REFRESH_TOKEN="your-token"

# Run the bot
python main.py
```

---

## Security Notes

- YouTube OAuth uses refresh tokens (long-lived, secure)
- API keys stored in GitHub Secrets (encrypted)
- No credentials hardcoded in repository
- Video IDs stored in plain text (public, no privacy risk)
- Git commits use generic "bot@github.com" identity

---

Last Updated: 2026-03-16
