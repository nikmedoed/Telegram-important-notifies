import os
import socket
import time

from dotenv import load_dotenv
from telethon.sync import TelegramClient
import logging

logging.basicConfig(
    level=logging.INFO,
    # format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    format="%(levelname)s:%(name)s - %(message)s",
)

data_directory = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
session = os.path.join(data_directory, 'channel_watcher.session')

load_dotenv()

TELEGRAM_RETRY_DELAY_SECONDS = float(os.getenv("TELEGRAM_RETRY_DELAY_SECONDS", "5"))
TELEGRAM_NETWORK_CHECK_HOST = os.getenv("TELEGRAM_NETWORK_CHECK_HOST", "8.8.8.8")
TELEGRAM_NETWORK_CHECK_PORT = int(os.getenv("TELEGRAM_NETWORK_CHECK_PORT", "53"))
TELEGRAM_NETWORK_CHECK_TIMEOUT = float(os.getenv("TELEGRAM_NETWORK_CHECK_TIMEOUT", "3"))


def _wait_for_internet_connection(delay: float, host: str, port: int, timeout: float) -> None:
    """Block until the OS confirms a TCP connection can be established."""
    while True:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                logging.info("Internet connection detected (%s:%s)", host, port)
                return
        except OSError as exc:
            logging.warning(
                "Internet unreachable (%s:%s) - %s; retrying in %s seconds",
                host,
                port,
                exc,
                delay,
            )
            time.sleep(delay)


client = TelegramClient(
    session,
    int(os.getenv('TELEGRAM_APP_ID')),
    os.getenv('TELEGRAM_API_HASH')
)
client.parse_mode = 'html'
_wait_for_internet_connection(
    TELEGRAM_RETRY_DELAY_SECONDS,
    TELEGRAM_NETWORK_CHECK_HOST,
    TELEGRAM_NETWORK_CHECK_PORT,
    TELEGRAM_NETWORK_CHECK_TIMEOUT,
)
client.start()

TARGET_USER = int(os.getenv('TARGET_USER'))
TARGET_USER = client.get_entity(TARGET_USER)
