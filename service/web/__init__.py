from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote_plus, unquote_plus

from aiohttp import web
from service.config import WEB_HOST, WEB_PORT
from jinja2 import Environment, FileSystemLoader, select_autoescape

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

FLASH_COOKIE_NAME = "flash_msg"
FLASH_COOKIE_MAX_AGE = 30

_JINJA_ENV = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(("jinja2", "html", "xml")),
)
_JINJA_ENV.globals["static"] = lambda asset: f"/static/{asset.lstrip('/')}"


def _pop_flash(request: web.Request | None) -> str | None:
    if not request:
        return None
    raw = request.cookies.get(FLASH_COOKIE_NAME)
    if not raw:
        return None
    try:
        return unquote_plus(raw)
    except Exception:
        return raw


def render_template(template_name: str, *, request: web.Request | None = None, **context) -> web.Response:
    message = context.pop("message", None)
    if message is None:
        message = _pop_flash(request)
    context["message"] = message
    context.setdefault("title", "Telegram watcher")
    template = _JINJA_ENV.get_template(template_name)
    html = template.render(**context)
    response = web.Response(text=html, content_type="text/html")
    if request:
        response.del_cookie(FLASH_COOKIE_NAME, path="/")
    return response


def _redirect(path: str, message: str | None = None) -> web.HTTPSeeOther:
    response = web.HTTPSeeOther(path)
    if message:
        response.set_cookie(
            FLASH_COOKIE_NAME,
            quote_plus(message),
            max_age=FLASH_COOKIE_MAX_AGE,
            path="/",
        )
    raise response


from . import cache, channels, groups, queries  # noqa: E402  # isort:skip


def create_app(client) -> web.Application:
    app = web.Application()
    app["tg_client"] = client
    app.router.add_static("/static/", STATIC_DIR, name="static")
    app.add_routes(queries.routes)
    app.add_routes(groups.routes)
    app.add_routes(channels.routes)
    app.add_routes(cache.routes)
    return app


async def start_web_server(client, host: str | None = None, port: int | None = None):
    host = host if host is not None else WEB_HOST
    port = port if port is not None else WEB_PORT
    app = create_app(client)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    logging.info("Web UI listening on http://%s:%s", host, port)
    return runner
