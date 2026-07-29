"""
True Classic Bot - Database Layer
Author: Aljay Leodones
Organization: True Classic
"""

import os
import aiosqlite

DB_FILE = os.path.join("data", "bot_database.db")

class Database:
    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        await self._conn.commit()

        await self._create_tables()
        print(f"[Database] Connected to SQLite database at {self.db_path} (WAL mode enabled)")

    async def _create_tables(self):
        queries = [
            """
            CREATE TABLE IF NOT EXISTS onboarded_members (
                user_id      INTEGER NOT NULL,
                guild_id     INTEGER NOT NULL,
                onboarded_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, guild_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS member_snapshots (
                guild_id      INTEGER NOT NULL,
                snapshot_date TEXT NOT NULL,   -- 'YYYY-MM-DD' (UTC)
                total         INTEGER NOT NULL,
                humans        INTEGER NOT NULL,
                bots          INTEGER NOT NULL,
                online        INTEGER NOT NULL DEFAULT 0,
                admins        INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (guild_id, snapshot_date)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS member_joins (
                guild_id    INTEGER NOT NULL,
                period      TEXT NOT NULL,    -- 'day' or 'week'
                period_date TEXT NOT NULL,    -- 'YYYY-MM-DD' (UTC; week = Monday)
                joins       INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, period, period_date)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS member_reports (
                guild_id    INTEGER NOT NULL,
                timeframe   TEXT NOT NULL,    -- 'daily' / 'weekly' / 'monthly'
                channel_id  INTEGER NOT NULL,
                message_id  INTEGER NOT NULL,
                updated_at  TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (guild_id, timeframe)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS engagement_daily (
                guild_id   INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,  -- Tracked root channel
                user_id    INTEGER NOT NULL,
                day        TEXT NOT NULL,     -- 'YYYY-MM-DD' (UTC)
                messages   INTEGER NOT NULL DEFAULT 0,
                reactions  INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, channel_id, user_id, day)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS editor_sessions (
                message_id   INTEGER PRIMARY KEY,
                user_id      INTEGER NOT NULL,
                session_type TEXT NOT NULL,  -- 'embed' or 'hook'
                payload      TEXT NOT NULL,   -- JSON EmbedScript state
                updated_at   TEXT DEFAULT (datetime('now'))
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS scheduled_messages (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id       INTEGER NOT NULL,
                user_id        INTEGER NOT NULL,
                channel_ids    TEXT NOT NULL,   -- JSON list of channel IDs e.g. [123, 456]
                payload        TEXT NOT NULL,   -- JSON EmbedScript state
                scheduled_time TEXT NOT NULL,   -- ISO 8601 UTC timestamp e.g. '2026-07-30T10:15:00+00:00'
                timezone_name  TEXT NOT NULL,   -- Timezone name e.g. 'US/Eastern'
                status         TEXT DEFAULT 'pending', -- 'pending', 'sent', 'failed', 'cancelled'
                created_at     TEXT DEFAULT (datetime('now')),
                sent_at        TEXT DEFAULT NULL
            );
            """
        ]
        for query in queries:
            await self._conn.execute(query)
        await self._conn.commit()

    async def execute(self, sql: str, parameters: tuple = ()):
        cursor = await self._conn.execute(sql, parameters)
        await self._conn.commit()
        return cursor

    async def fetchall(self, sql: str, parameters: tuple = ()):
        async with self._conn.execute(sql, parameters) as cursor:
            return await cursor.fetchall()

    async def fetchone(self, sql: str, parameters: tuple = ()):
        async with self._conn.execute(sql, parameters) as cursor:
            return await cursor.fetchone()

    async def close(self):
        if self._conn:
            await self._conn.close()
            print("[Database] Database connection closed.")
