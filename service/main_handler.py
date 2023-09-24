import html
import logging
import traceback
from service import db
from service.config import client, TARGET_USER
from service.search_engine import find_queries
from service.utils import get_chat_name, get_message_source_link
from telethon.tl import types
from telethon import events
import asyncio
import hashlib
from service.cache import Cache

message_mutex = asyncio.Lock()
duplicate_cache = Cache(60 * 60 * 12)


async def handle_new_message(event: events.newmessage.NewMessage.Event, forward_func=None):
    try:
        if hasattr(event, 'messages'):
            messages = event.messages
        elif hasattr(event, 'message') and isinstance(event.message, types.Message):
            messages = event.message
        else:
            messages = event

        message = messages[0] if isinstance(messages, list) else messages
        chat_id = message.chat_id
        query = db.get_word_for_chat(chat_id)
        chat = await get_chat_name(message)

        mess_info = f"{chat_id} :: {chat} :: mid:{message.id}"
        if not message.text:
            logging.info(f"No text :: {mess_info}")
            return

        text = message.text.lower()
        trep = text.replace('\n', '|')
        skip_info = f"{mess_info} :: {trep}"

        message_hash = hashlib.sha256(text.encode()).hexdigest()
        if duplicate_cache.get(message_hash):
            logging.info(f"Duplicate skipped :: {skip_info}")
            return
        duplicate_cache.set(message_hash, True)

        res = find_queries(query, text)
        if not res:
            logging.info(f"Skipped :: {skip_info}")
            return

        message_link, location_link = await get_message_source_link(message)
        scores = "\n".join([f'{i} :: {v:.0f} %' for i, v in res.items()])
        infomes = (
            f"<b>Сработало условие</b>\n"
            f"<a href='{html.escape(location_link)}'>{html.escape(chat)}</a>\n"
            f"id: <code>{chat_id}</code>\n\n"
            f"{scores}\n\n"
            f"<a href='{html.escape(message_link)}'>Сообщение</a>"
        )
        async with message_mutex:
            if not forward_func:
                message = await event.forward_to(TARGET_USER)
            else:
                message = await forward_func()
            if isinstance(message, list):
                message = message[0]
            await message.reply(infomes)
        logging.info(f"👀 {mess_info} :: {res} :: {trep[:64]}...")
    except Exception as e:
        logging.error(f"Ошибка обработки сообщения: {e.__class__}: {e}\n"
                      f"{traceback.print_exc()}")
    finally:
        await client.send_read_acknowledge(message.chat, messages)
