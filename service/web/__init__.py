from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlencode

from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

_JINJA_ENV = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(("jinja2", "html", "xml")),
)
_JINJA_ENV.globals["static"] = lambda asset: f"/static/{asset.lstrip('/')}"


def render_template(template_name: str, **context) -> web.Response:
    context.setdefault("message", None)
    context.setdefault("title", "Telegram watcher")
    template = _JINJA_ENV.get_template(template_name)
    html = template.render(**context)
    return web.Response(text=html, content_type="text/html")


def _redirect(path: str, message: str | None = None) -> web.HTTPSeeOther:
    if message:
        separator = "&" if "?" in path else "?"
        path = f"{path}{separator}{urlencode({'msg': message})}"
    raise web.HTTPSeeOther(path)


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


async def start_web_server(client, host: str = "127.0.0.1", port: int = 8080):
    app = create_app(client)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    logging.info("Web UI listening on http://%s:%s", host, port)
    return runner
