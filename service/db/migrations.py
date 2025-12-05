from __future__ import annotations

import threading
from importlib import resources
from pathlib import Path
import hashlib

from .sql import (
    SQL_COPY_CHANNEL_QUERIES_FROM_LEGACY,
    SQL_COPY_CHANNELS_FROM_LEGACY,
    SQL_COPY_GROUP_MEMBERS_FROM_LEGACY,
    SQL_CREATE_CHANNELS_TABLE,
    SQL_CREATE_CHANNEL_GROUP_MEMBERS_TABLE,
    SQL_CREATE_CHANNEL_QUERIES_TABLE,
)


def _exec(conn, lock: threading.RLock, sql: str, params=(), commit: bool = True):
    with lock:
        cur = conn.execute(sql, params)
        if commit:
            conn.commit()
        return cur


def _column_exists(conn, lock: threading.RLock, table: str, column: str) -> bool:
    rows = _exec(conn, lock, f"PRAGMA table_info({table})", commit=False).fetchall()
    return any(row["name"] == column for row in rows)


def _table_exists(conn, lock: threading.RLock, table: str) -> bool:
    row = _exec(conn, lock, "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,), commit=False).fetchone()
    return bool(row)


def ensure_schema(conn, lock: threading.RLock, db_dir: Path) -> None:
    schema_resource = resources.files("service.db").joinpath("schema.sql")
    schema_copy = db_dir / "schema.sql"
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
    with lock:
        conn.executescript(schema_sql)
        conn.commit()


def _refresh_channel_relationship_tables(conn, lock: threading.RLock, *, foreign_keys_disabled: bool = False) -> None:
    with lock:
        if not foreign_keys_disabled:
            conn.execute("PRAGMA foreign_keys=OFF;")
        try:
            if _table_exists(conn, lock, "channel_queries"):
                conn.execute("ALTER TABLE channel_queries RENAME TO legacy_channel_queries")
                conn.execute(SQL_CREATE_CHANNEL_QUERIES_TABLE)
                conn.execute(SQL_COPY_CHANNEL_QUERIES_FROM_LEGACY)
                conn.execute("DROP TABLE legacy_channel_queries")

            if _table_exists(conn, lock, "channel_group_members"):
                conn.execute("ALTER TABLE channel_group_members RENAME TO legacy_channel_group_members")
                conn.execute(SQL_CREATE_CHANNEL_GROUP_MEMBERS_TABLE)
                conn.execute(SQL_COPY_GROUP_MEMBERS_FROM_LEGACY)
                conn.execute("DROP TABLE legacy_channel_group_members")
        finally:
            if not foreign_keys_disabled:
                conn.execute("PRAGMA foreign_keys=ON;")
            conn.commit()


def _create_blocked_messages_table(conn, lock: threading.RLock) -> None:
    _exec(
        conn,
        lock,
        """
        CREATE TABLE IF NOT EXISTS blocked_messages
        (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            sample     TEXT NOT NULL,
            author_id  INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )


def _migrate_blocked_messages_table(conn, lock: threading.RLock) -> None:
    has_hash = _column_exists(conn, lock, "blocked_messages", "hash")
    has_sample_hash = _column_exists(conn, lock, "blocked_messages", "sample_hash")
    has_author = _column_exists(conn, lock, "blocked_messages", "author_id")
    has_id = _column_exists(conn, lock, "blocked_messages", "id")
    has_created_at = _column_exists(conn, lock, "blocked_messages", "created_at")

    # If hash/sample_hash columns exist, rebuild table without them.
    if has_hash or has_sample_hash:
        _exec(conn, lock, """
                          CREATE TABLE IF NOT EXISTS blocked_messages_new
                          (
                              id         INTEGER PRIMARY KEY AUTOINCREMENT,
                              sample     TEXT NOT NULL,
                              author_id  INTEGER,
                              created_at TEXT DEFAULT CURRENT_TIMESTAMP
                          )
                          """)
        try:
            select_columns = [
                col
                for col, present in (
                    ("id", has_id),
                    ("sample", True),
                    ("author_id", has_author),
                    ("created_at", has_created_at),
                )
                if present
            ]
            rows = _exec(
                conn,
                lock,
                f"SELECT {', '.join(select_columns)} FROM blocked_messages",
                commit=False,
            ).fetchall()
            for row in rows:
                author_val = row["author_id"] if has_author else None
                insert_columns = ["sample", "author_id"]
                insert_values = [row["sample"], author_val]
                if has_created_at:
                    insert_columns.append("created_at")
                    insert_values.append(row["created_at"])
                placeholders = ", ".join(["?"] * len(insert_columns))
                column_list = ", ".join(insert_columns)
                if has_id:
                    column_list = "id, " + column_list
                    placeholders = "?, " + placeholders
                    insert_values = [row["id"]] + insert_values
                _exec(
                    conn,
                    lock,
                    f"INSERT INTO blocked_messages_new ({column_list}) VALUES ({placeholders})",
                    tuple(insert_values),
                )
            _exec(conn, lock, "DROP TABLE blocked_messages")
            _exec(conn, lock, "ALTER TABLE blocked_messages_new RENAME TO blocked_messages")
        finally:
            with lock:
                conn.commit()


def _ensure_blocked_author_index(conn, lock: threading.RLock) -> None:
    _exec(
        conn,
        lock,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_blocked_messages_author
            ON blocked_messages (author_id)
            WHERE author_id IS NOT NULL
        """,
    )


def _remove_last_seen_column(conn, lock: threading.RLock) -> None:
    with lock:
        conn.execute("PRAGMA foreign_keys=OFF;")
        try:
            conn.execute("ALTER TABLE channels RENAME TO legacy_channels")
            conn.execute(SQL_CREATE_CHANNELS_TABLE)
            conn.execute(SQL_COPY_CHANNELS_FROM_LEGACY)
            _refresh_channel_relationship_tables(conn, lock, foreign_keys_disabled=True)
            conn.execute("DROP TABLE legacy_channels")
        finally:
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.commit()


def apply_migrations(conn, lock: threading.RLock) -> None:
    if _column_exists(conn, lock, "channels", "last_seen"):
        _remove_last_seen_column(conn, lock)
    for table in ("channel_queries", "channel_group_members"):
        if not _table_exists(conn, lock, table):
            continue
        rows = _exec(conn, lock, f"PRAGMA foreign_key_list({table})", commit=False).fetchall()
        if any(row["table"] == "legacy_channels" for row in rows):
            _refresh_channel_relationship_tables(conn, lock)
            break
    if not _table_exists(conn, lock, "blocked_messages"):
        _create_blocked_messages_table(conn, lock)
    else:
        _migrate_blocked_messages_table(conn, lock)
    _ensure_blocked_author_index(conn, lock)


def run_migrations(conn, lock: threading.RLock, db_dir: Path) -> None:
    ensure_schema(conn, lock, db_dir)
    apply_migrations(conn, lock)
