"""Async SQLite persistence for events, interest, and guild settings."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import aiosqlite

from bot.models import Event, GuildSettings


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._create_tables()

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
        return GuildSettings(
            guild_id=row["guild_id"],
            announcement_channel_id=row["announcement_channel_id"],
            calendar_channel_id=row["calendar_channel_id"],
            calendar_message_id=row["calendar_message_id"],
            timezone=row["timezone"],
        )

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
        return self._row_to_event(row) if row else None

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
        return [self._row_to_event(row) for row in rows]

    async def toggle_interest(self, event_id: int, user_id: int) -> tuple[bool, int]:
        """Return (is_interested_now, interested_count)."""
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
        return [
            GuildSettings(
                guild_id=row["guild_id"],
                announcement_channel_id=row["announcement_channel_id"],
                calendar_channel_id=row["calendar_channel_id"],
                calendar_message_id=row["calendar_message_id"],
                timezone=row["timezone"],
            )
            for row in rows
        ]

    @staticmethod
    def _row_to_event(row: aiosqlite.Row) -> Event:
        return Event(
            id=row["id"],
            guild_id=row["guild_id"],
            title=row["title"],
            event_date=date.fromisoformat(row["event_date"]),
            event_time=row["event_time"],
            description=row["description"] or "",
            created_by=row["created_by"],
            created_at=row["created_at"],
            interested_count=int(row["interested_count"] or 0),
        )
