"""
video_processor.py — Download, clip, and process videos from YouTube
Handles: video download, caption extraction, clipping, vertical cropping, subtitle burning
"""

import os
import re
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional, List
import tempfile

import yt_dlp
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


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
            "write_auto_subs": True,  # Download auto-generated captions
            "skip_download": True,    # Don't re-download the video
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


def extract_caption_text(caption_path: Path) -> str:
    """
    Extract plain text from VTT caption file.

    Args:
        caption_path: Path to VTT file

    Returns:
        Extracted caption text
    """
    try:
        content = caption_path.read_text(encoding="utf-8")

        # Remove VTT header and timing info
        lines = content.split("\n")
        text_lines = []
        for line in lines:
            # Skip headers, timing, and blank lines
            if line.startswith("WEBVTT") or "-->" in line or not line.strip():
                continue
            text_lines.append(line.strip())

        return " ".join(text_lines)

    except Exception as e:
        logger.error(f"Error extracting caption text: {e}")
        return ""


def translate_captions_to_ukrainian(caption_text: str) -> str:
    """
    Translate caption text to Ukrainian using Gemini.

    Args:
        caption_text: Original caption text (likely English)

    Returns:
        Translated text in Ukrainian
    """
    if not caption_text.strip():
        logger.warning("Empty caption text to translate")
        return ""

    try:
        prompt = f"""Translate the following caption/subtitle text to Ukrainian.
Keep it concise and natural for spoken subtitles.
Return ONLY the translated text, no explanations.

Original text:
{caption_text}"""

        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=2000,
            )
        )

        translated = response.text.strip()
        logger.info(f"Translated captions to Ukrainian ({len(translated)} chars)")
        return translated

    except Exception as e:
        logger.error(f"Error translating captions: {e}")
        return caption_text  # Fallback to original


def clip_video(video_path: Path, output_path: Path, duration: int = 45) -> bool:
    """
    Clip first N seconds of video using ffmpeg.

    Args:
        video_path: Input MP4 file
        output_path: Output MP4 file
        duration: Clip duration in seconds (default 45)

    Returns:
        True if successful
    """
    try:
        logger.info(f"Clipping video to {duration} seconds...")
        cmd = [
            "ffmpeg",
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

        # FFmpeg filter: crop=ih*9/16:ih (width = height * 9/16, height stays same)
        # Then scale to standard YouTube Shorts size
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


def burn_subtitles_ass(
    video_path: Path,
    subtitle_text: str,
    output_path: Path,
) -> bool:
    """
    Burn Ukrainian subtitles (ASS format) onto video.
    Uses large yellow text with black border for mobile readability.

    Args:
        video_path: Input MP4 file
        subtitle_text: Ukrainian subtitle text
        output_path: Output MP4 with burnt subtitles

    Returns:
        True if successful
    """
    try:
        logger.info("Creating ASS subtitle file...")

        # Create temporary ASS subtitle file
        ass_file = Path(tempfile.gettempdir()) / "subtitles.ass"

        # ASS format with styling for readability
        ass_content = f"""[Script Info]
Title: YouTube Shorts Subtitle
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans Bold,56,&H00FFFF00,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,2,2,10,10,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:01:00.00,Default,,0,0,0,,{subtitle_text}
"""

        ass_file.write_text(ass_content, encoding="utf-8")
        logger.info(f"ASS file created: {ass_file}")

        # Burn subtitles onto video
        logger.info("Burning subtitles onto video...")
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", f"ass={str(ass_file)}",
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

        logger.info(f"Video with subtitles saved: {output_path}")
        ass_file.unlink()  # Clean up temp file
        return True

    except Exception as e:
        logger.error(f"Error burning subtitles: {e}")
        return False


def process_video_pipeline(
    video_id: str,
    output_dir: Path,
) -> Optional[Path]:
    """
    Complete pipeline: download → clip → crop → add subtitles

    Args:
        video_id: YouTube video ID
        output_dir: Working directory

    Returns:
        Path to final processed video, or None if failed
    """
    try:
        # Step 1: Download video
        video_path = download_video(video_id, output_dir)
        if not video_path:
            return None

        # Step 2: Try to get captions
        caption_path = download_captions(video_id, output_dir)
        caption_text = ""
        if caption_path:
            caption_text = extract_caption_text(caption_path)

        # Step 3: Translate captions if available
        ukrainian_text = ""
        if caption_text:
            ukrainian_text = translate_captions_to_ukrainian(caption_text)

        # Step 4: Clip to 45 seconds
        clipped_path = output_dir / "clipped.mp4"
        if not clip_video(video_path, clipped_path, duration=45):
            logger.warning("Failed to clip video, using original")
            clipped_path = video_path

        # Step 5: Crop to vertical
        vertical_path = output_dir / "vertical.mp4"
        if not crop_to_vertical(clipped_path, vertical_path):
            logger.error("Failed to crop to vertical")
            return None

        # Step 6: Burn subtitles if available
        final_path = output_dir / "final.mp4"
        if ukrainian_text:
            if not burn_subtitles_ass(vertical_path, ukrainian_text, final_path):
                logger.warning("Failed to burn subtitles, using video without")
                final_path = vertical_path
        else:
            logger.info("No captions available, using video without subtitles")
            final_path = vertical_path

        logger.info(f"Video processing complete: {final_path}")
        return final_path

    except Exception as e:
        logger.error(f"Error in video pipeline: {e}")
        return None
