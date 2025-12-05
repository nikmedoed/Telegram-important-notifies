# AGENTS

Quick reference for engineers operating the Telegram important notifications service.

## Purpose & Overall Flow
- The daemon monitors configured Telegram chats/channels, searches message text with fuzzy multi-clause queries, and forwards matches to `TARGET_USER`, together with a score explanation and a deep link to the source message.
- The service targets single-board computers (ARM Cortex-A7 ~1.3 GHz, 512 MB RAM). Every change must preserve low memory usage, minimal disk writes, and short critical sections so Telethon callbacks stay responsive.
- Startup flow (`main.py`):
  1. Instantiate a long-lived Telethon client (`service/telegram_client.py`) that blocks until basic network connectivity is confirmed.
  2. Register handlers for albums, regular messages, and control messages (`service/main_handler.py`).
  3. Launch the aiohttp-based web UI (`service/web`) on `WEB_HOST:WEB_PORT`.
  4. Sync the list of dialogs into SQLite (`service/channel_sync.py`) and process unread history (`service/process_history.py`) before entering `client.run_until_disconnected()`.
- Channel metadata stays warm via raw update listeners (`service/channel_updates.py`) so IDs/titles remain current even when Telegram renames chats.

## Key Modules
- `service/main_handler.py` — Cleans and deduplicates messages, checks ignores, executes fuzzy search, forwards matches, and posts match summaries to the target chat inside a mutex to keep albums atomic. Provides duplicate caches:
  - `duplicate_cache`: exact SHA256 hash cache (TTL 15 min, max 5000 items).
  - `advanced_duplicate_cache`: per-sender similarity cache (TTL 15 min) that reuses sorted tokens to drop near-duplicates (93%+ similarity, <=10% length delta).
- `service/search_engine.py` — Tokenization (nltk + pymorphy3) with a 24h cached normalization (`Cache(max_items=5000)`), bag-of-tokens scoring with compactness penalty, tf-idf signal per clause, required tokens via `+word`, and `ClauseSpec` definitions shared by all channels.
- `service/db/database.py` — Owns the SQLite database under `data/app.db`, performs migrations (`service/db/migrations.py`), bootstraps from legacy `data/queries` & `data/chats` files when tables are empty, and keeps in-memory caches:
  - `QuerySearchEntry` and `ChannelSearchContext` built from the latest channel-query assignments (stored again whenever queries/channels change).
  - Blocked messages cache keyed by `author_id`, supplying `IgnoreMatcher`.
  - Channel groups, memberships, query assignments for bulk operations in the web UI.
- `service/ignore_matcher.py` — Author-scoped fuzzy ignore list. Messages can be added by replying “нет” to a forwarded message (handled in `handle_control_message`) or via the `/cache` web form.
- `service/process_history.py` — Walks unread history for tracked chats, batching grouped media before replaying them through the regular handler path.
- `service/channel_sync.py` & `service/channel_updates.py` — Pull current dialogs (respecting invite links/usernames when possible), classify kind (`chat`, `supergroup`, `channel`, etc.), and keep the `channels` table up-to-date. The web UI exposes `/channels/refresh` to run the sync.
- `service/web` — aiohttp + Jinja2 admin console:
  - `/` & `/queries/*`: CRUD for search phrases and channel assignments.
  - `/channels/*`: Inspect per-channel query bindings and group membership.
  - `/groups/*`: Manage channel groups and propagate queries to every member via `set_group_queries`.
  - `/cache`: Inspect runtime caches, dump ignored samples, add/remove ignore rules.
  - Templates live under `service/web/templates`, static assets under `service/web/static`.

## Search & Matching Notes
- Queries are comma-separated clauses. Each clause becomes a `ClauseSpec(tokens, required)` where `+token` indicates a compulsory normalized token; windows missing any required token are discarded immediately.
- Token matching is bag-based: each text token can serve at most one query token, compactness is enforced via span penalties, and a fast path returns 100 when a contiguous permutation exists.
- tf-idf is computed from tokens of all clauses assigned to the same channel. Clause scores blend bag-of-tokens, phrase similarity, and tf-idf; the final score for a query is the minimum across its clauses. Threshold to alert is 55+.
- If you change tokenization, thresholds, or clause parsing you **must** keep `parse_query_phrase`, `ClauseSpec`, and cache rebuilding in sync; otherwise the DB’s cached vectors will go stale and cause silent misses.

## Data Layer & Cache Management
- SQLite runs in WAL mode with foreign keys enabled. All write operations take an internal `RLock`; avoid long transactions or heavy queries inside Telethon callbacks.
- Main tables:
  - `queries`, `channels`, `channel_queries` for assignments.
  - `channel_groups`, `channel_group_members` for bulk mappings.
  - `blocked_messages` for per-author ignores.
  - `channel_metadata` tables created by migrations (see `service/db/sql.py`).
- The database caches live in-process; after any structural update call the provided setters (`set_query_channels`, `set_channel_group_members`, `set_group_queries`, etc.) so `_reload_assignment_cache()` runs and search contexts stay accurate.
- The `/cache` page surfaces telemetry for `duplicate_cache`, `advanced_duplicate_cache`, and the tokenizer cache. Use it to inspect current dedupe behavior or to promote a cached entry into the ignore list.

## Runtime Operations
- Required environment variables (see `service/config.py`):
  - `TELEGRAM_APP_ID`, `TELEGRAM_API_HASH`, `TARGET_USER`.
  - Optional overrides: `TELEGRAM_RETRY_DELAY_SECONDS`, `TELEGRAM_NETWORK_CHECK_HOST|PORT|TIMEOUT`, `WEB_HOST`, `WEB_PORT`.
- Long-running deployment steps:
  1. `python -m venv .venv && .venv\\Scripts\\activate`.
  2. `pip install -r requirements.txt`.
  3. Provide secrets via `.env` or the process environment.
  4. Run `python main.py`, complete the first Telethon login, confirm the “Client started” log and the greeting sent to `TARGET_USER`.
- If you need new chats:
  1. Run the service so Telethon sees the dialogs.
  2. Use `/channels/refresh` or call `sync_channels_with_client()` in a shell to persist them.
  3. Assign queries individually (`/channels/{id}`) or via a group (`/groups/{id}`) before expecting hits.
- Control chat commands:
  - Reply “нет” to any forwarded message to bind an ignore sample to its original author.
  - The bot confirms whether the rule was newly created or updated; see `/cache` to review.

## Performance & Reliability Tips
- Keep allocations tight: most dataclasses in the DB layer use `slots=True` and tuples to reduce per-object overhead. Respect this pattern when adding new records.
- Tokenizer cache TTL is 24h with `max_items=5000`; large query additions may require a manual restart to rebuild IDF maps quickly.
- Do not introduce background jobs that might compete with Telethon’s event loop; everything heavy (nltk downloads, migrations) should happen during startup while the mutex is not contended.
- When tweaking search thresholds, validate that order independence remains: compactness should still influence the score, but the window logic must not force strict sequences.
- Before deploying new query syntax, extend both `parse_query_phrase` and downstream consumers (DB cache builder, templates, forms) so operators can configure the feature via the UI.

## Troubleshooting Checklist
- **No matches arrive:** verify `/channels/{id}` shows queries, `/cache` shows recent tokenizer entries, and `data/app.db` contains `channel_queries` rows; rebuild caches by toggling any assignment to trigger `_reload_assignment_cache()`.
- **High duplication:** inspect `duplicate_cache` via `/cache` and ensure album events hit the album handler (grouped media uses `events.Album`).
- **Unexpected ignores:** look at `/cache` → “ignored messages” or dump `blocked_messages` to confirm the per-author sample that fired; remove via the UI or `db.remove_blocked_message`.
- **Channel missing in UI:** run `/channels/refresh`; if still absent, check Telethon permissions (bot must have dialog access and, for invite links, admin rights).
- **Web UI unavailable:** confirm `WEB_HOST`, `WEB_PORT`, and that aiohttp server started (log entry “Web UI listening…”). The server runs inside the same loop, so blocking handlers will also freeze the UI.

Keep this document updated whenever you touch search behavior, ignore logic, or operational tooling—the on-call engineer relies on these notes during incidents.
