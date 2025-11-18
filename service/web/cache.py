from __future__ import annotations

from datetime import datetime

from aiohttp import web

from service.main_handler import advanced_duplicate_cache, duplicate_cache
from service.search_engine import cache as search_cache
from . import render_template


def _format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "0 с"
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} ч")
    if minutes:
        parts.append(f"{minutes} м")
    if sec or not parts:
        parts.append(f"{sec} с")
    return " ".join(parts)


def _serialize_cache(cache, title: str, description: str) -> dict:
    entries = []
    for entry in cache.dump():
        expires_at = datetime.fromtimestamp(entry["expires_at"])
        entries.append(
            {
                "key": entry["key"],
                "value": entry["value"],
                "expires_in": entry["expires_in"],
                "expires_in_human": _format_duration(entry["expires_in"]),
                "expires_at": expires_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    entries.sort(key=lambda item: item["expires_in"])
    return {
        "title": title,
        "description": description,
        "ttl": cache.ttl,
        "entries": entries,
    }


async def cache_overview(_: web.Request) -> web.Response:
    caches = [
        _serialize_cache(
            duplicate_cache,
            "Кеш хешей сообщений",
            "Позволяет быстро отбрасывать точные дубликаты сообщений.",
        ),
        _serialize_cache(
            advanced_duplicate_cache,
            "Кеш последних сообщений отправителей",
            "Хранит тексты для сравнения похожести подряд идущих сообщений.",
        ),
        _serialize_cache(
            search_cache,
            "Кеш токенизации поиска",
            "Сохраняет результаты нормализации текста для поиска совпадений.",
        ),
    ]
    total_entries = sum(len(cache["entries"]) for cache in caches)
    return render_template(
        "cache.jinja2",
        title="Кеш сообщений",
        caches=caches,
        total_entries=total_entries,
    )


routes = [web.get("/cache", cache_overview)]
