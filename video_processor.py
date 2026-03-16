"""
video_processor.py — Download, clip, and process videos from YouTube
Handles: video download, caption extraction with word-level timing,
clipping, vertical cropping, word-by-word subtitle generation, and hook text overlay
"""

import os
import re
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import tempfile

import yt_dlp
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

try:
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
except Exception as e:
    logger.warning(f"Failed to initialize Gemini client: {e}")
    client = None

# Font path for Ubuntu/GitHub Actions
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def download_video(video_id: str, output_dir: Path) -> Optional[Path]:
    """
    Download video from YouTube using yt-dlp.

    Args:
        video_id: YouTube video ID
        output_dir: Directory to save video

    Returns:
        Path to downloaded MP4 file, or None if failed
    """
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        output_template = str(output_dir / "video.%(ext)s")

        ydl_opts = {
            "format": "best[height<=720][ext=mp4]",
            "outtmpl": output_template,
            "quiet": False,
            "no_warnings": False,
            "socket_timeout": 30,
        }

        logger.info(f"Downloading video {video_id}...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        video_path = Path(output_dir) / f"video.{info['ext']}"
        if video_path.exists():
            logger.info(f"Downloaded video: {video_path} ({video_path.stat().st_size / 1024 / 1024:.1f} MB)")
            return video_path
        else:
            logger.error(f"Video file not found after download")
            return None

    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        return None


def download_captions(video_id: str, output_dir: Path) -> Optional[Path]:
    """
    Download auto-generated captions from YouTube using yt-dlp.

    Args:
        video_id: YouTube video ID
        output_dir: Directory to save captions

    Returns:
        Path to caption file (VTT format), or None if not available
    """
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        caption_template = str(output_dir / "captions.%(ext)s")

        ydl_opts = {
            "write_auto_subs": True,
            "skip_download": True,
            "skip_unavailable_fragments": True,
            "outtmpl": caption_template,
            "quiet": False,
            "no_warnings": False,
            "subtitlesformat": "vtt",
        }

        logger.info(f"Downloading captions for {video_id}...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)

        # Find the caption file (yt-dlp adds language code)
        caption_files = list(Path(output_dir).glob("captions*"))
        if caption_files:
            caption_path = caption_files[0]
            logger.info(f"Downloaded captions: {caption_path}")
            return caption_path
        else:
            logger.warning("No caption file found after download")
            return None

    except Exception as e:
        logger.warning(f"Could not download captions: {e}")
        return None


def parse_vtt_to_word_segments(caption_path: Path) -> List[Dict]:
    """
    Parse VTT caption file to extract individual words with timestamps.
    Returns list of dicts: {word, start_time_ms, end_time_ms}

    Args:
        caption_path: Path to VTT file

    Returns:
        List of word segments with timing
    """
    try:
        content = caption_path.read_text(encoding="utf-8")
        lines = content.split("\n")

        word_segments = []
        current_start = None
        current_end = None
        current_text = []

        for line in lines:
            # Match timing line: HH:MM:SS.mmm --> HH:MM:SS.mmm
            timing_match = re.match(r"(\d{1,2}):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})\.(\d{3})", line)

            if timing_match:
                # Save previous segment if exists
                if current_text and current_start is not None:
                    text = " ".join(current_text).strip()
                    if text:
                        # Split into words
                        words = text.split()
                        # Distribute time evenly across words
                        time_per_word = (current_end - current_start) / max(len(words), 1)
                        for i, word in enumerate(words):
                            word_start = current_start + (i * time_per_word)
                            word_end = current_start + ((i + 1) * time_per_word)
                            word_segments.append({
                                "word": word,
                                "start_ms": int(word_start),
                                "end_ms": int(word_end),
                            })

                # Parse new timing
                h1, m1, s1, ms1 = int(timing_match.group(1)), int(timing_match.group(2)), int(timing_match.group(3)), int(timing_match.group(4))
                h2, m2, s2, ms2 = int(timing_match.group(5)), int(timing_match.group(6)), int(timing_match.group(7)), int(timing_match.group(8))

                current_start = h1 * 3600000 + m1 * 60000 + s1 * 1000 + ms1
                current_end = h2 * 3600000 + m2 * 60000 + s2 * 1000 + ms2
                current_text = []

            elif line.strip() and not line.startswith("WEBVTT"):
                # This is caption text (not header, not timing)
                current_text.append(line.strip())

        # Don't forget the last segment
        if current_text and current_start is not None:
            text = " ".join(current_text).strip()
            if text:
                words = text.split()
                time_per_word = (current_end - current_start) / max(len(words), 1)
                for i, word in enumerate(words):
                    word_start = current_start + (i * time_per_word)
                    word_end = current_start + ((i + 1) * time_per_word)
                    word_segments.append({
                        "word": word,
                        "start_ms": int(word_start),
                        "end_ms": int(word_end),
                    })

        logger.info(f"Parsed {len(word_segments)} word segments from VTT")
        return word_segments

    except Exception as e:
        logger.error(f"Error parsing VTT: {e}")
        return []


def translate_word_segments_to_ukrainian(word_segments: List[Dict]) -> List[Dict]:
    """
    Translate word segments to Ukrainian using Gemini.
    Preserves timing information.

    Args:
        word_segments: List of {word, start_ms, end_ms}

    Returns:
        List of {word, start_ms, end_ms} with translated words
    """
    if not word_segments:
        logger.warning("No word segments to translate")
        return []

    if not client:
        logger.warning("Gemini client unavailable, using original text")
        return word_segments

    try:
        # Join words for translation
        original_text = " ".join(seg["word"] for seg in word_segments)

        prompt = f"""Translate the following English subtitle text to Ukrainian.
Keep it natural and concise for spoken subtitles.
Return ONLY the translated text, word-by-word, separated by spaces. No explanations.

Original: {original_text}
Translation:"""

        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=1000,
            )
        )

        translated_text = response.text.strip()
        translated_words = translated_text.split()

        logger.info(f"Translated {len(word_segments)} words to Ukrainian")

        # Map translated words back to original segments
        # If lengths don't match, fall back to original
        if len(translated_words) != len(word_segments):
            logger.warning(f"Translation word count mismatch ({len(translated_words)} vs {len(word_segments)}), using original")
            return word_segments

        result = []
        for i, seg in enumerate(word_segments):
            result.append({
                "word": translated_words[i],
                "start_ms": seg["start_ms"],
                "end_ms": seg["end_ms"],
            })

        return result

    except Exception as e:
        logger.error(f"Error translating word segments: {e}")
        return word_segments


def generate_hook_text(video_title: str, video_description: str) -> str:
    """
    Generate a short compelling Ukrainian hook text (5-8 words).

    Args:
        video_title: Original video title
        video_description: Original video description

    Returns:
        Ukrainian hook text (5-8 words), or fallback if error
    """
    if not client:
        logger.warning("Gemini client unavailable, using fallback hook")
        return "ДИВИСЬ СКОРШЕ! ⚡"

    try:
        prompt = f"""Generate a SHORT, compelling Ukrainian hook/headline (5-8 words max)
that would make someone stop scrolling on YouTube Shorts.
Use ALL CAPS for impact. Can include emoji.
Return ONLY the hook text, nothing else.

Video title: {video_title}
Description excerpt: {video_description[:100]}"""

        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=50,
            )
        )

        hook = response.text.strip()
        if hook:
            logger.info(f"Generated hook: {hook}")
            return hook

    except Exception as e:
        logger.error(f"Error generating hook text: {e}")

    return "ДИВИСЬ СКОРШЕ! ⚡"


def create_word_by_word_ass_subtitles(
    word_segments: List[Dict],
    output_path: Path,
) -> bool:
    """
    Create ASS subtitle file with word-by-word animation.
    Each word appears one at a time, highlighted in yellow, with styling.

    Args:
        word_segments: List of {word, start_ms, end_ms}
        output_path: Path to output ASS file

    Returns:
        True if successful
    """
    try:
        logger.info("Creating word-by-word ASS subtitles...")

        ass_header = """[Script Info]
Title: YouTube Shorts Word-by-Word
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CurrentWord,DejaVu Sans Bold,66,&H00FFFF00,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,2,2,10,10,100,1
Style: OtherWord,DejaVu Sans Bold,52,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,3,2,2,10,10,100,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        dialogue_lines = []

        # For each word, create a dialogue line
        for i, seg in enumerate(word_segments):
            start_ms = seg["start_ms"]
            end_ms = seg["end_ms"]

            # Convert ms to ASS timestamp format (H:MM:SS.cc)
            def ms_to_ass(ms):
                total_sec = ms / 1000
                h = int(total_sec // 3600)
                m = int((total_sec % 3600) // 60)
                s = total_sec % 60
                return f"{h}:{m:02d}:{s:05.2f}"

            start_time = ms_to_ass(start_ms)
            end_time = ms_to_ass(end_ms)

            # Build text with current word highlighted
            text_parts = []
            for j, other_seg in enumerate(word_segments):
                if i == j:
                    # Current word: yellow and larger
                    text_parts.append(f"{{\\c&HFF00FF&\\fs66}}{other_seg['word']}{{\\r}}")
                else:
                    # Other words: white and smaller (or skip for now to focus current)
                    pass

            text = "".join(text_parts)

            # Create dialogue line
            dialogue = f"Dialogue: 0,{start_time},{end_time},CurrentWord,,0,0,0,,{text}\n"
            dialogue_lines.append(dialogue)

        # Write ASS file
        ass_content = ass_header + "".join(dialogue_lines)
        output_path.write_text(ass_content, encoding="utf-8")
        logger.info(f"ASS subtitle file created: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Error creating ASS subtitles: {e}")
        return False


def create_hook_text_overlay(
    hook_text: str,
) -> Path:
    """
    Create a drawtext filter string for ffmpeg to overlay hook text.
    Text appears at top, yellow with black border, for first 5 seconds.

    Args:
        hook_text: Ukrainian hook text

    Returns:
        Path to temporary file containing ffmpeg filter (or empty if error)
    """
    try:
        # Escape special characters for ffmpeg drawtext filter
        escaped_text = hook_text.replace("'", "\\'").replace('"', '\\"')

        # Create filter for drawtext overlay
        # Text: at top, yellow, bold, large, black border
        # Duration: first 5 seconds only
        filter_str = f"""drawtext=fontfile='{FONT_PATH}':text='{escaped_text}':fontsize=48:fontcolor=yellow:x=(w-text_w)/2:y=50:borderw=3:bordercolor=black:enable='lt(t\\,5)'"""

        logger.info(f"Hook text overlay filter created")
        return filter_str

    except Exception as e:
        logger.error(f"Error creating hook text overlay: {e}")
        return ""


def find_best_clip_start(word_segments: List[Dict], video_duration_s: int, clip_duration: int = 45) -> int:
    """
    Find the best start time (in seconds) for a 45-second clip.
    Strategy: find the most speech-dense 45-second window in the first half of the video,
    but never start within the first 45 seconds (skip intro).

    Args:
        word_segments: List of {word, start_ms, end_ms} from VTT
        video_duration_s: Total video duration in seconds
        clip_duration: Desired clip length in seconds

    Returns:
        Best start time in seconds (minimum 45s, maximum 1/2 of video)
    """
    if not word_segments:
        # No captions — skip 60s of intro for news, 90s for podcasts
        default_skip = min(90, max(45, video_duration_s // 6))
        logger.info(f"No captions for clip start detection, skipping {default_skip}s")
        return default_skip

    clip_ms = clip_duration * 1000
    min_start_ms = 45_000   # never clip within first 45s
    max_start_ms = (video_duration_s * 1000) // 2  # search only first half

    if max_start_ms <= min_start_ms:
        return 45

    # Slide a window of clip_ms and count words that fall within it
    best_start_ms = min_start_ms
    best_count = 0

    # Check every 5-second step for efficiency
    step_ms = 5_000
    t = min_start_ms
    while t <= max_start_ms:
        window_end = t + clip_ms
        count = sum(
            1 for seg in word_segments
            if t <= seg["start_ms"] < window_end
        )
        if count > best_count:
            best_count = count
            best_start_ms = t
        t += step_ms

    best_start_s = best_start_ms // 1000
    logger.info(f"Best clip start: {best_start_s}s ({best_count} words in window)")
    return best_start_s


def clip_video(video_path: Path, output_path: Path, start_sec: int = 0, duration: int = 45) -> bool:
    """
    Clip N seconds from a given start position using ffmpeg.

    Args:
        video_path: Input MP4 file
        output_path: Output MP4 file
        start_sec: Start position in seconds (default 0)
        duration: Clip duration in seconds (default 45)

    Returns:
        True if successful
    """
    try:
        logger.info(f"Clipping video: start={start_sec}s, duration={duration}s")
        cmd = [
            "ffmpeg",
            "-ss", str(start_sec),
            "-i", str(video_path),
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-y",
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.error(f"ffmpeg error: {result.stderr}")
            return False

        logger.info(f"Clipped video saved: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Error clipping video: {e}")
        return False


def crop_to_vertical(video_path: Path, output_path: Path) -> bool:
    """
    Crop video to vertical 9:16 aspect ratio (center crop).
    Aspect ratio: 1080x1920 (standard YouTube Shorts)

    Args:
        video_path: Input MP4 file
        output_path: Output MP4 file

    Returns:
        True if successful
    """
    try:
        logger.info("Cropping to vertical 9:16 aspect ratio...")

        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", "crop=ih*9/16:ih,scale=1080:1920",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-y",
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.error(f"ffmpeg error: {result.stderr}")
            return False

        logger.info(f"Vertical video saved: {output_path} (1080x1920)")
        return True

    except Exception as e:
        logger.error(f"Error cropping video: {e}")
        return False


def burn_subtitles_and_hook(
    video_path: Path,
    ass_file: Path,
    hook_text: str,
    output_path: Path,
) -> bool:
    """
    Burn word-by-word subtitles (ASS) and hook text overlay onto video using ffmpeg.

    Args:
        video_path: Input MP4 file
        ass_file: Path to ASS subtitle file
        hook_text: Ukrainian hook text for overlay
        output_path: Output MP4 with burnt subtitles and overlay

    Returns:
        True if successful
    """
    try:
        logger.info("Burning subtitles and hook text onto video...")

        # Escape hook text for drawtext filter
        escaped_hook = hook_text.replace("'", "\\'").replace('"', '\\"').replace(":", "\\:")

        # Build filter chain: ASS subtitles + hook text overlay
        # Hook text appears for first 5 seconds, centered at top, yellow with black border
        filter_str = f"""[0:v]ass='{str(ass_file)}'[subbed];[subbed]drawtext=fontfile='{FONT_PATH}':text='{escaped_hook}':fontsize=48:fontcolor=yellow:x=(w-text_w)/2:y=50:borderw=3:bordercolor=black:enable='lt(t,5)'[final]"""

        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-filter_complex", filter_str,
            "-map", "[final]",
            "-map", "0:a",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-y",
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            logger.error(f"ffmpeg error: {result.stderr}")
            return False

        logger.info(f"Video with subtitles and hook saved: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Error burning subtitles and hook: {e}")
        return False


def process_video_pipeline(
    video_id: str,
    video_title: str,
    video_description: str,
    output_dir: Path,
) -> Optional[Path]:
    """
    Complete pipeline: download → clip → crop → add word-by-word subtitles → add hook overlay

    Args:
        video_id: YouTube video ID
        video_title: Video title (for hook generation)
        video_description: Video description (for hook generation)
        output_dir: Working directory

    Returns:
        Path to final processed video, or None if failed
    """
    try:
        # Step 1: Download video
        video_path = download_video(video_id, output_dir)
        if not video_path:
            return None

        # Step 2: Download captions early — needed to find best clip moment
        caption_path = download_captions(video_id, output_dir)
        all_segments = []
        if caption_path:
            all_segments = parse_vtt_to_word_segments(caption_path)

        # Step 3: Find the best 45-second window (most speech-dense, skip intro)
        import subprocess as _sp
        # Get video duration via ffprobe
        try:
            probe = _sp.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
                capture_output=True, text=True, timeout=30,
            )
            video_duration_s = int(float(probe.stdout.strip()))
        except Exception:
            video_duration_s = 600  # fallback 10 min

        clip_start = find_best_clip_start(all_segments, video_duration_s, clip_duration=50)

        # Step 4: Clip to 50 seconds from the best moment
        clipped_path = output_dir / "clipped.mp4"
        if not clip_video(video_path, clipped_path, start_sec=clip_start, duration=50):
            logger.warning("Failed to clip video, using original")
            clipped_path = video_path

        # Step 5: Crop to vertical 9:16
        vertical_path = output_dir / "vertical.mp4"
        if not crop_to_vertical(clipped_path, vertical_path):
            logger.error("Failed to crop to vertical")
            return None

        # Step 6: Filter captions to only the clipped window, then translate
        clip_start_ms = clip_start * 1000
        clip_end_ms   = clip_start_ms + 50_000
        window_segments = [
            {"word": s["word"],
             "start_ms": s["start_ms"] - clip_start_ms,
             "end_ms":   s["end_ms"]   - clip_start_ms}
            for s in all_segments
            if clip_start_ms <= s["start_ms"] < clip_end_ms
        ]

        if window_segments:
            window_segments = translate_word_segments_to_ukrainian(window_segments)

        # Step 7: Generate hook text
        hook_text = generate_hook_text(video_title, video_description)

        # Step 8: Create word-by-word ASS subtitles
        ass_file = output_dir / "subtitles.ass"
        subtitles_ok = False
        if window_segments:
            subtitles_ok = create_word_by_word_ass_subtitles(window_segments, ass_file)

        # Step 9: Burn subtitles + hook overlay onto final video
        final_path = output_dir / "final.mp4"
        if subtitles_ok and window_segments:
            if not burn_subtitles_and_hook(vertical_path, ass_file, hook_text, final_path):
                logger.warning("Subtitle burn failed, using video without subtitles")
                final_path = vertical_path
        else:
            logger.info("No subtitles available, using video without overlays")
            final_path = vertical_path

        logger.info(f"✅ Video processing complete: {final_path}")
        return final_path

    except Exception as e:
        logger.error(f"Error in video pipeline: {e}")
        return None
