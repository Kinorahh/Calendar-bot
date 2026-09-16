from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass(slots=True)
class Event:
    id: int
    guild_id: int
    title: str
    event_date: date
    event_time: Optional[str]
    description: str
    created_by: int
    created_at: str
    interested_count: int = 0


@dataclass(slots=True)
class GuildSettings:
    guild_id: int
    announcement_channel_id: Optional[int]
    calendar_channel_id: Optional[int]
    calendar_message_id: Optional[int]
    timezone: str
