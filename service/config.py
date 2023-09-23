import os
from dotenv import load_dotenv
from telethon.sync import TelegramClient
import logging

from service.data_dir import data_directory

session = os.path.join(data_directory, 'channel_watcher.session')

load_dotenv()

client = TelegramClient(
    session,
    int(os.getenv('TELEGRAM_APP_ID')),
    os.getenv('TELEGRAM_API_HASH')
)
client.parse_mode = 'html'
client.start()

TARGET_USER = int(os.getenv('TARGET_USER'))
TARGET_USER = client.get_entity(TARGET_USER)

logging.basicConfig(
    level=logging.INFO,
    # format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    format="%(levelname)s:%(name)s - %(message)s",
)
