from __future__ import annotations

from .database import Database
from .models import ChannelGroupRecord, ChannelRecord, QueryRecord

db = Database()

__all__ = [
    "db",
    "Database",
    "ChannelGroupRecord",
    "ChannelRecord",
    "QueryRecord",
]
