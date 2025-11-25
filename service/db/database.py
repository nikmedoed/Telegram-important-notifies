from __future__ import annotations

import sqlite3
import threading
from collections import defaultdict
from importlib import resources
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set, Tuple

from service.bootstrap import bootstrap_from_legacy_files
from service.config import data_directory
from .models import (
    ChannelGroupRecord,
    ChannelRecord,
    QueryRecord,
    QuerySearchEntry,
    ChannelSearchContext,
)
from .sql import *


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
        self._ensure_schema()
        self._apply_migrations()
        self._bootstrap_from_legacy_files()
        self._query_entries: Dict[int, QuerySearchEntry] = {}
        self._channel_search_ctx: Dict[int, ChannelSearchContext] = {}
        self._reload_assignment_cache()
        self._blocked_hashes: Set[str] = set()
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

    # region schema + migrations ----------------------------------------
    def _ensure_schema(self) -> None:
        schema_resource = resources.files("service.db").joinpath("schema.sql")
        schema_copy = self._db_dir / "schema.sql"
        if schema_copy.exists():
            try:
                schema_sql = schema_copy.read_text(encoding="utf-8")
            except OSError:
                schema_sql = schema_resource.read_text(encoding="utf-8")
        else:
            schema_sql = schema_resource.read_text(encoding="utf-8")
            try:
                schema_copy.write_text(schema_sql, encoding="utf-8")
            except OSError:
                pass
        with self._lock:
            self._conn.executescript(schema_sql)
            self._conn.commit()

    def _bootstrap_from_legacy_files(self) -> None:
        with self._lock:
            bootstrap_from_legacy_files(self._conn, data_directory)

    def _apply_migrations(self) -> None:
        if self._column_exists("channels", "last_seen"):
            self._remove_last_seen_column()
        if self._channel_relationships_reference_legacy_channels():
            self._refresh_channel_relationship_tables()
        if not self._table_exists("blocked_messages"):
            self._create_blocked_messages_table()

    def _column_exists(self, table: str, column: str) -> bool:
        rows = self._fetchall(f"PRAGMA table_info({table})")
        return any(row["name"] == column for row in rows)

    def _table_exists(self, table: str) -> bool:
        row = self._fetchone(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        )
        return bool(row)

    def _channel_relationships_reference_legacy_channels(self) -> bool:
        def _references_legacy(table: str) -> bool:
            if not self._table_exists(table):
                return False
            rows = self._fetchall(f"PRAGMA foreign_key_list({table})")
            return any(row["table"] == "legacy_channels" for row in rows)

        return any(
            _references_legacy(table)
            for table in ("channel_queries", "channel_group_members")
        )

    def _refresh_channel_relationship_tables(self, foreign_keys_disabled: bool = False) -> None:
        with self._lock:
            if not foreign_keys_disabled:
                self._conn.execute("PRAGMA foreign_keys=OFF;")
            try:
                if self._table_exists("channel_queries"):
                    self._conn.execute("ALTER TABLE channel_queries RENAME TO legacy_channel_queries")
                    self._conn.execute(SQL_CREATE_CHANNEL_QUERIES_TABLE)
                    self._conn.execute(SQL_COPY_CHANNEL_QUERIES_FROM_LEGACY)
                    self._conn.execute("DROP TABLE legacy_channel_queries")

                if self._table_exists("channel_group_members"):
                    self._conn.execute("ALTER TABLE channel_group_members RENAME TO legacy_channel_group_members")
                    self._conn.execute(SQL_CREATE_CHANNEL_GROUP_MEMBERS_TABLE)
                    self._conn.execute(SQL_COPY_GROUP_MEMBERS_FROM_LEGACY)
                    self._conn.execute("DROP TABLE legacy_channel_group_members")
            finally:
                if not foreign_keys_disabled:
                    self._conn.execute("PRAGMA foreign_keys=ON;")
                self._conn.commit()

    def _create_blocked_messages_table(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS blocked_messages (
                    hash TEXT PRIMARY KEY,
                    sample TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._conn.commit()

    def _remove_last_seen_column(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys=OFF;")
            try:
                self._conn.execute("ALTER TABLE channels RENAME TO legacy_channels")
                self._conn.execute(SQL_CREATE_CHANNELS_TABLE)
                self._conn.execute(SQL_COPY_CHANNELS_FROM_LEGACY)
                self._refresh_channel_relationship_tables(foreign_keys_disabled=True)
                self._conn.execute("DROP TABLE legacy_channels")
            finally:
                self._conn.execute("PRAGMA foreign_keys=ON;")
                self._conn.commit()

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

    # region metadata + cache -------------------------------------------
    def set_metadata(self, key: str, value: str) -> None:
        self._execute(
            "INSERT INTO metadata(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def get_metadata(self, key: str) -> str | None:
        row = self._fetchone("SELECT value FROM metadata WHERE key = ?", (key,))
        return row["value"] if row else None

    # region blocked messages ------------------------------------------
    def _reload_blocked_messages_cache(self) -> None:
        rows = self._fetchall("SELECT hash FROM blocked_messages")
        self._blocked_hashes = {row["hash"] for row in rows}

    def is_message_blocked(self, message_hash: str) -> bool:
        return message_hash in self._blocked_hashes

    def add_blocked_message(self, message_hash: str, sample: str) -> bool:
        cleaned = (sample or "").strip()
        if not cleaned:
            raise ValueError("Нельзя заблокировать пустой текст")
        truncated = cleaned[:2048]
        cur = self._execute(
            """
            INSERT INTO blocked_messages (hash, sample)
            VALUES (?, ?)
            ON CONFLICT(hash) DO NOTHING
            """,
            (message_hash, truncated),
        )
        created = cur.rowcount > 0
        if created:
            self._blocked_hashes.add(message_hash)
        return created

    def remove_blocked_message(self, message_hash: str) -> bool:
        cur = self._execute("DELETE FROM blocked_messages WHERE hash = ?", (message_hash,))
        removed = cur.rowcount > 0
        if removed:
            self._blocked_hashes.discard(message_hash)
        return removed

    def list_blocked_messages(self, limit: int = 100) -> List[Dict[str, str]]:
        rows = self._fetchall(
            """
            SELECT hash, sample, created_at
            FROM blocked_messages
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, limit),),
        )
        return [
            {"hash": row["hash"], "sample": row["sample"], "created_at": row["created_at"]}
            for row in rows
        ]

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
