from telethon.tl import types
from service.config import client
import logging
import traceback


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


async def chanel_title(message):
    return message.chat.title


async def group_title(message):
    ms = message.chat
    if not ms:
        ms = await client.get_entity(message.chat_id)
    return ms.title


async def user_ent(message):
    ms = message.ent
    return f"{ms.first_name} {ms.last_name} @{ms.username}"


async def user_name(message):
    ms = message.sender or message.chat
    if not ms:
        ms = await client.get_entity(message.sender_id)
        message.ent = ms
    return f"{ms.first_name} {ms.last_name} @{ms.username}"


TITLES = [chanel_title, group_title, user_ent, user_name]


async def get_chat_name(message):
    chat_name = "Unknown"
    for tit_func in TITLES:
        try:
            chat_name = await tit_func(message)
            break
        except:
            pass
    return chat_name
