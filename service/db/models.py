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


@dataclass(frozen=True)
class ClauseSpec:
    tokens: tuple[str, ...]
    required: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuerySearchEntry:
    id: int
    phrase: str
    tokens: list[str]
    clauses: tuple[ClauseSpec, ...]


@dataclass(frozen=True)
class ChannelSearchContext:
    """
    Per-channel search metadata built from assigned queries.
    Holds idf map and per-query tf-idf vectors (normalized) using shared tokens from QuerySearchEntry.
    """
    query_ids: tuple[int, ...]
    idf_map: dict[str, float]
    tfidf_map: dict[int, tuple[tuple[dict[str, float], float], ...]]
    entries_map: dict[int, QuerySearchEntry]
