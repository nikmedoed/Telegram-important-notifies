from __future__ import annotations

from collections import defaultdict
from typing import List

from rapidfuzz import fuzz


class IgnoreMatcher:
    """In-memory matcher for blocked messages with author scoping."""

    def __init__(
            self,
            db,
            similarity_threshold: int = 90,
            global_similarity_threshold: int = 97,
            global_min_tokens: int = 12,
    ) -> None:
        self._db = db
        self.similarity_threshold = similarity_threshold
        self.global_similarity_threshold = global_similarity_threshold
        self.global_min_tokens = global_min_tokens
        self._entries_by_author: dict[int, List[dict]] = defaultdict(list)
        self._entries_all: list[dict] = []
        # Initialize with provided entries or pull current ones from db.
        for entry in db.get_blocked_entries():
            self.add_entry(entry)

    @staticmethod
    def _token_count(token_sorted: str) -> int:
        return len(token_sorted.split()) if token_sorted else 0

    def _resort(self) -> None:
        for bucket in self._entries_by_author.values():
            bucket.sort(key=lambda e: e["token_count"])
        self._entries_all.sort(key=lambda e: e["token_count"])

    def add_entry(self, entry) -> None:
        """Add or replace entry for author without wiping the whole cache."""
        if entry.author_id is None:
            return
        bucket = self._entries_by_author.setdefault(entry.author_id, [])
        if any(existing["id"] == entry.id for existing in self._entries_all):
            return
        payload = {
            "id": entry.id,
            "author_id": entry.author_id,
            "hash": entry.hash,
            "token_sorted": entry.token_sorted,
            "length": entry.length,
            "token_count": self._token_count(entry.token_sorted),
        }
        bucket.append(payload)
        self._entries_all.append(payload)
        self._resort()

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
        self._entries_all = [e for e in self._entries_all if e["id"] != entry_id]

    def _match_candidates(self, candidates: List[dict], prepared: dict, message_hash: str, threshold: int) -> bool:
        if not candidates:
            return False

        tokens = prepared["token_sorted"]
        pcount = self._token_count(tokens)
        lower_bound = pcount / 1.1
        upper_bound = pcount / 0.9

        for entry in candidates:
            token_count = entry["token_count"]
            if token_count < lower_bound:
                continue
            if token_count > upper_bound:
                break
            if message_hash == entry["hash"]:
                return True
            score = fuzz.ratio(tokens, entry["token_sorted"])
            if score >= threshold:
                merged = " ".join(sorted({*entry["token_sorted"].split(), *tokens.split()}))
                merged_token_count = self._token_count(merged)
                if merged != entry["token_sorted"] or merged_token_count > entry["token_count"]:
                    entry["token_sorted"] = merged
                    entry["length"] = len(merged)
                    entry["token_count"] = merged_token_count
                    self._db.update_blocked_message(
                        entry["id"],
                        sample=prepared['raw'],
                        author_id=entry["author_id"],
                    )
                    self._resort()
                return True
        return False

    def check(self, prepared: dict, message_hash: str, author_id: int) -> bool:
        candidates = self._entries_by_author.get(author_id)
        if self._match_candidates(candidates, prepared, message_hash, self.similarity_threshold):
            return True

        # Telegram can expose different sender identifiers for the same ad
        # depending on forward/privacy mode. For long near-identical texts,
        # fall back to a stricter global match to avoid missed ignores.
        if self._token_count(prepared["token_sorted"]) < self.global_min_tokens:
            return False
        return self._match_candidates(self._entries_all, prepared, message_hash, self.global_similarity_threshold)
