import logging
import traceback
from service import db
from telethon import functions, types
from service.config import client, TARGET_USER
from utils.main_handler import handle_new_message


# last_readed_id = result.messages[0].id
# unreaded_count = result.dialogs[0].unread_count

async def analyse(messages):
    async def fwd():
        await client.forward_messages(TARGET_USER, messages)

    if messages:
        await handle_new_message(
            messages[0] if isinstance(messages, list) else messages,
            fwd
        )


async def get_unread_messages(chat_id):
    chat = await client.get_input_entity(chat_id)
    result = await client(functions.messages.GetPeerDialogsRequest(
        peers=[chat]
    ))
    group = []
    group_id = -1
    message = None
    read_inbox_max_id = result.dialogs[0].read_inbox_max_id
    async for message in client.iter_messages(
            chat,
            min_id=read_inbox_max_id,
            reverse=True
    ):
        if hasattr(message, "grouped_id"):
            if group_id == message.grouped_id:
                group.append(message)
            else:
                await analyse(group)
                group = [message]
                group_id = message.grouped_id
        elif group:
            await analyse(group)
            group = []
            group_id = -1
        else:
            await analyse(message)


async def process_unread_messages():
    chats_to_process = db.get_chats()
    me = await client.get_me()
    me = {me.id, TARGET_USER.id}
    for chat in chats_to_process:
        if chat in me:
            continue
        try:
            await get_unread_messages(chat)
        except Exception as e:
            logging.error(f"Ошибка обработки непрочитанных сообщений в id {chat}: {e.__class__}: {e}\n"
                          f"{traceback.print_exc()}")


if __name__ == "__main__":
    import asyncio

    loop = asyncio.get_event_loop()
    loop.run_until_complete(process_unread_messages())

    # loop.run_until_complete(get_unread_messages(-1001844767026))
