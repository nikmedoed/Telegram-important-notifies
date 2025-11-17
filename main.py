import logging
import os

from telethon.sync import events

from service.config import client, TARGET_USER
from service.main_handler import handle_new_message
from service.process_history import process_unread_messages
from service.web import start_web_server


@client.on(events.Album())
async def handle_album(event):
    # first_message = event.messages[0] if getattr(event, "messages", None) else None
    # if first_message is not None and first_message.out:
    #     return
    await handle_new_message(event)


@client.on(events.NewMessage(incoming=True))
async def handle_single(event):
    if hasattr(event, 'message') and (not hasattr(event.message, 'grouped_id') or not event.message.grouped_id):
        await handle_new_message(event)


async def notify(text):
    await client.send_message(TARGET_USER, text)


if __name__ == "__main__":

    WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
    WEB_PORT = int(os.getenv("WEB_PORT", "8080"))


    async def app_main():
        await notify("Клиент успешно запущен!")
        logging.info("Client started")
        await process_unread_messages()
        runner = await start_web_server(client, host=WEB_HOST, port=WEB_PORT)
        try:
            await client.run_until_disconnected()
        finally:
            await runner.cleanup()


    client.loop.run_until_complete(app_main())
