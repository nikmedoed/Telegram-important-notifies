import os
from dotenv import load_dotenv
from telethon.sync import TelegramClient
import logging
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

current_directory = os.path.dirname(os.path.abspath(__file__))
session = config_file_path = os.path.join(current_directory, 'channel_watcher.session')

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
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)

NLTK_LANGUAGE = os.getenv('NLTK_LANGUAGE')
try:
    words = word_tokenize("This is a test sentence.")
except LookupError:
    nltk.download('punkt')
try:
    stop_words = set(stopwords.words(NLTK_LANGUAGE))
except LookupError:
    nltk.download('stopwords')
    stop_words = set(stopwords.words("russian"))
