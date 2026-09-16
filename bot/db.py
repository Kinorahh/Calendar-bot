"""Async persistence for events, interest, and guild settings.

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
    ) -> Event: ...
    async def update_event(
        self,
        event_id: int,
        *,
        title: Optional[str] = None,
        event_date: Optional[date] = None,
        event_time: Optional[str] = None,
        clear_time: bool = False,
        description: Optional[str] = None,
    ) -> Optional[Event]: ...
    async def delete_event(self, event_id: int) -> bool: ...
    async def get_event(self, event_id: int) -> Optional[Event]: ...
    async def get_events_between(
        self, guild_id: int, start: date, end: date
    ) -> list[Event]: ...
    async def toggle_interest(self, event_id: int, user_id: int) -> tuple[bool, int]: ...
    async def list_interested_user_ids(self, event_id: int) -> list[int]: ...
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
        interested_count=int(row["interested_count"] or 0),
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
        log.info("Connected to PostgreSQL")

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
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
    ) -> Event:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO events (
                    guild_id, title, event_date, event_time, description, created_by, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
                """,
                guild_id,
                title.strip(),
                event_date,
                event_time.strip() if event_time else None,
                description.strip(),
                created_by,
                datetime.now(timezone.utc),
            )
        event = await self.get_event(int(row["id"]))
        assert event is not None
        return event

    async def update_event(
        self,
        event_id: int,
        *,
        title: Optional[str] = None,
        event_date: Optional[date] = None,
        event_time: Optional[str] = None,
        clear_time: bool = False,
        description: Optional[str] = None,
    ) -> Optional[Event]:
        event = await self.get_event(event_id)
        if event is None:
            return None

        new_title = title.strip() if title is not None else event.title
        new_date = event_date if event_date is not None else event.event_date
        if clear_time:
            new_time = None
        elif event_time is not None:
            new_time = event_time.strip() or None
        else:
            new_time = event.event_time
        new_description = description.strip() if description is not None else event.description

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE events
                SET title = $1, event_date = $2, event_time = $3, description = $4
                WHERE id = $5
                """,
                new_title,
                new_date,
                new_time,
                new_description,
                event_id,
            )
        return await self.get_event(event_id)

    async def delete_event(self, event_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM events WHERE id = $1", event_id)
        # asyncpg returns strings like "DELETE 1"
        return result.endswith("1")

    async def get_event(self, event_id: int) -> Optional[Event]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT e.*,
                       (SELECT COUNT(*) FROM event_interest i WHERE i.event_id = e.id)
                           AS interested_count
                FROM events e
                WHERE e.id = $1
                """,
                event_id,
            )
        return _event_from_row(row) if row else None

    async def get_events_between(
        self, guild_id: int, start: date, end: date
    ) -> list[Event]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT e.*,
                       (SELECT COUNT(*) FROM event_interest i WHERE i.event_id = e.id)
                           AS interested_count
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

    async def toggle_interest(self, event_id: int, user_id: int) -> tuple[bool, int]:
        async with self.pool.acquire() as conn:
            existing = await conn.fetchrow(
                """
                SELECT 1 FROM event_interest
                WHERE event_id = $1 AND user_id = $2
                """,
                event_id,
                user_id,
            )
            if existing:
                await conn.execute(
                    """
                    DELETE FROM event_interest
                    WHERE event_id = $1 AND user_id = $2
                    """,
                    event_id,
                    user_id,
                )
                interested = False
            else:
                await conn.execute(
                    """
                    INSERT INTO event_interest (event_id, user_id, created_at)
                    VALUES ($1, $2, $3)
                    """,
                    event_id,
                    user_id,
                    datetime.now(timezone.utc),
                )
                interested = True
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM event_interest WHERE event_id = $1",
                event_id,
            )
        return interested, int(count)

    async def list_interested_user_ids(self, event_id: int) -> list[int]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id FROM event_interest
                WHERE event_id = $1
                ORDER BY created_at ASC
                """,
                event_id,
            )
        return [int(row["user_id"]) for row in rows]

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
        log.info("Connected to SQLite at %s", self.path)

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
                created_at TEXT NOT NULL
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
    ) -> Event:
        created_at = datetime.now(timezone.utc).isoformat()
        cursor = await self.conn.execute(
            """
            INSERT INTO events (
                guild_id, title, event_date, event_time, description, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                title.strip(),
                event_date.isoformat(),
                event_time.strip() if event_time else None,
                description.strip(),
                created_by,
                created_at,
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
        title: Optional[str] = None,
        event_date: Optional[date] = None,
        event_time: Optional[str] = None,
        clear_time: bool = False,
        description: Optional[str] = None,
    ) -> Optional[Event]:
        event = await self.get_event(event_id)
        if event is None:
            return None

        new_title = title.strip() if title is not None else event.title
        new_date = event_date if event_date is not None else event.event_date
        if clear_time:
            new_time = None
        elif event_time is not None:
            new_time = event_time.strip() or None
        else:
            new_time = event.event_time
        new_description = description.strip() if description is not None else event.description

        await self.conn.execute(
            """
            UPDATE events
            SET title = ?, event_date = ?, event_time = ?, description = ?
            WHERE id = ?
            """,
            (new_title, new_date.isoformat(), new_time, new_description, event_id),
        )
        await self.conn.commit()
        return await self.get_event(event_id)

    async def delete_event(self, event_id: int) -> bool:
        cursor = await self.conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        await self.conn.commit()
        return cursor.rowcount > 0

    async def get_event(self, event_id: int) -> Optional[Event]:
        async with self.conn.execute(
            """
            SELECT e.*,
                   (SELECT COUNT(*) FROM event_interest i WHERE i.event_id = e.id)
                       AS interested_count
            FROM events e
            WHERE e.id = ?
            """,
            (event_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return _event_from_row(row) if row else None

    async def get_events_between(
        self, guild_id: int, start: date, end: date
    ) -> list[Event]:
        async with self.conn.execute(
            """
            SELECT e.*,
                   (SELECT COUNT(*) FROM event_interest i WHERE i.event_id = e.id)
                       AS interested_count
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

    async def toggle_interest(self, event_id: int, user_id: int) -> tuple[bool, int]:
        async with self.conn.execute(
            "SELECT 1 FROM event_interest WHERE event_id = ? AND user_id = ?",
            (event_id, user_id),
        ) as cursor:
            existing = await cursor.fetchone()

        now = datetime.now(timezone.utc).isoformat()
        if existing:
            await self.conn.execute(
                "DELETE FROM event_interest WHERE event_id = ? AND user_id = ?",
                (event_id, user_id),
            )
            interested = False
        else:
            await self.conn.execute(
                """
                INSERT INTO event_interest (event_id, user_id, created_at)
                VALUES (?, ?, ?)
                """,
                (event_id, user_id, now),
            )
            interested = True
        await self.conn.commit()

        async with self.conn.execute(
            "SELECT COUNT(*) AS c FROM event_interest WHERE event_id = ?",
            (event_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return interested, int(row["c"])

    async def list_interested_user_ids(self, event_id: int) -> list[int]:
        async with self.conn.execute(
            "SELECT user_id FROM event_interest WHERE event_id = ? ORDER BY created_at ASC",
            (event_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [int(row["user_id"]) for row in rows]

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
