import asyncio
import hashlib
import html
import logging
import traceback

from rapidfuzz import fuzz
from telethon import events
from telethon.tl import types
from telethon.utils import get_peer_id

from service.cache import Cache
from service.db import db
from service.ignore_matcher import IgnoreMatcher
from service.search_engine import find_queries
from service.text_cleaner import clean_text
from service.utils import get_chat_name, get_message_source_link, sorted_tokens
from service.telegram_client import client, TARGET_USER

message_mutex = asyncio.Lock()
# Exact hash cache: skips identical messages seen in the recent window.
duplicate_cache = Cache(60 * 15, max_items=5000)
# Similarity cache: compares sorted tokens for near-duplicates.
advanced_duplicate_cache = Cache(60 * 15)
ignore_matcher = IgnoreMatcher(db)


def _get_original_author_id(message) -> int | None:
    """Prefer original sender/channel from forwarded metadata."""
    fwd = getattr(message, "fwd_from", None)
    if fwd:
        if getattr(fwd, "from_id", None):
            try:
                return get_peer_id(fwd.from_id)
            except Exception:
                pass
        if getattr(fwd, "saved_from_peer", None):
            try:
                return get_peer_id(fwd.saved_from_peer)
            except Exception:
                pass
    # Fallbacks: sender_id for chats, or chat_id as last resort.
    if getattr(message, "sender_id", None):
        return message.sender_id
    return getattr(message, "chat_id", None)


async def _get_album_text(message) -> str | None:
    """Return caption text from any message in the same album."""
    grouped_id = getattr(message, "grouped_id", None)
    if not grouped_id:
        return None

    try:
        ids = list(range(max(1, message.id - 10), message.id + 11))
        messages = await client.get_messages(message.chat_id or message.peer_id, ids=ids)
    except Exception:
        logging.warning("Failed to fetch album messages for ignore lookup", exc_info=True)
        return None

    parts = []
    for msg in messages:
        if not msg or getattr(msg, "grouped_id", None) != grouped_id:
            continue
        if msg.text:
            parts.append(msg.text)

    if not parts:
        return None

    combined = "\n".join(parts)
    logging.debug("Album text collected for ignore: %s", combined[:200])
    return combined


async def handle_control_message(event: events.newmessage.NewMessage.Event) -> None:
    """Process commands in the private chat with TARGET_USER."""
    message = getattr(event, "message", event)
    command = (message.text or "").strip().lower()
    if command != "нет":
        return
    reply = await message.get_reply_message()
    if not reply:
        await message.reply("Ответьте 'нет' на пересланное сообщение, чтобы добавить его в игнор.")
        return
    source_text = reply.text
    if not source_text:
        source_text = await _get_album_text(reply)
    if not source_text:
        await message.reply("В исходном сообщении нет текста — игнор не сохранен.")
        return
    normalized = clean_text(source_text).lower()
    if not normalized:
        await message.reply("После очистки текста ничего не осталось, игнор не сохранен.")
        return
    author_id = _get_original_author_id(reply)
    if author_id is None:
        await message.reply("Не удалось определить автора, игнор не сохранен.")
        return
    try:
        created, entry = db.add_blocked_message(normalized, author_id=author_id)
        ignore_matcher.add_entry(entry)
    except ValueError as exc:
        await message.reply(str(exc))
        return
    feedback = "Добавлено в игнор" if created else "Уже есть правило игнора"
    await message.reply(f"{feedback} для автора {author_id}")
    logging.info("Ignore via reply :: author %s :: %s", author_id, normalized[:64])


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
        is_album_event = isinstance(messages, list) and messages_count > 1
        chat_id = message.chat_id
        ctx = db.get_channel_search_context(chat_id)
        if not ctx or not ctx.query_ids:
            return

        # For grouped media (albums) rely on the Album event to avoid
        # splitting and forwarding only the first media item.
        if not is_album_event and getattr(message, "grouped_id", None):
            return

        entity = getattr(message, 'chat', None) or getattr(message, 'peer_id', None)
        if not entity and hasattr(event, 'chat'):
            entity = event.chat

        album_messages = messages if isinstance(messages, list) else None

        async def album_forward():
            # Explicitly forward all grouped messages to avoid Telethon
            # auto-forward losing part of the media group.
            return await client.forward_messages(TARGET_USER, album_messages)

        forward = album_forward if album_messages else forward_func

        await process_message(event, forward, message, ctx, messages_count)
        await client.send_read_acknowledge(entity, messages)
    except Exception as e:
        logging.error(f"Ошибка обработки сообщения: {e.__class__}: {e}\n"
                      f"{traceback.print_exc()}")


async def process_message(event, forward_func, message, ctx, messages_count):
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
    message_hash = hashlib.sha256(text.encode()).hexdigest()
    previous_messages_count = duplicate_cache.get(message_hash)
    duplicate_cache.set(message_hash, True)
    if previous_messages_count:
        logging.info(f"Duplicate skipped mc {messages_count} :: {skip_info}")
        return None

    token_sorted = sorted_tokens(text)
    prepared_text = {"token_sorted": token_sorted, "length": len(token_sorted), "raw": text}

    sender_id = message.sender_id if message.sender_id else message.chat_id
    cache_key = f"{sender_id}_{messages_count}"

    previous_message = advanced_duplicate_cache.get(cache_key)
    previous_message_length = previous_message["length"] if previous_message else 0
    advanced_duplicate_cache.set(cache_key, prepared_text)

    if previous_message_length:
        length_difference = abs(previous_message_length - prepared_text["length"])
        percentage_difference = 100 * length_difference / previous_message_length
        if percentage_difference <= 10 and previous_message:
            similarity = fuzz.ratio(prepared_text["token_sorted"], previous_message["token_sorted"])
            if similarity > 93:
                logging.info(f"Duplicate by similarity ({similarity:.1f}) :: {skip_info}")
                return None

    if ignore_matcher.check(prepared_text, message_hash, sender_id):
        logging.info(f"Blocked by fuzzy ignore :: {skip_info}")
        return None

    res = find_queries(ctx, text)
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
        forwarded = None
        try:
            forwarded = await event.forward_to(TARGET_USER) if not forward_func else await forward_func()
        except Exception:
            logging.warning("Forwarding failed; sending info without forward", exc_info=True)
        if isinstance(forwarded, list):
            forwarded = forwarded[0] if forwarded else None
        if forwarded:
            await forwarded.reply(infomes)
        else:
            # Fallback: deliver the match info even if forwarding failed or returned nothing.
            await client.send_message(TARGET_USER, infomes)
    logging.info(f"👀 {mess_info} :: {res} :: {trep[:64]}...")
