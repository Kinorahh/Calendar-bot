"""Async persistence for events and guild settings.

Uses PostgreSQL when DATABASE_URL is set (Railway), otherwise SQLite locally.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

import aiosqlite
import asyncpg

from bot.models import Event, GuildSettings
from bot.parsers import convert_24h_time_if_needed

log = logging.getLogger(__name__)


def normalize_database_url(url: str) -> str:
    """Railway often provides postgres:// — asyncpg wants postgresql://."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


class Database(Protocol):
    path: str

    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def get_settings(self, guild_id: int) -> GuildSettings: ...
    async def upsert_settings(
        self,
        guild_id: int,
        *,
        announcement_channel_id: Optional[int] = None,
        calendar_channel_id: Optional[int] = None,
        calendar_message_id: Optional[int] = None,
        timezone_name: Optional[str] = None,
    ) -> GuildSettings: ...
    async def clear_calendar_message(self, guild_id: int) -> None: ...
    async def add_event(
        self,
        *,
        guild_id: int,
        title: str,
        event_date: date,
        event_time: Optional[str],
        description: str,
        created_by: int,
        match_a_type: Optional[str] = None,
        match_a_id: Optional[int] = None,
        match_b_type: Optional[str] = None,
        match_b_id: Optional[int] = None,
    ) -> Event: ...
    async def update_event(
        self,
        event_id: int,
        *,
        event_date: Optional[date] = None,
        event_time: Optional[str] = None,
    ) -> Optional[Event]: ...
    async def delete_event(self, event_id: int) -> bool: ...
    async def set_ping_message(
        self, event_id: int, *, channel_id: int, message_id: int
    ) -> None: ...
    async def clear_ping_message(self, event_id: int) -> None: ...
    async def get_event(self, event_id: int) -> Optional[Event]: ...
    async def get_events_between(
        self, guild_id: int, start: date, end: date
    ) -> list[Event]: ...
    async def guilds_with_announcements(self) -> list[GuildSettings]: ...
    async def guilds_with_live_calendar(self) -> list[GuildSettings]: ...


def create_database(
    *,
    database_url: Optional[str] = None,
    sqlite_path: Optional[Path] = None,
) -> Database:
    if database_url:
        return PostgresDatabase(normalize_database_url(database_url))
    if sqlite_path is None:
        raise ValueError("sqlite_path is required when DATABASE_URL is not set")
    return SQLiteDatabase(sqlite_path)


def _coerce_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value))


def _settings_from_row(row: Any, guild_id: int | None = None) -> GuildSettings:
    return GuildSettings(
        guild_id=int(row["guild_id"] if guild_id is None else guild_id),
        announcement_channel_id=_optional_int(row["announcement_channel_id"]),
        calendar_channel_id=_optional_int(row["calendar_channel_id"]),
        calendar_message_id=_optional_int(row["calendar_message_id"]),
        timezone=row["timezone"],
    )


def _optional_int(value: Any) -> Optional[int]:
    return None if value is None else int(value)


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def _event_from_row(row: Any) -> Event:
    return Event(
        id=int(row["id"]),
        guild_id=int(row["guild_id"]),
        title=row["title"],
        event_date=_coerce_date(row["event_date"]),
        event_time=row["event_time"],
        description=row["description"] or "",
        created_by=int(row["created_by"]),
        created_at=str(row["created_at"]),
        match_a_type=_row_value(row, "match_a_type"),
        match_a_id=_optional_int(_row_value(row, "match_a_id")),
        match_b_type=_row_value(row, "match_b_type"),
        match_b_id=_optional_int(_row_value(row, "match_b_id")),
        ping_channel_id=_optional_int(_row_value(row, "ping_channel_id")),
        ping_message_id=_optional_int(_row_value(row, "ping_message_id")),
    )


class PostgresDatabase:
    def __init__(self, dsn: str) -> None:
        self.path = "postgresql"
        self._dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database is not connected")
        return self._pool

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)
        await self._create_tables()
        await self._migrate_match_columns()
        converted = await self._migrate_event_times_to_12h()
        log.info("Connected to PostgreSQL")
        if converted:
            log.info("Converted %s leftover 24h event time(s) to 12h", converted)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def _create_tables(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id BIGINT PRIMARY KEY,
                    announcement_channel_id BIGINT,
                    calendar_channel_id BIGINT,
                    calendar_message_id BIGINT,
                    timezone TEXT NOT NULL DEFAULT 'America/New_York'
                );

                CREATE TABLE IF NOT EXISTS events (
                    id SERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    title TEXT NOT NULL,
                    event_date DATE NOT NULL,
                    event_time TEXT,
                    description TEXT NOT NULL DEFAULT '',
                    created_by BIGINT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    match_a_type TEXT,
                    match_a_id BIGINT,
                    match_b_type TEXT,
                    match_b_id BIGINT,
                    ping_channel_id BIGINT,
                    ping_message_id BIGINT
                );

                CREATE TABLE IF NOT EXISTS event_interest (
                    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                    user_id BIGINT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (event_id, user_id)
                );

                CREATE INDEX IF NOT EXISTS idx_events_guild_date
                    ON events (guild_id, event_date);
                """
            )

    async def _migrate_match_columns(self) -> None:
        async with self.pool.acquire() as conn:
            for stmt in (
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS match_a_type TEXT",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS match_a_id BIGINT",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS match_b_type TEXT",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS match_b_id BIGINT",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS ping_channel_id BIGINT",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS ping_message_id BIGINT",
            ):
                await conn.execute(stmt)

    async def _migrate_event_times_to_12h(self) -> int:
        """One-time style fix: rewrite stored 24h times like 21:00 → 9:00 PM."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, event_time FROM events WHERE event_time IS NOT NULL"
            )
            updated = 0
            for row in rows:
                converted = convert_24h_time_if_needed(row["event_time"])
                if converted is None:
                    continue
                await conn.execute(
                    "UPDATE events SET event_time = $1 WHERE id = $2",
                    converted,
                    row["id"],
                )
                updated += 1
                log.info(
                    "Event #%s time %s → %s",
                    row["id"],
                    row["event_time"],
                    converted,
                )
            return updated

    async def get_settings(self, guild_id: int) -> GuildSettings:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM guild_settings WHERE guild_id = $1",
                guild_id,
            )
        if row is None:
            return GuildSettings(
                guild_id=guild_id,
                announcement_channel_id=None,
                calendar_channel_id=None,
                calendar_message_id=None,
                timezone="America/New_York",
            )
        return _settings_from_row(row)

    async def upsert_settings(
        self,
        guild_id: int,
        *,
        announcement_channel_id: Optional[int] = None,
        calendar_channel_id: Optional[int] = None,
        calendar_message_id: Optional[int] = None,
        timezone_name: Optional[str] = None,
    ) -> GuildSettings:
        current = await self.get_settings(guild_id)
        announcement = (
            announcement_channel_id
            if announcement_channel_id is not None
            else current.announcement_channel_id
        )
        cal_channel = (
            calendar_channel_id if calendar_channel_id is not None else current.calendar_channel_id
        )
        cal_message = (
            calendar_message_id if calendar_message_id is not None else current.calendar_message_id
        )
        tz = timezone_name if timezone_name is not None else current.timezone

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_settings (
                    guild_id, announcement_channel_id, calendar_channel_id,
                    calendar_message_id, timezone
                ) VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (guild_id) DO UPDATE SET
                    announcement_channel_id = EXCLUDED.announcement_channel_id,
                    calendar_channel_id = EXCLUDED.calendar_channel_id,
                    calendar_message_id = EXCLUDED.calendar_message_id,
                    timezone = EXCLUDED.timezone
                """,
                guild_id,
                announcement,
                cal_channel,
                cal_message,
                tz,
            )
        return await self.get_settings(guild_id)

    async def clear_calendar_message(self, guild_id: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE guild_settings
                SET calendar_message_id = NULL
                WHERE guild_id = $1
                """,
                guild_id,
            )

    async def add_event(
        self,
        *,
        guild_id: int,
        title: str,
        event_date: date,
        event_time: Optional[str],
        description: str,
        created_by: int,
        match_a_type: Optional[str] = None,
        match_a_id: Optional[int] = None,
        match_b_type: Optional[str] = None,
        match_b_id: Optional[int] = None,
    ) -> Event:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO events (
                    guild_id, title, event_date, event_time, description, created_by,
                    created_at, match_a_type, match_a_id, match_b_type, match_b_id
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING id
                """,
                guild_id,
                title.strip(),
                event_date,
                event_time.strip() if event_time else None,
                description.strip(),
                created_by,
                datetime.now(timezone.utc),
                match_a_type,
                match_a_id,
                match_b_type,
                match_b_id,
            )
        event = await self.get_event(int(row["id"]))
        assert event is not None
        return event

    async def update_event(
        self,
        event_id: int,
        *,
        event_date: Optional[date] = None,
        event_time: Optional[str] = None,
    ) -> Optional[Event]:
        event = await self.get_event(event_id)
        if event is None:
            return None

        new_date = event_date if event_date is not None else event.event_date
        new_time = event_time.strip() if event_time is not None else event.event_time

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE events
                SET event_date = $1, event_time = $2
                WHERE id = $3
                """,
                new_date,
                new_time,
                event_id,
            )
        return await self.get_event(event_id)

    async def delete_event(self, event_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM events WHERE id = $1", event_id)
        # asyncpg returns strings like "DELETE 1"
        return result.endswith("1")

    async def set_ping_message(
        self, event_id: int, *, channel_id: int, message_id: int
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE events
                SET ping_channel_id = $1, ping_message_id = $2
                WHERE id = $3
                """,
                channel_id,
                message_id,
                event_id,
            )

    async def clear_ping_message(self, event_id: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE events
                SET ping_channel_id = NULL, ping_message_id = NULL
                WHERE id = $1
                """,
                event_id,
            )

    async def get_event(self, event_id: int) -> Optional[Event]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT e.* FROM events e WHERE e.id = $1",
                event_id,
            )
        return _event_from_row(row) if row else None

    async def get_events_between(
        self, guild_id: int, start: date, end: date
    ) -> list[Event]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT e.*
                FROM events e
                WHERE e.guild_id = $1
                  AND e.event_date >= $2
                  AND e.event_date <= $3
                ORDER BY e.event_date ASC,
                         CASE WHEN e.event_time IS NULL THEN 1 ELSE 0 END,
                         e.event_time ASC,
                         e.id ASC
                """,
                guild_id,
                start,
                end,
            )
        return [_event_from_row(row) for row in rows]

    async def guilds_with_announcements(self) -> list[GuildSettings]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM guild_settings
                WHERE announcement_channel_id IS NOT NULL
                """
            )
        return [_settings_from_row(row) for row in rows]

    async def guilds_with_live_calendar(self) -> list[GuildSettings]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM guild_settings
                WHERE calendar_channel_id IS NOT NULL
                  AND calendar_message_id IS NOT NULL
                """
            )
        return [_settings_from_row(row) for row in rows]


class SQLiteDatabase:
    def __init__(self, path: Path) -> None:
        self.path = str(path)
        self._path = path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._create_tables()
        await self._migrate_match_columns()
        converted = await self._migrate_event_times_to_12h()
        log.info("Connected to SQLite at %s", self.path)
        if converted:
            log.info("Converted %s leftover 24h event time(s) to 12h", converted)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    async def _create_tables(self) -> None:
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                announcement_channel_id INTEGER,
                calendar_channel_id INTEGER,
                calendar_message_id INTEGER,
                timezone TEXT NOT NULL DEFAULT 'America/New_York'
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                event_date TEXT NOT NULL,
                event_time TEXT,
                description TEXT NOT NULL DEFAULT '',
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                match_a_type TEXT,
                match_a_id INTEGER,
                match_b_type TEXT,
                match_b_id INTEGER,
                ping_channel_id INTEGER,
                ping_message_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS event_interest (
                event_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (event_id, user_id),
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_events_guild_date
                ON events (guild_id, event_date);
            """
        )
        await self.conn.commit()

    async def _migrate_match_columns(self) -> None:
        columns = (
            ("match_a_type", "TEXT"),
            ("match_a_id", "INTEGER"),
            ("match_b_type", "TEXT"),
            ("match_b_id", "INTEGER"),
            ("ping_channel_id", "INTEGER"),
            ("ping_message_id", "INTEGER"),
        )
        for name, col_type in columns:
            try:
                await self.conn.execute(
                    f"ALTER TABLE events ADD COLUMN {name} {col_type}"
                )
            except Exception:
                # Column already exists on upgraded databases.
                pass
        await self.conn.commit()

    async def _migrate_event_times_to_12h(self) -> int:
        """One-time style fix: rewrite stored 24h times like 21:00 → 9:00 PM."""
        async with self.conn.execute(
            "SELECT id, event_time FROM events WHERE event_time IS NOT NULL"
        ) as cursor:
            rows = await cursor.fetchall()
        updated = 0
        for row in rows:
            converted = convert_24h_time_if_needed(row["event_time"])
            if converted is None:
                continue
            await self.conn.execute(
                "UPDATE events SET event_time = ? WHERE id = ?",
                (converted, row["id"]),
            )
            updated += 1
            log.info(
                "Event #%s time %s → %s",
                row["id"],
                row["event_time"],
                converted,
            )
        if updated:
            await self.conn.commit()
        return updated

    async def get_settings(self, guild_id: int) -> GuildSettings:
        async with self.conn.execute(
            "SELECT * FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return GuildSettings(
                guild_id=guild_id,
                announcement_channel_id=None,
                calendar_channel_id=None,
                calendar_message_id=None,
                timezone="America/New_York",
            )
        return _settings_from_row(row)

    async def upsert_settings(
        self,
        guild_id: int,
        *,
        announcement_channel_id: Optional[int] = None,
        calendar_channel_id: Optional[int] = None,
        calendar_message_id: Optional[int] = None,
        timezone_name: Optional[str] = None,
    ) -> GuildSettings:
        current = await self.get_settings(guild_id)
        announcement = (
            announcement_channel_id
            if announcement_channel_id is not None
            else current.announcement_channel_id
        )
        cal_channel = (
            calendar_channel_id if calendar_channel_id is not None else current.calendar_channel_id
        )
        cal_message = (
            calendar_message_id if calendar_message_id is not None else current.calendar_message_id
        )
        tz = timezone_name if timezone_name is not None else current.timezone

        await self.conn.execute(
            """
            INSERT INTO guild_settings (
                guild_id, announcement_channel_id, calendar_channel_id,
                calendar_message_id, timezone
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                announcement_channel_id = excluded.announcement_channel_id,
                calendar_channel_id = excluded.calendar_channel_id,
                calendar_message_id = excluded.calendar_message_id,
                timezone = excluded.timezone
            """,
            (guild_id, announcement, cal_channel, cal_message, tz),
        )
        await self.conn.commit()
        return await self.get_settings(guild_id)

    async def clear_calendar_message(self, guild_id: int) -> None:
        await self.conn.execute(
            """
            UPDATE guild_settings
            SET calendar_message_id = NULL
            WHERE guild_id = ?
            """,
            (guild_id,),
        )
        await self.conn.commit()

    async def add_event(
        self,
        *,
        guild_id: int,
        title: str,
        event_date: date,
        event_time: Optional[str],
        description: str,
        created_by: int,
        match_a_type: Optional[str] = None,
        match_a_id: Optional[int] = None,
        match_b_type: Optional[str] = None,
        match_b_id: Optional[int] = None,
    ) -> Event:
        created_at = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            """
            INSERT INTO events (
                guild_id, title, event_date, event_time, description, created_by,
                created_at, match_a_type, match_a_id, match_b_type, match_b_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                title.strip(),
                event_date.isoformat(),
                event_time.strip() if event_time else None,
                description.strip(),
                created_by,
                created_at,
                match_a_type,
                match_a_id,
                match_b_type,
                match_b_id,
            ),
        )
        await self.conn.commit()
        event = await self.get_event(cursor.lastrowid)
        assert event is not None
        return event

    async def update_event(
        self,
        event_id: int,
        *,
        event_date: Optional[date] = None,
        event_time: Optional[str] = None,
    ) -> Optional[Event]:
        event = await self.get_event(event_id)
        if event is None:
            return None

        new_date = event_date if event_date is not None else event.event_date
        new_time = event_time.strip() if event_time is not None else event.event_time

        await self.conn.execute(
            """
            UPDATE events
            SET event_date = ?, event_time = ?
            WHERE id = ?
            """,
            (new_date.isoformat(), new_time, event_id),
        )
        await self.conn.commit()
        return await self.get_event(event_id)

    async def delete_event(self, event_id: int) -> bool:
        cursor = await self.conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        await self.conn.commit()
        return cursor.rowcount > 0

    async def set_ping_message(
        self, event_id: int, *, channel_id: int, message_id: int
    ) -> None:
        await self.conn.execute(
            """
            UPDATE events
            SET ping_channel_id = ?, ping_message_id = ?
            WHERE id = ?
            """,
            (channel_id, message_id, event_id),
        )
        await self.conn.commit()

    async def clear_ping_message(self, event_id: int) -> None:
        await self.conn.execute(
            """
            UPDATE events
            SET ping_channel_id = NULL, ping_message_id = NULL
            WHERE id = ?
            """,
            (event_id,),
        )
        await self.conn.commit()

    async def get_event(self, event_id: int) -> Optional[Event]:
        async with self.conn.execute(
            "SELECT e.* FROM events e WHERE e.id = ?",
            (event_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return _event_from_row(row) if row else None

    async def get_events_between(
        self, guild_id: int, start: date, end: date
    ) -> list[Event]:
        async with self.conn.execute(
            """
            SELECT e.*
            FROM events e
            WHERE e.guild_id = ?
              AND e.event_date >= ?
              AND e.event_date <= ?
            ORDER BY e.event_date ASC,
                     CASE WHEN e.event_time IS NULL THEN 1 ELSE 0 END,
                     e.event_time ASC,
                     e.id ASC
            """,
            (guild_id, start.isoformat(), end.isoformat()),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_event_from_row(row) for row in rows]

    async def guilds_with_announcements(self) -> list[GuildSettings]:
        async with self.conn.execute(
            """
            SELECT * FROM guild_settings
            WHERE announcement_channel_id IS NOT NULL
            """
        ) as cursor:
            rows = await cursor.fetchall()
        return [_settings_from_row(row) for row in rows]

    async def guilds_with_live_calendar(self) -> list[GuildSettings]:
        async with self.conn.execute(
            """
            SELECT * FROM guild_settings
            WHERE calendar_channel_id IS NOT NULL
              AND calendar_message_id IS NOT NULL
            """
        ) as cursor:
            rows = await cursor.fetchall()
        return [_settings_from_row(row) for row in rows]
