from __future__ import annotations

import logging
import os
import socket
import time

from telethon.sync import TelegramClient

from service.config import (
    TELEGRAM_NETWORK_CHECK_HOST,
    TELEGRAM_NETWORK_CHECK_PORT,
    TELEGRAM_NETWORK_CHECK_TIMEOUT,
    TELEGRAM_RETRY_DELAY_SECONDS,
    session,
)

logger = logging.getLogger(__name__)


def _wait_for_internet_connection(delay: float, host: str, port: int, timeout: float) -> None:
    """Block until the OS confirms a TCP connection can be established."""
    while True:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                logger.info("Internet connection detected (%s:%s)", host, port)
                return
        except OSError as exc:
            logger.warning(
                "Internet unreachable (%s:%s) - %s; retrying in %s seconds",
                host,
                port,
                exc,
                delay,
            )
            time.sleep(delay)


def _create_client() -> TelegramClient:
    client = TelegramClient(
        session,
        int(os.getenv("TELEGRAM_APP_ID")),
        os.getenv("TELEGRAM_API_HASH"),
    )
    client.parse_mode = "html"
    _wait_for_internet_connection(
        TELEGRAM_RETRY_DELAY_SECONDS,
        TELEGRAM_NETWORK_CHECK_HOST,
        TELEGRAM_NETWORK_CHECK_PORT,
        TELEGRAM_NETWORK_CHECK_TIMEOUT,
    )
    client.start()
    return client


client = _create_client()

TARGET_USER = client.get_entity(int(os.getenv("TARGET_USER")))

__all__ = ["client", "TARGET_USER"]
