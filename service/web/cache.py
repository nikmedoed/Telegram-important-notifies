from __future__ import annotations

from datetime import datetime
import hashlib

from aiohttp import web

from service.main_handler import advanced_duplicate_cache, duplicate_cache
from service.search_engine import cache as search_cache
from service.db import db
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


def _serialize_cache(cache, title: str, description: str, *, allow_block: bool = False, entry_transform=None) -> dict:
    entries = []
    for entry in cache.dump():
        expires_at = datetime.fromtimestamp(entry["expires_at"])
        payload = {
            "key": entry["key"],
            "value": entry["value"],
            "raw_value": entry["value"] if isinstance(entry["value"], str) else None,
            "expires_in": entry["expires_in"],
            "expires_in_human": _format_duration(entry["expires_in"]),
            "expires_at": expires_at.strftime("%Y-%m-%d %H:%M:%S"),
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
    def _annotate_hash(entry):
        value = entry["value"]
        if isinstance(value, str):
            return {"hash": hashlib.sha256(value.encode()).hexdigest()}
        return {}

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
            allow_block=True,
            entry_transform=_annotate_hash,
        ),
        _serialize_cache(
            search_cache,
            "Кеш токенизации поиска",
            "Сохраняет результаты нормализации текста для поиска совпадений.",
        ),
    ]
    total_entries = sum(len(cache["entries"]) for cache in caches)
    ignored = db.list_blocked_messages(limit=200)
    return render_template(
        "cache.jinja2",
        title="Кеш сообщений",
        caches=caches,
        total_entries=total_entries,
        ignored_messages=ignored,
        message=request.rel_url.query.get("msg"),
    )


async def ignore_message(request: web.Request) -> web.Response:
    form = await request.post()
    text = (form.get("text") or "").strip()
    normalized = text.lower()
    if not normalized:
        _redirect("/cache", "Нельзя заблокировать пустой текст")
    message_hash = hashlib.sha256(normalized.encode()).hexdigest()
    try:
        created = db.add_blocked_message(message_hash, normalized)
    except ValueError as exc:
        _redirect("/cache", str(exc))
    else:
        feedback = "Сообщение занесено в игнор-лист" if created else "Такой текст уже заблокирован"
        _redirect("/cache", feedback)


async def unignore_message(request: web.Request) -> web.Response:
    form = await request.post()
    message_hash = (form.get("hash") or "").strip()
    if not message_hash:
        _redirect("/cache", "Не указан хеш сообщения")
    removed = db.remove_blocked_message(message_hash)
    feedback = "Правило удалено" if removed else "Хеш не найден"
    _redirect("/cache", feedback)


routes = [
    web.get("/cache", cache_overview),
    web.post("/cache/ignore", ignore_message),
    web.post("/cache/unignore", unignore_message),
]
