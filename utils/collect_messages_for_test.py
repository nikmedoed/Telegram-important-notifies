from service.config import client
from service.data_dir import data_directory
import hashlib
import os

chat_ids = [
    -1001844767026,
    -1001628122702,
    -1001820749278,
    -1001627327716,
    -1001805296788
]

output_directory = "messages"
output_directory = os.path.join(data_directory, output_directory)
if not os.path.exists(output_directory):
    os.makedirs(output_directory)

for chat_id in chat_ids:
    messages = client.get_messages(chat_id, limit=1000)
    for message in messages:
        if message.text:
            message_hash = hashlib.md5(message.text.encode()).hexdigest()

            file_path = os.path.join(output_directory, f"{message_hash}.txt")

            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(message.text)
