"""
news_fetcher.py — Збір актуальних новин зі світових джерел
Підтримує Ukrainian та English RSS-стрічки з фокусом на геополітику та конфлікти
"""

import re
import logging
import feedparser
from typing import List, Dict

logger = logging.getLogger(__name__)

# ─── Джерела новин ───────────────────────────────────────────
NEWS_SOURCES = [
    # Українськомовні
    {
        "url": "https://feeds.bbci.co.uk/ukrainian/rss.xml",
        "name": "BBC Україна",
        "lang": "uk",
        "priority": 1
    },
    {
        "url": "https://rss.dw.com/rdf/rss-uk-all",
        "name": "DW Україна",
        "lang": "uk",
        "priority": 1
    },
    {
        "url": "https://www.ukrinform.ua/rss/block-world",
        "name": "Укрінформ Світ",
        "lang": "uk",
        "priority": 1
    },
    {
        "url": "https://www.radiosvoboda.org/api/zpqoimvekg",
        "name": "Радіо Свобода",
        "lang": "uk",
        "priority": 2
    },
    # Англомовні (для більшого охоплення)
    {
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "name": "BBC World",
        "lang": "en",
        "priority": 2
    },
    {
        "url": "https://feeds.reuters.com/reuters/worldnews",
        "name": "Reuters World",
        "lang": "en",
        "priority": 2
    },
    {
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "name": "NYT World",
        "lang": "en",
        "priority": 3
    },
    {
        "url": "https://feeds.skynews.com/feeds/rss/world.xml",
        "name": "Sky News World",
        "lang": "en",
        "priority": 3
    },
]

# Ключові слова для фільтрації (конфлікти, геополітика)
PRIORITY_KEYWORDS = [
    # Конфлікти
    "war", "attack", "strike", "military", "troops", "missiles",
    "conflict", "ceasefire", "offensive", "war",
    # Геополітика
    "sanctions", "nato", "un ", "election", "president", "prime minister",
    "summit", "treaty", "nuclear", "crisis",
    # Регіони
    "ukraine", "russia", "middle east", "israel", "iran", "china",
    "north korea", "taiwan", "gaza", "syria",
    # Укр
    "війна", "удар", "наступ", "атака", "ракет", "санкці", "вибори",
    "переговор", "нато", "оон", "криза", "ядерн"
]


def clean_html(text: str) -> str:
    """Видалення HTML тегів із тексту"""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def priority_score(article: dict) -> int:
    """Розрахунок пріоритетності статті за ключовими словами"""
    score = 0
    combined = (article["title"] + " " + article["summary"]).lower()
    for keyword in PRIORITY_KEYWORDS:
        if keyword in combined:
            score += 1
    return score


def fetch_top_news(max_articles: int = 20) -> List[Dict]:
    """
    Завантажити топ-новини з усіх джерел.
    Повертає список статей, відсортованих за релевантністю.
    """
    all_articles = []

    for source in NEWS_SOURCES:
        try:
            logger.debug(f"Завантаження: {source['name']}...")
            feed = feedparser.parse(source["url"])

            articles_from_source = 0
            for entry in feed.entries[:6]:  # Топ 6 з кожного джерела
                title = clean_html(entry.get("title", "")).strip()
                summary = clean_html(
                    entry.get("summary", entry.get("description", ""))
                ).strip()

                if not title or len(title) < 10:
                    continue

                article = {
                    "title": title,
                    "summary": summary[:500],  # Обмежуємо розмір
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "source": source["name"],
                    "lang": source["lang"],
                    "source_priority": source["priority"],
                }
                all_articles.append(article)
                articles_from_source += 1

            logger.debug(f"  {source['name']}: {articles_from_source} статей")

        except Exception as e:
            logger.warning(f"Помилка при завантаженні {source['name']}: {e}")
            continue

    if not all_articles:
        logger.error("Жодне джерело новин не відповіло!")
        return []

    # Сортування: спочатку за пріоритетністю ключових слів, потім за джерелом
    all_articles.sort(
        key=lambda a: (priority_score(a), -a["source_priority"]),
        reverse=True
    )

    logger.info(f"Зібрано {len(all_articles)} статей, топ-{max_articles} відібрано")
    return all_articles[:max_articles]
