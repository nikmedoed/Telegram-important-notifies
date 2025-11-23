import logging

from telethon.sync import events

from service.config import client, TARGET_USER
from service.main_handler import handle_new_message
from service.process_history import process_unread_messages
from service.web import start_web_server


if __name__ == "__main__":

    client.add_event_handler(handle_new_message, events.Album())
    client.add_event_handler(handle_new_message, events.NewMessage(incoming=True))

    async def app_main():
        runner = await start_web_server(client)
        await client.send_message(TARGET_USER, "Клиент успешно запущен!")
        logging.info("Client started")
        await process_unread_messages()
        try:
            await client.run_until_disconnected()
        finally:
            await runner.cleanup()


    client.loop.run_until_complete(app_main())
