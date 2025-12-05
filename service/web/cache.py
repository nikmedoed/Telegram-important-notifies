from __future__ import annotations

from datetime import datetime

from aiohttp import web

from service.db import db
from service.main_handler import advanced_duplicate_cache, duplicate_cache, ignore_matcher
from service.search_engine import cache as search_cache
from . import render_template, _redirect


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


def _extract_author_id(key: str) -> int | None:
    try:
        if "_" in key:
            return int(str(key).split("_", 1)[0])
    except (TypeError, ValueError):
        return None
    return None


def _serialize_cache(cache, title: str, description: str, *, allow_block: bool = False, entry_transform=None) -> dict:
    entries = []
    for entry in cache.dump():
        value = entry["value"]
        raw_value = None
        if isinstance(value, str):
            raw_value = value
        elif isinstance(value, dict):
            raw_value = value.get("raw")
        else:
            raw_value = getattr(value, "raw", None)
        expires_at = datetime.fromtimestamp(entry["expires_at"])
        payload = {
            "key": entry["key"],
            "value": value,
            "raw_value": raw_value,
            "expires_in": entry["expires_in"],
            "expires_in_human": _format_duration(entry["expires_in"]),
            "expires_at": expires_at.strftime("%Y-%m-%d %H:%M:%S"),
            "token_sorted": value.get("token_sorted") if isinstance(value, dict) else getattr(value, "token_sorted", None),
            "author_id": _extract_author_id(entry["key"]) if allow_block else None,
        }
        if entry_transform:
            payload.update(entry_transform(entry))
        entries.append(payload)
    entries.sort(key=lambda item: item["expires_in"])
    return {
        "title": title,
        "description": description,
        "ttl": cache.ttl,
        "entries": entries,
        "allow_block": allow_block,
    }


async def cache_overview(request: web.Request) -> web.Response:
    hash_cache_stats = {
        "title": "Кеш хешей сообщений (статистика)",
        "description": "Позволяет быстро отбрасывать точные дубликаты сообщений.",
        "ttl": duplicate_cache.ttl,
        "entries_count": len(duplicate_cache.dump()),
    }
    caches = [
        _serialize_cache(
            advanced_duplicate_cache,
            "Кеш последних сообщений отправителей",
            "Хранит тексты для сравнения похожести подряд идущих сообщений.",
            allow_block=True,
            entry_transform=dict,
        ),
        _serialize_cache(
            search_cache,
            "Кеш токенизации поиска",
            "Сохраняет результаты нормализации текста для поиска совпадений.",
        ),
    ]
    ignored = db.list_blocked_messages(limit=200)
    return render_template(
        "cache.jinja2",
        title="Кеш сообщений",
        caches=caches,
        hash_cache=hash_cache_stats,
        ignored_messages=ignored,
        message=request.rel_url.query.get("msg"),
    )


async def ignore_message(request: web.Request) -> web.Response:
    form = await request.post()
    text = (form.get("text") or "").strip()
    author_value = (form.get("author_id") or "").strip()
    author_id = None
    if author_value:
        try:
            author_id = int(author_value)
        except ValueError:
            _redirect("/cache", "author_id должен быть числом")
    normalized = text.lower()
    if not normalized:
        _redirect("/cache", "Нельзя заблокировать пустой текст")
    try:
        created, entry = db.add_blocked_message(normalized, author_id=author_id)
        ignore_matcher.add_entry(entry)
    except ValueError as exc:
        _redirect("/cache", str(exc))
    else:
        feedback = "Сообщение занесено в игнор-лист" if created else "Правило обновлено"
        _redirect("/cache", feedback)


async def unignore_message(request: web.Request) -> web.Response:
    form = await request.post()
    entry_id_raw = (form.get("id") or "").strip()
    if not entry_id_raw:
        _redirect("/cache", "Не указан id")
    try:
        entry_id = int(entry_id_raw)
    except ValueError:
        _redirect("/cache", "id должен быть числом")
    entry = db.remove_blocked_message(entry_id)
    if entry:
        ignore_matcher.remove_entry(entry.id, entry.author_id)
    feedback = "Правило удалено" if entry else "Правило не найдено"
    _redirect("/cache", feedback)


routes = [
    web.get("/cache", cache_overview),
    web.post("/cache/ignore", ignore_message),
    web.post("/cache/unignore", unignore_message),
]
