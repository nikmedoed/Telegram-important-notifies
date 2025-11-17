from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, List


def _read_queries(queries_file: Path) -> Iterable[str]:
    return [
        line.strip()
        for line in queries_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _read_chat_ids(chats_file: Path) -> List[int]:
    ids: List[int] = []
    for chunk in chats_file.read_text(encoding="utf-8").split():
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.append(int(chunk))
        except ValueError:
            continue
    return ids


def bootstrap_from_legacy_files(conn: sqlite3.Connection, data_dir: str) -> None:
    chats_file = Path(data_dir) / "chats"
    queries_file = Path(data_dir) / "queries"

    query_count = conn.execute("SELECT COUNT(1) FROM queries").fetchone()[0]
    channel_count = conn.execute("SELECT COUNT(1) FROM channels").fetchone()[0]
    mapping_count = conn.execute("SELECT COUNT(1) FROM channel_queries").fetchone()[0]

    if query_count == 0 and queries_file.exists():
        phrases = _read_queries(queries_file)
        if phrases:
            conn.executemany("INSERT INTO queries (phrase) VALUES (?)", ((p,) for p in phrases))
            query_count = len(phrases)

    if channel_count == 0 and chats_file.exists():
        ids = _read_chat_ids(chats_file)
        if ids:
            conn.executemany(
                """
                INSERT INTO channels (id, title, invite_link, username, kind)
                VALUES (?, ?, ?, ?, ?)
                """,
                ((cid, f"Legacy chat {cid}", None, None, "unknown") for cid in ids),
            )
            channel_count = len(ids)

    if mapping_count == 0 and query_count and channel_count:
        channel_rows = conn.execute("SELECT id FROM channels").fetchall()
        query_rows = conn.execute("SELECT id FROM queries").fetchall()
        conn.executemany(
            "INSERT INTO channel_queries (channel_id, query_id) VALUES (?, ?)",
            ((c[0], q[0]) for c in channel_rows for q in query_rows),
        )

    conn.commit()
