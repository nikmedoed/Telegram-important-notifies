from __future__ import annotations

from collections import defaultdict
from typing import List

from rapidfuzz import fuzz


class IgnoreMatcher:
    """In-memory matcher for blocked messages with author scoping."""

    def __init__(self, db, similarity_threshold: int = 90) -> None:
        self._db = db
        self.similarity_threshold = similarity_threshold
        self._entries_by_author: dict[int, List[dict]] = defaultdict(list)
        # Initialize with provided entries or pull current ones from db.
        for entry in db.get_blocked_entries():
            self.add_entry(entry)

    def add_entry(self, entry) -> None:
        """Add or replace entry for author without wiping the whole cache."""
        if entry.author_id is None:
            return
        bucket = self._entries_by_author.setdefault(entry.author_id, [])
        bucket.append(
            {
                "id": entry.id,
                "hash": entry.hash,
                "token_sorted": entry.token_sorted,
                "length": entry.length,
            }
        )
        bucket.sort(key=lambda e: e["length"])
        self._entries_by_author[entry.author_id] = bucket

    def remove_entry(self, entry_id: int, author_id: int | None) -> None:
        if author_id is None:
            return
        bucket = self._entries_by_author.get(author_id)
        if not bucket:
            return
        bucket = [e for e in bucket if e["id"] != entry_id]
        if bucket:
            self._entries_by_author[author_id] = bucket
        else:
            self._entries_by_author.pop(author_id, None)

    def check(self, prepared: dict, message_hash: str, author_id: int) -> bool:
        candidates = self._entries_by_author.get(author_id)
        if not candidates:
            return False

        tokens = prepared["token_sorted"]
        plen = prepared["length"]
        lower_bound = plen / 1.1
        upper_bound = plen / 0.9

        for entry in candidates:
            elen = entry["length"]
            if elen < lower_bound:
                continue
            if elen > upper_bound:
                break
            if message_hash == entry["hash"]:
                return True
            score = fuzz.ratio(tokens, entry["token_sorted"])
            if score >= self.similarity_threshold:
                merged = " ".join(sorted({*entry["token_sorted"].split(), *tokens.split()}))
                if merged != entry["token_sorted"] or plen > entry["length"]:
                    entry["token_sorted"] = merged
                    entry["length"] = len(merged)
                    self._db.update_blocked_message(entry["id"], sample=prepared['raw'], author_id=author_id)
                return True
        return False
