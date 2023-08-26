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

message_mutex = asyncio.Lock()


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
        text = message.text.lower()
        res = find_queries(query, text)
        chat = await get_chat_name(message)
        trep = text.replace('\n', '|')

        if res:
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
                await client.send_message(TARGET_USER, infomes)
                if not forward_func:
                    await event.forward_to(TARGET_USER)
                else:
                    await forward_func()
            logging.info(f"{chat_id} {chat} :: {res} :: {trep[:64]}...")
        else:
            logging.info(f"Skipped :: {chat_id} :: {chat} :: mid:{message.id} :: {trep}")
        await client.send_read_acknowledge(message.chat, messages)
    except Exception as e:
        logging.error(f"Ошибка обработки сообщения: {e.__class__}: {e}\n"
                      f"{traceback.print_exc()}")
