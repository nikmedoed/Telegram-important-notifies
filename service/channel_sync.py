from __future__ import annotations

import logging
from typing import Dict, List, Optional

from telethon import functions
from telethon.errors import ChannelInvalidError, ChatAdminRequiredError
from telethon.tl import types as tl_types

from service.db import ChannelRecord


def _can_export_invite(entity) -> bool:
    if isinstance(entity, tl_types.Channel):
        if entity.creator:
            return True
        rights = getattr(entity, "admin_rights", None)
        if rights:
            return bool(getattr(rights, "invite_users", False) or getattr(rights, "add_admins", False))
        return False
    if isinstance(entity, tl_types.Chat):
        return bool(entity.creator or getattr(entity, "admin_rights", None))
    return False


async def _resolve_invite_link(client, entity, existing: Optional[str]) -> str | None:
    if existing:
        return existing

    if isinstance(entity, tl_types.User):
        if getattr(entity, "username", None):
            return f"https://t.me/{entity.username}"
        return None

    if isinstance(entity, (tl_types.Chat, tl_types.Channel)):
        if getattr(entity, "username", None):
            return f"https://t.me/{entity.username}"
        if not _can_export_invite(entity):
            return None
        try:
            result = await client(functions.messages.ExportChatInviteRequest(peer=entity))
            return getattr(result, "link", None)
        except (ChannelInvalidError, ChatAdminRequiredError):
            return None
        except Exception:
            return None

    return None


def _detect_kind(dialog, entity) -> str:
    if dialog.is_user or isinstance(entity, tl_types.User):
        return "user"
    if dialog.is_group or isinstance(entity, (tl_types.Chat, tl_types.ChatForbidden)):
        return "chat"
    if dialog.is_channel or isinstance(entity, (tl_types.Channel, tl_types.ChannelForbidden)):
        if isinstance(entity, tl_types.Channel):
            if getattr(entity, "gigagroup", False):
                return "gigagroup"
            if getattr(entity, "megagroup", False):
                return "supergroup"
        return "channel"
    return "unknown"


async def fetch_dialog_channels(client, cached_links: Optional[Dict[int, Optional[str]]] = None) -> List[ChannelRecord]:
    cached_links = cached_links or {}
    records: List[ChannelRecord] = []
    async for dialog in client.iter_dialogs():
        try:
            entity = dialog.entity
            chat_id = int(dialog.id)
            title = dialog.title or getattr(entity, "title", None)
            if not title and isinstance(entity, tl_types.User):
                title = " ".join(filter(None, [entity.first_name, entity.last_name])).strip()
            title = title or f"Chat {chat_id}"
            invite_link = await _resolve_invite_link(client, entity, cached_links.get(chat_id))
            username = getattr(entity, "username", None)
            kind = _detect_kind(dialog, entity)
            if kind == "user":
                continue
            records.append(
                ChannelRecord(
                    id=chat_id,
                    title=title,
                    invite_link=invite_link,
                    username=username,
                    kind=kind,
                )
            )
        except Exception as exc:
            logging.warning("Skipping dialog due to error: %s", exc)
            continue
    return records
