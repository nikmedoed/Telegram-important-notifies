from __future__ import annotations

import threading

from .database import Database
from .models import ChannelGroupRecord, ChannelRecord, QueryRecord

_db_instance: Database | None = None
_db_lock = threading.Lock()


def _get_db() -> Database:
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                _db_instance = Database()
    return _db_instance


class _DatabaseProxy:
    """Lazily instantiate the heavy Database to avoid circular imports at module load."""

    def __getattr__(self, item):
        return getattr(_get_db(), item)


db = _DatabaseProxy()

__all__ = [
    "db",
    "Database",
    "ChannelGroupRecord",
    "ChannelRecord",
    "QueryRecord",
]
