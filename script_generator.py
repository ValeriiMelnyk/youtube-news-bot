"""
script_generator.py — Генерація сценарію через GPT-4o-mini
Вибирає найважливішу новину та створює 30–45 секундний сценарій
"""

import os
import json
import logging
from typing import List, Dict
from openai import OpenAI

logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


SYSTEM_PROMPT = """Ти — провідний редактор авторитетного українського новинного YouTube-каналу.
Твій стиль: стриманий, точний, авторитетний — як у BBC або DW.
Ніякої паніки, ніякого сенсаціоналізму. Тільки факти, подані чітко й зрозуміло.
Ти завжди відповідаєш ВИКЛЮЧНО коректним JSON без жодного тексту навколо."""


def generate_script(articles: List[Dict]) -> Dict:
    """
    На основі списку статей вибрати найважливішу та згенерувати:
    - Сценарій для диктора (30–45 сек)
    - Заголовок YouTube
    - Заголовок для відео (короткий)
    - 3 ключових факти для відображення
    - Теги та опис
    """

    # Форматуємо статті для промпту
    articles_text = "\n\n".join([
        f"[{i + 1}] ДЖЕРЕЛО: {a['source']} ({a['lang'].upper()})\n"
        f"ЗАГОЛОВОК: {a['title']}\n"
        f"ОПИС: {a['summary'][:400]}"
        for i, a in enumerate(articles[:15])
    ])

    user_prompt = f"""Ось сьогоднішні топ-новини:

{articles_text}

━━━ ТВОЄ ЗАВДАННЯ ━━━
1. Вибери ОДНУ найбільш важливу новину (пріоритет: геополітика, конфлікти, великі рішення)
2. Напиши сценарій для диктора ВИКЛЮЧНО українською мовою
3. Сценарій: 100–140 слів, 30–45 секунд читання
4. Тон: серйозний, авторитетний, нейтральний

Поверни ТІЛЬКИ цей JSON (без markdown, без пояснень):

{{
  "selected_index": <число 1-15>,
  "yt_title": "<YouTube заголовок до 60 символів, без кирличних великих літер ВСЮДИ, природний>",
  "title_overlay": "<заголовок для відео: 3–6 ВЕЛИКИХ СЛІВ українською>",
  "script": "<сценарій 100-140 слів українською. Починай з чіпляючого речення. Закінчуй закликом підписатися>",
  "key_facts": [
    "<факт 1: до 7 слів>",
    "<факт 2: до 7 слів>",
    "<факт 3: до 7 слів>"
  ],
  "pexels_keywords": "<2-3 АНГЛІЙСЬКИХ слова для пошуку відеофону, напр: war military conflict>",
  "description": "<опис для YouTube 100-130 символів>",
  "tags": ["новини", "Україна", "світ", "<конкретний тег4>", "<конкретний тег5>", "Shorts"]
}}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.65,
            max_tokens=1200,
            response_format={"type": "json_object"}
        )

        raw = response.choices[0].message.content
        result = json.loads(raw)

        # Валідація обов'язкових полів
        required_fields = ["yt_title", "title_overlay", "script", "key_facts", "pexels_keywords"]
        for field in required_fields:
            if field not in result:
                raise ValueError(f"GPT не повернув поле: {field}")

        logger.info(f"Сценарій згенеровано. Слів у сценарії: {len(result['script'].split())}")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"GPT повернув некоректний JSON: {e}")
        # Запасний варіант
        return _fallback_script(articles[0] if articles else {})
    except Exception as e:
        logger.error(f"Помилка генерації сценарію: {e}")
        return _fallback_script(articles[0] if articles else {})


def _fallback_script(article: Dict) -> Dict:
    """Запасний сценарій якщо GPT недоступний"""
    title = article.get("title", "Важливі новини дня")
    return {
        "yt_title": title[:60],
        "title_overlay": "ВАЖЛИВІ НОВИНИ",
        "script": (
            f"Увага — важлива новина. {title}. "
            "Слідкуйте за нашим каналом, щоб не пропустити найважливіші події у світі. "
            "Підпишіться та натисніть дзвіночок для щоденних оновлень."
        ),
        "key_facts": ["Стежте за оновленнями", "Підпишіться на канал", "Нові відео щодня"],
        "pexels_keywords": "world news politics",
        "description": "Найважливіші новини дня. Підпишіться щоб не пропустити!",
        "tags": ["новини", "Україна", "світ", "Shorts"]
    }
