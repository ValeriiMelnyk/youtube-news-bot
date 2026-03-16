# YouTube Shorts News Bot - Quick Start Guide

## What This Bot Does

Automatically finds trending news videos on YouTube, clips them, adds Ukrainian subtitles, and publishes them as YouTube Shorts.

## Setup

### 1. Prerequisites
- GitHub repository with Actions enabled
- Python 3.11+
- YouTube Data API credentials (OAuth)
- Google Gemini API key

### 2. Get YouTube OAuth Credentials

Run the setup script (if available) or manually:

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project
3. Enable "YouTube Data API v3"
4. Create OAuth 2.0 credentials (Desktop app)
5. Run `python setup_youtube_auth.py` to get refresh token
6. Save: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`

### 3. Get Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com)
2. Create API key
3. Copy: `GEMINI_API_KEY`

### 4. Add GitHub Secrets

Go to your repo → Settings → Secrets and variables → Actions

Add these secrets:
```
GEMINI_API_KEY
YOUTUBE_CLIENT_ID
YOUTUBE_CLIENT_SECRET
YOUTUBE_REFRESH_TOKEN
```

### 5. Commit and Push

```bash
git add -A
git commit -m "YouTube Shorts bot rewrite"
git push origin main
```

The workflow will automatically run at 07:00 UTC daily, or click "Run workflow" button.

---

## How It Works

### Step-by-Step

1. **Find Video** (video_finder.py)
   - Search YouTube for trending news videos
   - Filter: Last 24h, 3-15 min duration, >10k views, from UA region
   - Check `used_videos.txt` to avoid repeats

2. **Process Video** (video_processor.py)
   - Download video (720p)
   - Download captions (if available)
   - Translate to Ukrainian (via Gemini)
   - Clip to 45 seconds
   - Crop to 9:16 vertical (1080x1920)
   - Burn Ukrainian subtitles onto video

3. **Generate Metadata** (script_generator.py)
   - Create catchy Ukrainian title (<60 chars)
   - Write description with credit to original
   - Pick 6-8 tags (mix Ukrainian + English)

4. **Upload** (youtube_uploader.py)
   - Upload to YouTube as Short
   - Add #Shorts hashtag
   - Set category: News & Politics

5. **Track** (main.py)
   - Save video ID to `used_videos.txt`
   - Git commit and push

---

## Monitoring

### GitHub Actions Dashboard
Go to your repo → Actions → Daily YouTube Shorts Bot

**Status Indicators:**
- ✅ Green = Video published
- ❌ Red = Error (check logs)

### View Logs
Click on the workflow run to see detailed logs

### Check Published Videos
```bash
cat used_videos.txt
```

---

## Troubleshooting

### "Missing required env vars"
- Check GitHub Secrets are set correctly
- Verify secret names (case-sensitive)

### "Could not find suitable trending video"
- YouTube API might be rate-limited
- Try again in a few hours
- Check API quota in Google Cloud Console

### "Failed to download video"
- Video might be age-restricted or deleted
- yt-dlp might need update: `pip install --upgrade yt-dlp`

### "Gemini translation failed"
- Check GEMINI_API_KEY is correct
- Verify API quota

### "YouTube upload failed"
- Check YOUTUBE_REFRESH_TOKEN is still valid
- OAuth tokens expire after ~6 months without use
- Re-run setup_youtube_auth.py to get new token

### "Git push failed"
- Workflow still succeeds (video uploaded already)
- Usually happens if used_videos.txt has merge conflicts
- Manual fix: `git pull`, resolve conflict, `git push`

---

## Customization

### Change Search Criteria
Edit `video_finder.py`:
```python
# Line ~70
q="news breaking politics world"  # Change search query
order="viewCount"                 # Try "date" for recent
```

### Change Clip Duration
Edit `video_processor.py`:
```python
# Line ~180
clip_video(video_path, clipped_path, duration=45)  # Change 45 to desired seconds
```

### Change Subtitle Style
Edit `video_processor.py` - `burn_subtitles_ass()` function:
```python
Style: Default,DejaVu Sans Bold,56,&H00FFFF00,&H000000FF,&H00000000
                                   ^Yellow     ^Black outline
```

Color codes (BGR format):
- `&H00FFFF00` = Yellow
- `&H000000FF` = Red
- `&H0000FF00` = Green
- `&H00FFFFFF` = White

### Change Language
Edit `script_generator.py`:
- Change `model="gemini-2.0-flash-lite"` target language in prompts

---

## File Reference

| File | Purpose |
|------|---------|
| `main.py` | Entry point, orchestrates pipeline |
| `video_finder.py` | Find trending videos on YouTube |
| `video_processor.py` | Download, clip, crop, add subtitles |
| `script_generator.py` | Generate Ukrainian metadata |
| `youtube_uploader.py` | Upload to YouTube (read-only) |
| `used_videos.txt` | Track published video IDs |
| `requirements.txt` | Python dependencies |
| `.github/workflows/daily.yml` | GitHub Actions schedule |

---

## Performance

| Operation | Time |
|-----------|------|
| Find video | ~30 sec |
| Download | 2-5 min |
| Process | 3-4 min |
| Upload | 2-5 min |
| **Total** | **~10-15 min** |

---

## Logs Example

```
2026-03-16 10:00:05 [INFO] 🔍 Step 1/5 — Finding trending news video...
2026-03-16 10:00:10 [INFO] Searching for trending news videos...
2026-03-16 10:00:15 [INFO] Found suitable video: Breaking news from Ukraine...
2026-03-16 10:00:20 [INFO] 📥 Step 2/5 — Downloading and processing video...
2026-03-16 10:00:25 [INFO] Downloading video {video_id}...
2026-03-16 10:05:30 [INFO] Processed video ready (85.3 MB)
2026-03-16 10:05:35 [INFO] ✍️  Step 3/5 — Generating Ukrainian metadata...
2026-03-16 10:05:40 [INFO] Generated metadata: Важливі новини дня
2026-03-16 10:05:45 [INFO] 🚀 Step 4/5 — Uploading to YouTube...
2026-03-16 10:11:50 [INFO] ✅ Video uploaded: https://youtube.com/shorts/dQw4w9WgXcQ
2026-03-16 10:12:00 [INFO] 💾 Step 5/5 — Saving used video ID...
2026-03-16 10:12:05 [INFO] ============================================================
2026-03-16 10:12:05 [INFO] ✅ Video successfully published!
2026-03-16 10:12:05 [INFO] 🔗 https://youtube.com/shorts/dQw4w9WgXcQ
```

---

## FAQ

**Q: Can I publish multiple videos per day?**
A: Currently one per scheduled run. Edit `.github/workflows/daily.yml` to add more cron schedules.

**Q: Do I need PEXELS_API_KEY?**
A: No, that's from the old version. Removed in rewrite.

**Q: How do I stop the bot?**
A: Disable workflow: Actions → Daily YouTube Shorts Bot → three dots → Disable.

**Q: Will it republish the same video?**
A: No, `used_videos.txt` prevents that.

**Q: Can I test locally?**
A: Yes! Set env vars and run `python main.py` from the bot directory.

**Q: What if the video has no captions?**
A: It publishes without subtitles (video-only). Future version could add TTS voiceover.

---

Last Updated: 2026-03-16
