from telethon.sync import events
from service import db
from service.config import client, TARGET_USER
import logging
from utils.main_handler import handle_new_message
from utils.process_history import process_unread_messages


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

    loop.run_until_complete(process_unread_messages())

    with client:
        client.run_until_disconnected()
