from __future__ import annotations

from aiohttp import web

from service.db import db
from . import render_template, _redirect


async def index(request: web.Request) -> web.Response:
    message = request.rel_url.query.get("msg")
    queries = db.list_queries()
    return render_template("queries.jinja2", title="Запросы", message=message, queries=queries)


async def add_query(request: web.Request) -> web.Response:
    data = await request.post()
    phrase = data.get("phrase", "")
    try:
        query_id = db.add_query(phrase)
    except ValueError as exc:
        _redirect("/", str(exc))
    _redirect(f"/queries/{query_id}", "Запрос добавлен")


async def delete_query(request: web.Request) -> web.Response:
    query_id = int(request.match_info["query_id"])
    db.delete_query(query_id)
    _redirect("/", "Запрос удалён")


async def query_detail(request: web.Request) -> web.Response:
    query_id = int(request.match_info["query_id"])
    record = db.get_query(query_id)
    if not record:
        raise web.HTTPNotFound(text="Query not found")
    assigned = set(db.get_channel_ids_for_query(query_id))
    channels = db.list_channels()
    return render_template(
        "query_detail.jinja2",
        title=f"Запрос {record.id}",
        message=request.rel_url.query.get("msg"),
        query=record,
        selected_channels=[channel for channel in channels if channel.id in assigned],
        available_channels=[channel for channel in channels if channel.id not in assigned],
        assigned_channels=assigned,
        channel_groups_map=db.get_channel_groups_map(),
        groups=db.list_channel_groups(),
        group_memberships=db.get_all_group_memberships(),
    )


async def update_query(request: web.Request) -> web.Response:
    query_id = int(request.match_info["query_id"])
    data = await request.post()
    phrase = data.get("phrase", "")
    try:
        db.update_query(query_id, phrase)
    except ValueError as exc:
        _redirect(f"/queries/{query_id}", str(exc))
    _redirect(f"/queries/{query_id}", "Запрос обновлён")


async def update_query_channels(request: web.Request) -> web.Response:
    query_id = int(request.match_info["query_id"])
    data = await request.post()
    channel_ids = data.getall("channel_ids")
    db.set_query_channels(query_id, channel_ids)
    _redirect(f"/queries/{query_id}", "Связи обновлены")


routes = [
    web.get("/", index),
    web.post("/queries", add_query),
    web.post("/queries/{query_id:\\d+}/delete", delete_query),
    web.get("/queries/{query_id:\\d+}", query_detail),
    web.post("/queries/{query_id:\\d+}", update_query),
    web.post("/queries/{query_id:\\d+}/channels", update_query_channels),
]
