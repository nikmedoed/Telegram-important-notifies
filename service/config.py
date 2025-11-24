import logging
import os

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    # format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    format="%(levelname)s:%(name)s - %(message)s",
)

data_directory = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
session = os.path.join(data_directory, "channel_watcher.session")

load_dotenv()

TELEGRAM_RETRY_DELAY_SECONDS = float(os.getenv("TELEGRAM_RETRY_DELAY_SECONDS", "5"))
TELEGRAM_NETWORK_CHECK_HOST = os.getenv("TELEGRAM_NETWORK_CHECK_HOST", "8.8.8.8")
TELEGRAM_NETWORK_CHECK_PORT = int(os.getenv("TELEGRAM_NETWORK_CHECK_PORT", "53"))
TELEGRAM_NETWORK_CHECK_TIMEOUT = float(os.getenv("TELEGRAM_NETWORK_CHECK_TIMEOUT", "3"))
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))
