from __future__ import annotations

import logging

from aiohttp import web

from service.channel_sync import fetch_dialog_channels
from service.db import db
from . import render_template, _redirect


async def channels_page(request: web.Request) -> web.Response:
    return render_template(
        "channels.jinja2",
        title="Каналы",
        message=request.rel_url.query.get("msg"),
        channels=db.list_channels(),
        channel_groups_map=db.get_channel_groups_map(),
    )


async def channel_detail(request: web.Request) -> web.Response:
    channel_id = int(request.match_info["channel_id"])
    record = db.get_channel(channel_id)
    if not record:
        raise web.HTTPNotFound(text="Channel not found")

    assigned = set(db.get_query_ids_for_channel(channel_id))
    queries = db.list_queries()
    ordered_queries = (
            [q for q in queries if q.id in assigned] +
            [q for q in queries if q.id not in assigned]
    )
    return render_template(
        "channel_detail.jinja2",
        title=f"Канал {record.title}",
        message=request.rel_url.query.get("msg"),
        channel=record,
        queries=ordered_queries,
        assigned_queries=assigned,
        channel_groups=db.get_groups_for_channel(channel_id),
    )


async def update_channel_queries(request: web.Request) -> web.Response:
    channel_id = int(request.match_info["channel_id"])
    data = await request.post()
    query_ids = data.getall("query_ids")
    db.set_channel_queries(channel_id, query_ids)
    _redirect(f"/channels/{channel_id}", "Связи обновлены")


async def refresh_channels(request: web.Request) -> web.Response:
    client = request.app["tg_client"]
    try:
        existing_channels = db.list_channels()
        existing_links = {channel.id: channel.invite_link for channel in existing_channels if channel.invite_link}
        existing_ids = {channel.id for channel in existing_channels}
        records = await fetch_dialog_channels(client, cached_links=existing_links)
        fetched_ids = {record.id for record in records}
        removed_ids = [channel_id for channel_id in existing_ids if channel_id not in fetched_ids]
        removed = db.delete_channels(removed_ids)
        db.delete_channels_by_kind("user")
        updated = db.upsert_channels(records)
        msg = f"Обновлено {updated} записей"
        if removed:
            msg = f"{msg}, удалено {removed}"
    except Exception as exc:  # pragma: no cover
        logging.exception("Failed to refresh channels")
        msg = f"Ошибка обновления: {exc}"
    _redirect("/channels", msg)


routes = [
    web.get("/channels", channels_page),
    web.get("/channels/{channel_id:-?\\d+}", channel_detail),
    web.post("/channels/{channel_id:-?\\d+}/queries", update_channel_queries),
    web.post("/channels/refresh", refresh_channels),
]
