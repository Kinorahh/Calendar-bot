from __future__ import annotations

from dataclasses import dataclass
from datetime import date
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
    match_a_type: Optional[str] = None  # "user" | "role"
    match_a_id: Optional[int] = None
    match_b_type: Optional[str] = None
    match_b_id: Optional[int] = None
    ping_channel_id: Optional[int] = None
    ping_message_id: Optional[int] = None

    @property
    def is_match(self) -> bool:
        return self.match_a_type is not None and self.match_b_type is not None


@dataclass(slots=True)
class GuildSettings:
    guild_id: int
    announcement_channel_id: Optional[int]
    calendar_channel_id: Optional[int]
    calendar_message_id: Optional[int]
    timezone: str
