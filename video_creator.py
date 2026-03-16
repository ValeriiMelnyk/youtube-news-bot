"""
video_creator.py — Монтаж YouTube Shorts відео
Формат: 1080x1920 (9:16), вертикальне
Структура: фон з Pexels + темний оверлей + заголовок + факти + аудіо
"""

import os
import random
import logging
import requests
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import moviepy.editor as mpe

logger = logging.getLogger(__name__)

# ─── Константи ───────────────────────────────────────────────
W, H = 1080, 1920          # Розміри відео (вертикальне Shorts)
PADDING = 55               # Відступ від країв
TEXT_W = W - 2 * PADDING   # Доступна ширина для тексту
FPS = 30

# ─── Кольори (RGBA) ──────────────────────────────────────────
COLOR_TITLE = (255, 213, 0, 255)        # Золотисто-жовтий
COLOR_FACTS = (255, 255, 255, 255)      # Білий
COLOR_ACCENT = (220, 40, 40, 255)       # Червоний (брендінг)
COLOR_SHADOW = (0, 0, 0, 200)           # Чорна тінь


def get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    """Завантажити шрифт з підтримкою кирилиці"""
    candidates = [
        # Linux (GitHub Actions, Ubuntu)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold
            else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        # macOS
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    logger.warning(f"Шрифт не знайдено, використовую стандартний (кирилиця може не відображатись)")
    return ImageFont.load_default()


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list:
    """Перенос тексту по ширині"""
    words = text.split()
    lines, current = [], []
    for word in words:
        test = " ".join(current + [word])
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] <= max_w:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines or [text]


def draw_text_with_shadow(draw, pos, text, font, fill, shadow_fill, shadow_offset=3):
    """Намалювати текст із тінню"""
    x, y = pos
    draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow_fill)
    draw.text((x, y), text, font=font, fill=fill)


def create_overlay_image(title: str, key_facts: list, duration: float,
                          tmp_dir: Path) -> mpe.ImageClip:
    """
    Створити PNG-оверлей із заголовком і фактами.
    Повертає moviepy ImageClip.
    """
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── Градієнтний затемнений фон зверху ──────────────────
    gradient_top = Image.new("RGBA", (W, 600), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gradient_top)
    for i in range(600):
        alpha = int(190 * (1 - i / 600))
        gd.rectangle([(0, i), (W, i + 1)], fill=(0, 0, 0, alpha))
    img.alpha_composite(gradient_top, (0, 0))

    # ── Градієнтний затемнений фон знизу ───────────────────
    gradient_bot = Image.new("RGBA", (W, 700), (0, 0, 0, 0))
    gb = ImageDraw.Draw(gradient_bot)
    for i in range(700):
        alpha = int(200 * (1 - i / 700))
        gb.rectangle([(0, 700 - i - 1), (W, 700 - i)], fill=(0, 0, 0, alpha))
    img.alpha_composite(gradient_bot, (0, H - 700))

    draw = ImageDraw.Draw(img)

    # ── ЗАГОЛОВОК (зверху) ─────────────────────────────────
    title_font = get_font(78, bold=True)
    title_lines = wrap_text(title.upper(), title_font, TEXT_W)[:3]

    y = 70
    for line in title_lines:
        draw_text_with_shadow(draw, (PADDING, y), line,
                              title_font, COLOR_TITLE, COLOR_SHADOW)
        bbox = title_font.getbbox(line)
        y += (bbox[3] - bbox[1]) + 12

    # ── РОЗДІЛЮВАЧ ─────────────────────────────────────────
    y += 10
    draw.rectangle([(PADDING, y), (PADDING + 120, y + 4)], fill=COLOR_ACCENT)
    y += 20

    # ── КЛЮЧОВІ ФАКТИ (знизу) ──────────────────────────────
    facts_font = get_font(48, bold=False)
    y_facts = H - 420

    for i, fact in enumerate(key_facts[:3]):
        bullet = f"▶  {fact}"
        fact_lines = wrap_text(bullet, facts_font, TEXT_W)[:2]
        for line in fact_lines:
            draw_text_with_shadow(draw, (PADDING, y_facts), line,
                                  facts_font, COLOR_FACTS, COLOR_SHADOW, shadow_offset=2)
            bbox = facts_font.getbbox(line)
            y_facts += (bbox[3] - bbox[1]) + 10
        y_facts += 14

    # ── БРЕНДИНГ (самий низ) ───────────────────────────────
    brand_font = get_font(38, bold=True)
    brand_text = "🔴  НОВИНИ СЬОГОДНІ"
    draw_text_with_shadow(draw, (PADDING, H - 80), brand_text,
                          brand_font, COLOR_ACCENT, COLOR_SHADOW, shadow_offset=2)

    # ── Збереження та завантаження ─────────────────────────
    overlay_path = tmp_dir / "overlay.png"
    img.save(str(overlay_path), "PNG")

    clip = mpe.ImageClip(str(overlay_path), duration=duration)
    return clip


def download_pexels_video(keywords: str, tmp_dir: Path) -> Path | None:
    """Завантажити фонове відео з Pexels (безкоштовно)"""
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        logger.warning("PEXELS_API_KEY не встановлено — буде використаний кольоровий фон")
        return None

    search_queries = [keywords, "world politics", "breaking news", "global conflict"]

    for query in search_queries:
        try:
            resp = requests.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": api_key},
                params={"query": query, "orientation": "portrait", "per_page": 10},
                timeout=20
            )
            resp.raise_for_status()
            videos = resp.json().get("videos", [])

            if not videos:
                continue

            # Вибираємо випадкове відео з топ-5
            video = random.choice(videos[:5])

            # Шукаємо HD-файл
            video_files = sorted(
                video.get("video_files", []),
                key=lambda f: f.get("width", 0),
                reverse=True
            )
            video_url = None
            for vf in video_files:
                if vf.get("width", 0) >= 720:
                    video_url = vf["link"]
                    break
            if not video_url and video_files:
                video_url = video_files[0]["link"]

            if not video_url:
                continue

            # Завантаження файлу
            video_path = tmp_dir / "background.mp4"
            with requests.get(video_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(video_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        f.write(chunk)

            logger.info(f"Pexels відео завантажено (запит: '{query}')")
            return video_path

        except Exception as e:
            logger.warning(f"Pexels '{query}' не спрацював: {e}")
            continue

    return None


def build_background(bg_path: Path | None, duration: float) -> mpe.VideoClip:
    """Підготувати фоновий відеоклік потрібного формату"""

    if bg_path and bg_path.exists():
        try:
            clip = mpe.VideoFileClip(str(bg_path), audio=False)

            # Зациклити якщо коротше за потрібну тривалість
            if clip.duration < duration:
                clip = clip.loop(duration=duration)
            else:
                clip = clip.subclip(0, duration)

            # Кроп до 9:16
            src_ratio = clip.w / clip.h
            tgt_ratio = W / H
            if src_ratio > tgt_ratio:
                new_w = int(clip.h * tgt_ratio)
                clip = clip.crop(x_center=clip.w / 2, width=new_w)
            elif src_ratio < tgt_ratio:
                new_h = int(clip.w / tgt_ratio)
                clip = clip.crop(y_center=clip.h / 2, height=new_h)

            # Масштабування
            clip = clip.resize((W, H))
            return clip

        except Exception as e:
            logger.warning(f"Не вдалось обробити відео: {e}. Використовую кольоровий фон.")

    # Запасний варіант — темний градієнт
    logger.info("Генерую темний фон (Pexels недоступний)")

    def make_frame(t):
        frame = np.zeros((H, W, 3), dtype=np.uint8)
        # Темно-синій градієнт
        for y in range(H):
            v = int(10 + 25 * (y / H))
            frame[y, :] = [v, v + 5, v + 20]
        return frame

    return mpe.VideoClip(make_frame, duration=duration).set_fps(FPS)


def create_video(
    title: str,
    key_facts: list,
    audio_path: Path,
    topic_keywords: str,
    tmp_dir: Path,
    output_path: Path
) -> Path:
    """
    Зібрати фінальне відео для YouTube Shorts.

    title           — заголовок (3–6 слів, буде виведено ВЕЛИКИМИ)
    key_facts       — список із 3 коротких фактів
    audio_path      — шлях до MP3 (TTS)
    topic_keywords  — ключові слова для Pexels (англійською)
    tmp_dir         — тимчасова папка
    output_path     — куди зберегти MP4
    """

    # Завантажуємо аудіо і визначаємо тривалість
    audio_clip = mpe.AudioFileClip(str(audio_path))
    # Обрізаємо на 0.05 сек щоб уникнути moviepy OSError при читанні останніх фреймів
    safe_duration = max(0.5, audio_clip.duration - 0.05)
    audio_clip = audio_clip.subclip(0, safe_duration)
    duration = audio_clip.duration + 1.5  # невеликий відступ наприкінці

    logger.info(f"Тривалість відео: {duration:.1f} сек")

    # Фон
    bg_path = download_pexels_video(topic_keywords, tmp_dir)
    background = build_background(bg_path, duration)

    # Текстовий оверлей
    overlay = create_overlay_image(title, key_facts, duration, tmp_dir)

    # Компонування
    final = mpe.CompositeVideoClip(
        [background, overlay],
        size=(W, H)
    )
    final = final.set_audio(audio_clip)
    final = final.set_duration(duration)
    final = final.set_fps(FPS)

    # Рендеринг
    logger.info(f"Рендеринг відео → {output_path.name}...")
    final.write_videofile(
        str(output_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        bitrate="4000k",
        preset="fast",
        threads=2,
        verbose=False,
        logger=None
    )

    # Очищення пам'яті
    audio_clip.close()
    background.close()
    final.close()

    return output_path
