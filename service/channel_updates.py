import logging
from typing import Optional

from telethon import events
from telethon.tl import types as tl_types
from telethon.utils import get_peer_id

from service.channel_sync import _detect_kind
from service.db import ChannelRecord, db
from service.utils import format_user_name


class _EntityDialogProxy:
    __slots__ = ("is_user", "is_group", "is_channel")

    def __init__(self, entity):
        self.is_user = isinstance(entity, tl_types.User)
        self.is_group = isinstance(entity, (tl_types.Chat, tl_types.ChatForbidden))
        self.is_channel = isinstance(entity, (tl_types.Channel, tl_types.ChannelForbidden))


def _build_record(entity, existing: Optional[ChannelRecord] = None, forced_kind: Optional[str] = None) -> Optional[ChannelRecord]:
    try:
        channel_id = int(get_peer_id(entity))
    except Exception:
        channel_id = getattr(entity, "id", None)
    if channel_id is None:
        return None

    title = getattr(entity, "title", None)
    username = getattr(entity, "username", None)
    dialog_proxy = _EntityDialogProxy(entity)
    kind = forced_kind or _detect_kind(dialog_proxy, entity)

    if isinstance(entity, tl_types.User):
        title = format_user_name(entity)

    invite_link = None
    if existing:
        title = title or existing.title
        username = username or existing.username
        if not forced_kind and existing.kind:
            kind = existing.kind
        elif kind == "unknown":
            kind = existing.kind
        invite_link = existing.invite_link

    if kind == "user":
        return None

    return ChannelRecord(
        id=int(channel_id),
        title=title or f"Chat {channel_id}",
        invite_link=invite_link,
        username=username,
        kind=kind or "unknown",
    )


async def _upsert_entity(entity, forced_kind: Optional[str] = None) -> None:
    try:
        try:
            existing_id = int(get_peer_id(entity))
        except Exception:
            existing_id = getattr(entity, "id", None)
        existing = db.get_channel(int(existing_id)) if existing_id is not None else None
        record = _build_record(entity, existing=existing, forced_kind=forced_kind)
        if record:
            db.upsert_channels([record])
    except Exception:
        logging.exception("Failed to upsert chat/entity")


async def _refresh_peer(client, peer, forced_kind: Optional[str] = None) -> None:
    try:
        entity = await client.get_entity(peer)
    except Exception:
        logging.exception("Failed to fetch entity for %s", peer)
        return
    await _upsert_entity(entity, forced_kind=forced_kind)


def setup_channel_update_handlers(client) -> None:
    async def on_raw(event):
        update = event
        if isinstance(update, tl_types.UpdateChannel):
            await _refresh_peer(client, tl_types.PeerChannel(update.channel_id))
        elif isinstance(update, tl_types.UpdateChannelTooLong):
            await _refresh_peer(client, tl_types.PeerChannel(update.channel_id))
        elif isinstance(update, tl_types.UpdateChat):
            await _refresh_peer(client, tl_types.PeerChat(update.chat_id), forced_kind="chat")

    async def on_chat_action(event):
        if getattr(event, "new_title", None) or event.user_added or event.user_joined:
            chat = event.chat or await event.get_chat()
            forced_kind = "chat" if not event.is_channel else None
            await _upsert_entity(chat, forced_kind=forced_kind)

    client.add_event_handler(on_raw, events.Raw())
    client.add_event_handler(on_chat_action, events.ChatAction())
