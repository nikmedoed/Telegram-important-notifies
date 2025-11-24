from prettytable import PrettyTable
from telethon import functions
from telethon.errors.rpcerrorlist import ChannelInvalidError, ChatAdminRequiredError
from telethon.tl.types import User, Chat, Channel

from service.telegram_client import client

dialogs = client.get_dialogs()
table = PrettyTable()
table.field_names = ["Chat ID", "Chat Title", "Invite Link"]

table.align["Chat ID"] = "r"
table.align["Chat Title"] = "l"
table.align["Invite Link"] = "l"

dialog_data = []

for dialog in dialogs:
    chat_id = dialog.id
    chat_title = dialog.title
    invite_link = "N/A"
    try:
        entity = client.get_entity(dialog)
        if isinstance(entity, User):
            invite_link = f"https://t.me/{entity.username}" if entity.username else "N/A"
        elif isinstance(entity, (Chat, Channel)):
            if entity.username:
                invite_link = f"https://t.me/{entity.username}"
            else:
                try:
                    result = client(functions.messages.ExportChatInviteRequest(peer=entity))
                    invite_link = result.link
                except (ChannelInvalidError, ChatAdminRequiredError):
                    invite_link = "N/A"
    except Exception as e:
        invite_link = str(e)
    dialog_data.append((chat_id, chat_title, invite_link))

sorted_dialogs = sorted(dialog_data, key=lambda x: x[1])

for chat_id, chat_title, invite_link in sorted_dialogs:
    table.add_row([chat_id, chat_title, invite_link])

print(table)

output_lines = ["Chat ID\tChat Title\tInvite Link"]
sorted_dialogs = sorted(dialog_data, key=lambda x: x[1])
for chat_id, chat_title, invite_link in sorted_dialogs:
    output_lines.append(f"{chat_id}\t{chat_title}\t{invite_link}")

# Выводим строки
output = "\n".join(output_lines)
print(output)
