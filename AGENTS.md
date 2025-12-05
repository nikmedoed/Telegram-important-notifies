# AGENTS

Quick guide for the agent/operator working with the project.

## What the service does
- Monitors Telegram channels/chats, searches for messages using user queries (1–3 words, sometimes more), and forwards matches to the target user.
- Queries may consist of multiple independent clauses (comma separated); mandatory words are prefixed with `+`.
- Runs on weak hardware (ARM Cortex-A7 ~1.3 GHz, 512 MB RAM); priority is low memory usage and fast search.

## Core modules
- `service/search_engine.py` — tokenization, fuzzy/tf-idf search over sentence windows, supports independent clauses and `+` mandatory tokens.
- `service/db/database.py` + `service/db/models.py` — SQLite, caches of search data (`QuerySearchEntry`, `ChannelSearchContext`), `slots=True` and tuples to save RAM.
- `service/main_handler.py` — processes incoming messages, deduplicates, invokes search, forwards results.
- `service/telegram_client.py` — Telethon client initialization (split from config to reduce imports).
- `service/cache.py` — TTL cache with optional `max_items` and a background cleaner.

## How the search works (short version)
- Tokenization/lemmatization with caching (`Cache`), stop words filtered out, `rapidfuzz` used for token comparison.
- No strict word order: bag-of-tokens match with a constraint “one text token → max one query token”, penalty for dispersion (window compactness).
- Fast path: if all query tokens appear consecutively in any order, score = 100.
- TF-IDF is the second signal: build IDF from query tokens, cosine similarity boosts rare words.
- Queries are parsed into clauses ahead of time (comma separated). Each clause is searched independently; final score is the minimum across clauses (all must match).
- `+word` marks a mandatory token in a clause; windows missing it are rejected immediately.

## RAM/performance notes
- Tokenization cache: TTL 2 hours, `max_items=2000` — keeps normalized text tokens.
- Dedup caches in `main_handler` limited by item count to avoid growth.
- `dataclass(..., slots=True)` and tuples in search models reduce per-object overhead.
- Do not start heavy background jobs; write to SD only if necessary (SQLite and caches run in memory).

## Typical run/debug setup
- Required env vars: `TELEGRAM_APP_ID`, `TELEGRAM_API_HASH`, `TARGET_USER`, optional network timeouts (see `service/config.py`).
- Libraries: `telethon`, `rapidfuzz`, `nltk`, `pymorphy3`. Tests need `pytest`/`unittest` (may be absent in the environment).
- On startup the DB/caches load queries, tokenize them once, and build tf-idf for channels.

## What to watch out for
- Any search changes must respect word order independence while keeping compactness impact on score.
- When adding new query logic, update the parser in `parse_query_phrase` and the `ClauseSpec` models.
