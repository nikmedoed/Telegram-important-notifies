from __future__ import annotations

import hashlib
import sqlite3
import threading
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set, Tuple

from service.bootstrap import bootstrap_from_legacy_files
from service.config import data_directory
from .migrations import run_migrations
from .models import (
    BlockedMessageEntry,
    ChannelGroupRecord,
    ChannelRecord,
    QueryRecord,
    QuerySearchEntry,
    ChannelSearchContext,
)
from .sql import *
from ..utils import sorted_tokens


class Database:
    """Everything related to SQLite access lives here."""

    def __init__(self) -> None:
        self._db_dir = Path(data_directory)
        self._db_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._db_dir / "app.db"
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
        run_migrations(self._conn, self._lock, self._db_dir)
        self._bootstrap_from_legacy_files()
        self._query_entries: Dict[int, QuerySearchEntry] = {}
        self._channel_search_ctx: Dict[int, ChannelSearchContext] = {}
        self._reload_assignment_cache()
        self._blocked_entries: List[BlockedMessageEntry] = []
        self._reload_blocked_messages_cache()

    # region helpers -----------------------------------------------------
    def _execute(self, sql: str, params: Sequence | Tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _executemany(self, sql: str, rows: Iterable[Sequence]) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.executemany(sql, rows)
            self._conn.commit()
            return cur

    def _fetchall(self, sql: str, params: Sequence | Tuple = ()) -> List[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def _fetchone(self, sql: str, params: Sequence | Tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    @staticmethod
    def _normalize_ids(values: Sequence[int]) -> List[int]:
        collected = set()
        for value in values:
            text = str(value).strip()
            if not text:
                continue
            try:
                collected.add(int(text))
            except ValueError:
                continue
        return sorted(collected)

    # region bootstrap --------------------------------------------------
    def _bootstrap_from_legacy_files(self) -> None:
        with self._lock:
            bootstrap_from_legacy_files(self._conn, data_directory)

    # region query operations -------------------------------------------
    def list_queries(self) -> List[QueryRecord]:
        rows = self._fetchall(SQL_LIST_QUERIES)
        return [QueryRecord(id=row["id"], phrase=row["phrase"], channel_count=row["channel_count"]) for row in rows]

    def add_query(self, phrase: str) -> int:
        cleaned = (phrase or "").strip()
        if not cleaned:
            raise ValueError("Query text can not be empty")
        cur = self._execute("INSERT INTO queries (phrase) VALUES (?)", (cleaned,))
        return int(cur.lastrowid)

    def update_query(self, query_id: int, phrase: str) -> None:
        cleaned = (phrase or "").strip()
        if not cleaned:
            raise ValueError("Query text can not be empty")
        cur = self._execute("UPDATE queries SET phrase = ? WHERE id = ?", (cleaned, query_id))
        if cur.rowcount == 0:
            raise ValueError(f"Query {query_id} not found")
        self._reload_assignment_cache()

    def delete_query(self, query_id: int) -> None:
        self._execute("DELETE FROM channel_queries WHERE query_id = ?", (query_id,))
        cur = self._execute("DELETE FROM queries WHERE id = ?", (query_id,))
        if cur.rowcount:
            self._reload_assignment_cache()

    def get_query(self, query_id: int) -> QueryRecord | None:
        row = self._fetchone(SQL_GET_QUERY, (query_id,))
        if not row:
            return None
        return QueryRecord(id=row["id"], phrase=row["phrase"], channel_count=row["channel_count"])

    def get_channel_ids_for_query(self, query_id: int) -> List[int]:
        rows = self._fetchall(SQL_CHANNEL_IDS_FOR_QUERY, (query_id,))
        return [row["channel_id"] for row in rows]

    def set_query_channels(self, query_id: int, channel_ids: Sequence[int]) -> None:
        unique_ids = self._normalize_ids(channel_ids)
        self._execute("DELETE FROM channel_queries WHERE query_id = ?", (query_id,))
        if unique_ids:
            self._executemany(
                "INSERT INTO channel_queries (channel_id, query_id) VALUES (?, ?)",
                ((cid, query_id) for cid in unique_ids),
            )
        self._reload_assignment_cache()

    # region channel operations -----------------------------------------
    def list_channels(self) -> List[ChannelRecord]:
        rows = self._fetchall(SQL_LIST_CHANNELS)
        return [
            ChannelRecord(
                id=row["id"],
                title=row["title"] or f"Chat {row['id']}",
                invite_link=row["invite_link"],
                username=row["username"],
                kind=row["kind"],
            )
            for row in rows
        ]

    def get_channel(self, channel_id: int) -> ChannelRecord | None:
        row = self._fetchone(SQL_GET_CHANNEL, (channel_id,))
        if not row:
            return None
        return ChannelRecord(
            id=row["id"],
            title=row["title"] or f"Chat {row['id']}",
            invite_link=row["invite_link"],
            username=row["username"],
            kind=row["kind"],
        )

    def upsert_channels(self, entries: Iterable[ChannelRecord]) -> int:
        payload = []
        for entry in entries:
            payload.append(
                {
                    "id": entry.id,
                    "title": entry.title,
                    "invite_link": entry.invite_link,
                    "username": entry.username,
                    "kind": entry.kind or "unknown",
                }
            )
        if not payload:
            return 0
        self._executemany(SQL_UPSERT_CHANNELS, payload)
        return len(payload)

    def delete_channels_by_kind(self, kind: str) -> int:
        cur = self._execute("DELETE FROM channels WHERE kind = ?", (kind,))
        return cur.rowcount

    def delete_channels(self, channel_ids: Sequence[int]) -> int:
        normalized = self._normalize_ids(channel_ids)
        if not normalized:
            return 0
        placeholders = ",".join("?" for _ in normalized)
        cur = self._execute(f"DELETE FROM channels WHERE id IN ({placeholders})", normalized)
        if cur.rowcount:
            self._reload_assignment_cache()
        return cur.rowcount

    def get_query_ids_for_channel(self, channel_id: int) -> List[int]:
        rows = self._fetchall(SQL_QUERY_IDS_FOR_CHANNEL, (channel_id,))
        return [row["query_id"] for row in rows]

    def set_channel_queries(self, channel_id: int, query_ids: Sequence[int]) -> None:
        normalized = self._normalize_ids(query_ids)
        self._execute("DELETE FROM channel_queries WHERE channel_id = ?", (channel_id,))
        if normalized:
            self._executemany(
                "INSERT INTO channel_queries (channel_id, query_id) VALUES (?, ?)",
                ((channel_id, qid) for qid in normalized),
            )
        self._reload_assignment_cache()

    # region groups ------------------------------------------------------
    def list_channel_groups(self) -> List[ChannelGroupRecord]:
        rows = self._fetchall(SQL_LIST_GROUPS)
        return [
            ChannelGroupRecord(
                id=row["id"],
                title=row["title"],
                description=row["description"],
                channel_count=row["channel_count"],
            )
            for row in rows
        ]

    def get_channel_group(self, group_id: int) -> ChannelGroupRecord | None:
        row = self._fetchone(SQL_GET_GROUP, (group_id,))
        if not row:
            return None
        return ChannelGroupRecord(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            channel_count=row["channel_count"],
        )

    def add_channel_group(self, title: str, description: str | None = None) -> int:
        cleaned = (title or "").strip()
        if not cleaned:
            raise ValueError("Название группы не может быть пустым")
        cur = self._execute(
            "INSERT INTO channel_groups (title, description) VALUES (?, ?)",
            (cleaned, (description or "").strip() or None),
        )
        return int(cur.lastrowid)

    def update_channel_group(self, group_id: int, title: str, description: str | None = None) -> None:
        cleaned = (title or "").strip()
        if not cleaned:
            raise ValueError("Название группы не может быть пустым")
        cur = self._execute(
            "UPDATE channel_groups SET title = ?, description = ? WHERE id = ?",
            (cleaned, (description or "").strip() or None, group_id),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Группа {group_id} не найдена")

    def delete_channel_group(self, group_id: int) -> None:
        self._execute("DELETE FROM channel_groups WHERE id = ?", (group_id,))

    def get_channel_ids_for_group(self, group_id: int) -> List[int]:
        rows = self._fetchall(SQL_GROUP_CHANNEL_IDS, (group_id,))
        return [row["channel_id"] for row in rows]

    def set_channel_group_members(self, group_id: int, channel_ids: Sequence[int]) -> None:
        normalized = self._normalize_ids(channel_ids)
        self._execute("DELETE FROM channel_group_members WHERE group_id = ?", (group_id,))
        if normalized:
            self._executemany(
                "INSERT INTO channel_group_members (group_id, channel_id) VALUES (?, ?)",
                ((group_id, channel_id) for channel_id in normalized),
            )

    def get_all_group_memberships(self) -> Dict[int, List[int]]:
        rows = self._fetchall(
            "SELECT group_id, channel_id FROM channel_group_members ORDER BY group_id, channel_id"
        )
        mapping: Dict[int, List[int]] = defaultdict(list)
        for row in rows:
            mapping[row["group_id"]].append(row["channel_id"])
        return mapping

    def get_groups_for_channel(self, channel_id: int) -> List[ChannelGroupRecord]:
        rows = self._fetchall(SQL_GROUPS_FOR_CHANNEL, (channel_id,))
        return [
            ChannelGroupRecord(
                id=row["id"],
                title=row["title"],
                description=row["description"],
                channel_count=row["channel_count"],
            )
            for row in rows
        ]

    def get_channel_groups_map(self) -> Dict[int, List[ChannelGroupRecord]]:
        groups = {group.id: group for group in self.list_channel_groups()}
        rows = self._fetchall("SELECT group_id, channel_id FROM channel_group_members ORDER BY channel_id, group_id")
        mapping: Dict[int, List[ChannelGroupRecord]] = defaultdict(list)
        for row in rows:
            group = groups.get(row["group_id"])
            if group:
                mapping[row["channel_id"]].append(group)
        return mapping

    def get_group_query_assignments(self, group_id: int) -> Dict[int, int]:
        rows = self._fetchall(SQL_GROUP_QUERY_ASSIGNMENTS, (group_id,))
        return {row["query_id"]: row["cnt"] for row in rows}

    def set_group_queries(self, group_id: int, query_ids: Sequence[int]) -> None:
        normalized_queries = self._normalize_ids(query_ids)
        channel_ids = self.get_channel_ids_for_group(group_id)
        if not channel_ids:
            return
        placeholders = ",".join("?" for _ in channel_ids)
        existing_rows = self._fetchall(
            f"SELECT channel_id, query_id FROM channel_queries WHERE channel_id IN ({placeholders})",
            tuple(channel_ids),
        )
        existing_pairs: Set[Tuple[int, int]] = {(row["channel_id"], row["query_id"]) for row in existing_rows}
        desired_pairs: Set[Tuple[int, int]] = {
            (channel_id, query_id) for channel_id in channel_ids for query_id in normalized_queries
        }
        allowed_queries = set(normalized_queries)
        to_add = sorted(desired_pairs - existing_pairs)
        if allowed_queries:
            to_remove = sorted((cid, qid) for (cid, qid) in existing_pairs if qid not in allowed_queries)
        else:
            to_remove = sorted(existing_pairs)
        if to_add:
            self._executemany(
                "INSERT INTO channel_queries (channel_id, query_id) VALUES (?, ?)",
                to_add,
            )
        if to_remove:
            self._executemany(
                "DELETE FROM channel_queries WHERE channel_id = ? AND query_id = ?",
                to_remove,
            )
        self._reload_assignment_cache()

    # region blocked messages ------------------------------------------
    def _reload_blocked_messages_cache(self) -> None:
        rows = self._fetchall("SELECT id, sample, author_id FROM blocked_messages WHERE author_id IS NOT NULL")
        entries: List[BlockedMessageEntry] = []
        for row in rows:
            sample = row["sample"] or ""
            token_sorted = sorted_tokens(sample)
            entry = BlockedMessageEntry(
                id=row["id"],
                author_id=row["author_id"],
                hash=hashlib.sha256(sample.encode()).hexdigest(),
                token_sorted=token_sorted,
                length=len(token_sorted),
            )
            entries.append(entry)
        self._blocked_entries = entries

    def add_blocked_message(self, sample: str, author_id: int | None = None) -> tuple[bool, BlockedMessageEntry]:
        cleaned = (sample or "").strip()
        if not cleaned:
            raise ValueError("Нельзя заблокировать пустой текст")
        if author_id is None:
            raise ValueError("author_id обязателен для игнора")
        truncated = cleaned[:2048]
        row = self._fetchone("SELECT id FROM blocked_messages WHERE author_id = ?", (author_id,))
        created = False
        if row:
            entry_id = row["id"]
            self._execute("UPDATE blocked_messages SET sample = ? WHERE id = ?", (truncated, entry_id))
        else:
            cur = self._execute(
                "INSERT INTO blocked_messages (sample, author_id) VALUES (?, ?)",
                (truncated, author_id),
            )
            entry_id = int(cur.lastrowid)
            created = True
        token_sorted = sorted_tokens(truncated)
        entry = BlockedMessageEntry(
            id=entry_id,
            author_id=author_id,
            hash=hashlib.sha256(truncated.encode()).hexdigest(),
            token_sorted=token_sorted,
            length=len(token_sorted),
        )
        # refresh in-memory cache incrementally
        self._blocked_entries = [e for e in self._blocked_entries if e.author_id != author_id]
        self._blocked_entries.append(entry)
        return created, entry

    def remove_blocked_message(self, entry_id: int) -> BlockedMessageEntry | None:
        row = self._fetchone("SELECT id, sample, author_id FROM blocked_messages WHERE id = ?", (entry_id,))
        if not row:
            return None
        self._execute("DELETE FROM blocked_messages WHERE id = ?", (entry_id,))
        self._blocked_entries = [e for e in self._blocked_entries if e.id != entry_id]
        sample = row["sample"] or ""
        tokens = sorted_tokens(sample)
        return BlockedMessageEntry(
            id=row["id"],
            author_id=row["author_id"],
            hash=hashlib.sha256(sample.encode()).hexdigest(),
            token_sorted=tokens,
            length=len(tokens),
        )

    def update_blocked_message(
            self,
            entry_id: int,
            *,
            sample: str | None = None,
            author_id: int | None = None,
    ) -> None:
        updates = []
        params: list = []
        new_sample = None
        if sample is not None:
            cleaned = sample.strip()
            if cleaned:
                updates.append("sample = ?")
                params.append(cleaned[:2048])
                new_sample = cleaned[:2048]
            else:
                new_sample = None
        if author_id is not None:
            updates.append("author_id = ?")
            params.append(author_id)
        if not updates:
            return
        params.append(entry_id)
        self._execute(f"UPDATE blocked_messages SET {', '.join(updates)} WHERE id = ?", tuple(params))
        # Update in-memory cache incrementally.
        updated_entries: list[BlockedMessageEntry] = []
        for entry in self._blocked_entries:
            if entry.id != entry_id:
                updated_entries.append(entry)
                continue
            if sample is not None and new_sample:
                tokens = sorted_tokens(new_sample)
                updated_entries.append(
                    BlockedMessageEntry(
                        id=entry.id,
                        author_id=author_id if author_id is not None else entry.author_id,
                        hash=hashlib.sha256(new_sample.encode()).hexdigest(),
                        token_sorted=tokens,
                        length=len(tokens),
                    )
                )
            else:
                updated_entries.append(
                    BlockedMessageEntry(
                        id=entry.id,
                        author_id=author_id if author_id is not None else entry.author_id,
                        hash=entry.hash,
                        token_sorted=entry.token_sorted,
                        length=entry.length,
                    )
                )
        self._blocked_entries = updated_entries

    def list_blocked_messages(self, limit: int = 100) -> List[Dict[str, str]]:
        rows = self._fetchall(
            """
            SELECT id, sample, author_id, created_at
            FROM blocked_messages
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, limit),),
        )
        return [
            {
                "id": row["id"],
                "sample": row["sample"],
                "author_id": row["author_id"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_blocked_entries(self) -> Tuple[BlockedMessageEntry, ...]:
        return tuple(self._blocked_entries)

    def _reload_assignment_cache(self) -> None:
        from service import search_engine as se  # local import to avoid circular dependency during module load

        rows = self._fetchall(SQL_ASSIGNMENTS_FOR_CACHE)
        channel_queries: Dict[int, List[int]] = defaultdict(list)
        query_phrases: Dict[int, str] = {}
        for row in rows:
            qid = int(row["query_id"])
            channel_queries[int(row["channel_id"])].append(qid)
            query_phrases[qid] = row["phrase"]

        # Build unique query entries once (tokens are shared across channels).
        entries: Dict[int, QuerySearchEntry] = {}
        for qid, phrase in query_phrases.items():
            tokens, clauses = se.parse_query_phrase(phrase)
            entries[qid] = QuerySearchEntry(id=qid, phrase=phrase, tokens=tuple(tokens), clauses=clauses)
        self._query_entries = entries

        # Build per-channel search contexts with idf and tf-idf maps.
        self._channel_search_ctx = {}
        for chat_id, qids in channel_queries.items():
            unique_qids = tuple(sorted(set(qids)))
            tokens_list = [entries[qid].tokens for qid in unique_qids if qid in entries]
            if not tokens_list:
                continue
            idf_map = se._build_idf(tokens_list)
            tfidf_map: Dict[int, tuple[tuple[dict[str, float], float], ...]] = {}
            for qid in unique_qids:
                entry = entries.get(qid)
                if not entry:
                    continue
                clause_vectors = tuple(se._tfidf_vector(cl.tokens, idf_map) for cl in entry.clauses)
                tfidf_map[qid] = clause_vectors
            self._channel_search_ctx[chat_id] = ChannelSearchContext(
                query_ids=unique_qids,
                idf_map=idf_map,
                tfidf_map=tfidf_map,
                entries_map=entries,
            )

        # Backwards-compatible phrases per chat for external callers.
        self._queries_by_chat: Dict[int, Tuple[str, ...]] = {
            chat_id: tuple(entries[qid].phrase for qid in ctx.query_ids if qid in entries)
            for chat_id, ctx in self._channel_search_ctx.items()
        }
        self._tracked_chats = set(self._queries_by_chat.keys())

    def get_queries_for_chat(self, chat_id: int) -> Tuple[str, ...]:
        return self._queries_by_chat.get(chat_id, tuple())

    def get_tracked_chat_ids(self) -> Tuple[int, ...]:
        return tuple(self._tracked_chats)

    def get_query_entries(self) -> Dict[int, QuerySearchEntry]:
        return self._query_entries

    def get_channel_search_context(self, chat_id: int) -> ChannelSearchContext | None:
        return self._channel_search_ctx.get(chat_id)
