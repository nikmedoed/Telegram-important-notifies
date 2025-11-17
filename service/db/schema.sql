PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phrase TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY,
    title TEXT,
    invite_link TEXT,
    username TEXT,
    kind TEXT
);

CREATE TABLE IF NOT EXISTS channel_queries (
    channel_id INTEGER NOT NULL,
    query_id INTEGER NOT NULL,
    PRIMARY KEY (channel_id, query_id),
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE,
    FOREIGN KEY (query_id) REFERENCES queries(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS channel_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS channel_group_members (
    group_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    PRIMARY KEY (group_id, channel_id),
    FOREIGN KEY (group_id) REFERENCES channel_groups(id) ON DELETE CASCADE,
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
