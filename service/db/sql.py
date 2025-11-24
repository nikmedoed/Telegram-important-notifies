SQL_LIST_QUERIES = """
    SELECT q.id, q.phrase, COUNT(cq.channel_id) AS channel_count
    FROM queries q
    LEFT JOIN channel_queries cq ON cq.query_id = q.id
    GROUP BY q.id
    ORDER BY q.created_at DESC, q.id DESC
"""

SQL_GET_QUERY = """
    SELECT q.id, q.phrase, COUNT(cq.channel_id) AS channel_count
    FROM queries q
    LEFT JOIN channel_queries cq ON cq.query_id = q.id
    WHERE q.id = ?
    GROUP BY q.id
"""

SQL_CHANNEL_IDS_FOR_QUERY = """
    SELECT channel_id
    FROM channel_queries
    WHERE query_id = ?
    ORDER BY channel_id
"""

SQL_LIST_CHANNELS = """
    SELECT id, title, invite_link, username, kind
    FROM channels
    ORDER BY COALESCE(NULLIF(title, ''), CAST(id AS TEXT)) COLLATE NOCASE
"""

SQL_UPSERT_CHANNELS = """
    INSERT INTO channels (id, title, invite_link, username, kind)
    VALUES (:id, :title, :invite_link, :username, :kind)
    ON CONFLICT(id) DO UPDATE SET
        title = excluded.title,
        invite_link = excluded.invite_link,
        username = excluded.username,
        kind = excluded.kind
"""

SQL_GET_CHANNEL = """
    SELECT id, title, invite_link, username, kind
    FROM channels
    WHERE id = ?
"""

SQL_QUERY_IDS_FOR_CHANNEL = """
    SELECT query_id
    FROM channel_queries
    WHERE channel_id = ?
    ORDER BY query_id
"""

SQL_LIST_GROUPS = """
    SELECT g.id, g.title, g.description, COUNT(m.channel_id) AS channel_count
    FROM channel_groups g
    LEFT JOIN channel_group_members m ON m.group_id = g.id
    GROUP BY g.id
    ORDER BY g.title COLLATE NOCASE, g.id
"""

SQL_GET_GROUP = """
    SELECT g.id, g.title, g.description, COUNT(m.channel_id) AS channel_count
    FROM channel_groups g
    LEFT JOIN channel_group_members m ON m.group_id = g.id
    WHERE g.id = ?
    GROUP BY g.id
"""

SQL_GROUP_CHANNEL_IDS = """
    SELECT channel_id
    FROM channel_group_members
    WHERE group_id = ?
    ORDER BY channel_id
"""

SQL_GROUPS_FOR_CHANNEL = """
    SELECT g.id, g.title, g.description, COUNT(m2.channel_id) AS channel_count
    FROM channel_groups g
    JOIN channel_group_members m ON m.group_id = g.id
    LEFT JOIN channel_group_members m2 ON m2.group_id = g.id
    WHERE m.channel_id = ?
    GROUP BY g.id
    ORDER BY g.title COLLATE NOCASE, g.id
"""

SQL_GROUP_QUERY_ASSIGNMENTS = """
    SELECT cq.query_id, COUNT(*) AS cnt
    FROM channel_queries cq
    WHERE cq.channel_id IN (
        SELECT channel_id FROM channel_group_members WHERE group_id = ?
    )
    GROUP BY cq.query_id
"""

SQL_CREATE_CHANNEL_QUERIES_TABLE = """
    CREATE TABLE channel_queries (
        channel_id INTEGER NOT NULL,
        query_id INTEGER NOT NULL,
        PRIMARY KEY (channel_id, query_id),
        FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE,
        FOREIGN KEY (query_id) REFERENCES queries(id) ON DELETE CASCADE
    )
"""

SQL_COPY_CHANNEL_QUERIES_FROM_LEGACY = """
    INSERT INTO channel_queries (channel_id, query_id)
    SELECT channel_id, query_id FROM legacy_channel_queries
"""

SQL_CREATE_CHANNEL_GROUP_MEMBERS_TABLE = """
    CREATE TABLE channel_group_members (
        group_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        PRIMARY KEY (group_id, channel_id),
        FOREIGN KEY (group_id) REFERENCES channel_groups(id) ON DELETE CASCADE,
        FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
    )
"""

SQL_COPY_GROUP_MEMBERS_FROM_LEGACY = """
    INSERT INTO channel_group_members (group_id, channel_id)
    SELECT group_id, channel_id FROM legacy_channel_group_members
"""

SQL_CREATE_CHANNELS_TABLE = """
    CREATE TABLE channels (
        id INTEGER PRIMARY KEY,
        title TEXT,
        invite_link TEXT,
        username TEXT,
        kind TEXT
    )
"""

SQL_COPY_CHANNELS_FROM_LEGACY = """
    INSERT INTO channels (id, title, invite_link, username, kind)
    SELECT id, title, invite_link, username, kind FROM legacy_channels
"""
SQL_ASSIGNMENTS_FOR_CACHE = """
    SELECT cq.channel_id, cq.query_id, q.phrase
    FROM channel_queries cq
    JOIN queries q ON q.id = cq.query_id
    ORDER BY cq.channel_id
"""
