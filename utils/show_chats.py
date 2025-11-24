from prettytable import PrettyTable
from service.telegram_client import client

dialogs = client.get_dialogs()
table = PrettyTable()
table.field_names = ["Chat ID", "Chat Title"]

table.align["Chat ID"] = "r"
table.align["Chat Title"] = "l"

dialog_data = [(entity.id, entity.title) for entity in dialogs]

sorted_dialogs = sorted(dialog_data, key=lambda x: x[1])

for chat_id, chat_title in sorted_dialogs:
    table.add_row([chat_id, chat_title])

print(table)
