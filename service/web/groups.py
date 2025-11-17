from __future__ import annotations

from aiohttp import web

from service.db import db
from . import render_template, _redirect


async def groups_page(request: web.Request) -> web.Response:
    message = request.rel_url.query.get("msg")
    groups = db.list_channel_groups()
    return render_template("groups.jinja2", title="Группы каналов", message=message, groups=groups)


async def add_group(request: web.Request) -> web.Response:
    data = await request.post()
    title = data.get("title", "")
    description = data.get("description", "")
    try:
        group_id = db.add_channel_group(title, description)
    except ValueError as exc:
        _redirect("/groups", str(exc))
    _redirect(f"/groups/{group_id}", "Группа создана")


async def delete_group(request: web.Request) -> web.Response:
    group_id = int(request.match_info["group_id"])
    db.delete_channel_group(group_id)
    _redirect("/groups", "Группа удалена")


async def group_detail(request: web.Request) -> web.Response:
    group_id = int(request.match_info["group_id"])
    record = db.get_channel_group(group_id)
    if not record:
        raise web.HTTPNotFound(text="Group not found")

    assigned = set(db.get_channel_ids_for_group(group_id))
    channels = db.list_channels()
    total_channels = len(assigned)

    group_query_counts = db.get_group_query_assignments(group_id)

    queries_info = []
    for query in db.list_queries():
        assigned_count = group_query_counts.get(query.id, 0)
        queries_info.append(
            {
                "query": query,
                "assigned_count": assigned_count,
                "is_selected": bool(total_channels and assigned_count == total_channels),
                "is_partial": bool(total_channels and 0 < assigned_count < total_channels),
            }
        )
    return render_template(
        "group_detail.jinja2",
        title=f"Группа {record.title}",
        message=request.rel_url.query.get("msg"),
        group=record,
        selected_channels=[channel for channel in channels if channel.id in assigned],
        available_channels=[channel for channel in channels if channel.id not in assigned],
        assigned_channels=assigned,
        queries_info=queries_info,
        has_channels=total_channels > 0,
    )


async def update_group(request: web.Request) -> web.Response:
    group_id = int(request.match_info["group_id"])
    data = await request.post()
    title = data.get("title", "")
    description = data.get("description", "")
    try:
        db.update_channel_group(group_id, title, description)
    except ValueError as exc:
        _redirect(f"/groups/{group_id}", str(exc))
    _redirect(f"/groups/{group_id}", "Группа обновлена")


async def update_group_channels(request: web.Request) -> web.Response:
    group_id = int(request.match_info["group_id"])
    data = await request.post()
    channel_ids = data.getall("channel_ids")
    db.set_channel_group_members(group_id, channel_ids)
    _redirect(f"/groups/{group_id}", "Состав обновлён")


async def update_group_queries(request: web.Request) -> web.Response:
    group_id = int(request.match_info["group_id"])
    members = db.get_channel_ids_for_group(group_id)
    if not members:
        _redirect(f"/groups/{group_id}", "Добавьте каналы в группу, чтобы указать запросы")
    data = await request.post()
    query_ids = data.getall("query_ids")
    db.set_group_queries(group_id, query_ids)
    _redirect(f"/groups/{group_id}", "Запросы для группы обновлены")


routes = [
    web.get("/groups", groups_page),
    web.post("/groups", add_group),
    web.get("/groups/{group_id:\\d+}", group_detail),
    web.post("/groups/{group_id:\\d+}", update_group),
    web.post("/groups/{group_id:\\d+}/delete", delete_group),
    web.post("/groups/{group_id:\\d+}/channels", update_group_channels),
    web.post("/groups/{group_id:\\d+}/queries", update_group_queries),
]
