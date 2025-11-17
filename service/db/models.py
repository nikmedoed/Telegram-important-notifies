from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryRecord:
    id: int
    phrase: str
    channel_count: int = 0


@dataclass(frozen=True)
class ChannelRecord:
    id: int
    title: str
    invite_link: str | None
    username: str | None
    kind: str | None = None


@dataclass(frozen=True)
class ChannelGroupRecord:
    id: int
    title: str
    description: str | None = None
    channel_count: int = 0
