import asyncio
import hashlib
import html
import logging
import traceback

from rapidfuzz import fuzz
from telethon import events
from telethon.tl import types

from service.cache import Cache
from service.config import client, TARGET_USER
from service.db import db
from service.search_engine import find_queries
from service.text_cleaner import clean_text
from service.utils import get_chat_name, get_message_source_link

message_mutex = asyncio.Lock()
duplicate_cache = Cache(60 * 60 * 12)
advanced_duplicate_cache = Cache(60 * 15)


async def handle_new_message(event: events.newmessage.NewMessage.Event, forward_func=None):
    try:
        if hasattr(event, 'messages'):
            messages = event.messages
        elif hasattr(event, 'message') and isinstance(event.message, types.Message):
            messages = event.message
        else:
            messages = event

        messages_count = len(messages) if isinstance(messages, list) else 1
        message = messages[0] if isinstance(messages, list) else messages
        chat_id = message.chat_id
        queries = db.get_queries_for_chat(chat_id)
        if not queries:
            return

        entity = getattr(message, 'chat', None) or getattr(message, 'peer_id', None)
        if not entity and hasattr(event, 'chat'):
            entity = event.chat

        await process_message(event, forward_func, message, queries, messages_count)
        await client.send_read_acknowledge(entity, messages)
    except Exception as e:
        logging.error(f"Ошибка обработки сообщения: {e.__class__}: {e}\n"
                      f"{traceback.print_exc()}")


async def process_message(event, forward_func, message, queries, messages_count):
    chat_id  = message.chat_id
    chat = await get_chat_name(message)
    mess_info = f"{chat_id} :: {chat} :: mid:{message.id}"

    if not message.text:
        logging.info(f"No text :: {mess_info}")
        return None

    text = clean_text(message.text).lower()
    if not text:
        logging.info(f"No usable text after cleaning :: {mess_info}")
        return None
    trep = text.replace('\n', '|')
    skip_info = f"{mess_info} :: {trep}"

    sender_id = message.sender_id if message.sender_id else message.chat_id
    cache_key = f"{sender_id}_{messages_count}"

    message_hash = hashlib.sha256(text.encode()).hexdigest()
    if db.is_message_blocked(message_hash):
        logging.info(f"Blocked message skipped :: {skip_info}")
        return None

    previous_messages_count = duplicate_cache.get(message_hash)
    duplicate_cache.set(message_hash, messages_count)

    previous_message = advanced_duplicate_cache.get(cache_key)
    previous_message_length = len(previous_message) if previous_message else 0
    advanced_duplicate_cache.set(cache_key, text)

    if previous_messages_count:
        logging.info(f"Duplicate skipped mc {messages_count} :: {skip_info}")
        return None

    if previous_message_length:
        length_difference = abs(previous_message_length - len(text))
        percentage_difference = 100 * length_difference / previous_message_length
        if percentage_difference <= 10 and previous_message:
            similarity = fuzz.token_sort_ratio(text, previous_message)
            if similarity > 93:
                logging.info(f"Duplicate by similarity ({similarity:.1f}) :: {skip_info}")
                return None

    res = find_queries(queries, text)
    if not res:
        logging.info(f"Skipped :: {skip_info}")
        return None

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
        forwarded = await event.forward_to(TARGET_USER) if not forward_func else await forward_func()
        if isinstance(forwarded, list):
            forwarded = forwarded[0]
        await forwarded.reply(infomes)
    logging.info(f"👀 {mess_info} :: {res} :: {trep[:64]}...")
