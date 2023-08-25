from telethon.sync import events
from service import db
from service.config import client, TARGET_USER
from service.search_engine import find_queries
from service.utils import get_message_source_link, get_chat_name
import html
import logging
import traceback


async def handle_new_message(event: events.newmessage.NewMessage.Event):
    try:
        if hasattr(event, 'messages'):
            message = event.messages[0]
        else:
            message = event.message
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
            await client.send_message(TARGET_USER, infomes)
            await event.forward_to(TARGET_USER)
            logging.info(f"{chat_id} {chat} :: {res} :: {trep[:64]}...")
        else:
            logging.info(f"Skipped :: {chat_id} :: {chat} :: mid:{message.id} :: {trep}")
    except Exception as e:
        logging.error(f"Ошибка обработки сообщения: {e.__class__}: {e}\n"
                      f"{traceback.print_exc()}")


@client.on(events.Album(chats=db.get_chats()))
async def handle_album(event):
    await handle_new_message(event)


@client.on(events.NewMessage(chats=db.get_chats(), incoming=True))
async def handle_single(event):
    if (hasattr(event, 'message')
            and hasattr(event.message, 'groupped_id')
            and not event.message.groupped_id):
        await handle_new_message(event)


async def notify(text):
    await client.send_message(TARGET_USER, text)


if __name__ == "__main__":
    import asyncio

    loop = asyncio.get_event_loop()
    loop.run_until_complete(notify("Клиент успешно запущен!"))
    logging.info(f"Runned")
    with client:
        client.run_until_disconnected()