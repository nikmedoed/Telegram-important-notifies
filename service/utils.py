import logging
import traceback

from telethon.tl import types

from service.db import db
from service.telegram_client import client


async def get_message_source_link(message):
    message_link = ""
    location_link = ""
    chat_entity = {}
    try:
        if not hasattr(message, 'ent'):
            message.ent = await client.get_entity(message.chat_id)
        chat_entity = message.ent
        try:
            if not chat_entity.username:
                raise Exception
            message_link = f"https://t.me/{chat_entity.username}/{message.id}"
        except:
            if message.peer_id:
                message_link = f"https://t.me/c/{message.peer_id.channel_id}/{message.id}"

        if chat_entity.username:
            location_link = f"https://t.me/{chat_entity.username}"
        elif isinstance(message.peer_id, types.PeerChat):
            location_link = f"https://t.me/c/{message.chat_id}"
        elif isinstance(message.peer_id, types.PeerUser):
            location_link = f"https://t.me/user/{chat_entity.id}"
        else:
            location_link = f"https://t.me/{message.peer_id.channel_id}"

        # if isinstance(entity, types.PeerChat):
        #     location_link = f"tg://join?invite={entity.access_hash}"
        # elif isinstance(entity, types.PeerUser):
        #     location_link = f"tg://user?id={entity.user_id}"
        # elif isinstance(entity, types.PeerChannel):
        #     location_link = f"tg://resolve?domain={entity.channel_id}"
    except Exception as e:
        logging.error("Get Link error: {e.__class__}: {e}\n"
                      f"Message :: {message}\n"
                      f"Entity :: {chat_entity}\n"
                      f"{traceback.print_exc()}")
        pass
    return message_link, location_link


def format_user_name(entity):
    if not entity:
        return "Unknown"
    first = getattr(entity, "first_name", "")
    last = getattr(entity, "last_name", "")
    username = getattr(entity, "username", "")
    full_name = " ".join(part for part in (first, last) if part).strip()
    if username:
        return f"{full_name} @{username}"
    return full_name or "Unknown"


def _extract_title_from_message(message):
    chat = getattr(message, "chat", None)
    if chat and getattr(chat, "title", None):
        return chat.title
    sender = getattr(message, "sender", None)
    if sender:
        return format_user_name(sender)
    ent = getattr(message, "ent", None)
    if ent:
        return format_user_name(ent)
    return ""


async def get_chat_name(message):
    title = _extract_title_from_message(message)
    if title:
        return title

    channel = db.get_channel(message.chat_id)
    if channel and channel.title:
        return channel.title

    return "Unknown"
