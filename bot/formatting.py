"""Week helpers and Discord embed formatting for the calendar."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

import discord

from bot.models import Event

DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def get_tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("America/New_York")


def today_in_tz(tz_name: str) -> date:
    return datetime.now(get_tz(tz_name)).date()


def week_start(day: date) -> date:
    """Monday of the week containing `day`."""
    return day - timedelta(days=day.weekday())


def week_end(monday: date) -> date:
    return monday + timedelta(days=6)


def shift_week(monday: date, delta_weeks: int) -> date:
    return monday + timedelta(weeks=delta_weeks)


def format_event_line(event: Event) -> str:
    time_bit = f" · {event.event_time}" if event.event_time else ""
    interest = f" · ⭐ {event.interested_count}" if event.interested_count else ""
    return f"• **{event.title}**{time_bit}{interest} `(#{event.id})`"


def build_week_embed(
    *,
    guild_name: str,
    monday: date,
    events: Iterable[Event],
    timezone_name: str,
    footer: Optional[str] = None,
) -> discord.Embed:
    sunday = week_end(monday)
    by_day: dict[date, list[Event]] = defaultdict(list)
    for event in events:
        by_day[event.event_date].append(event)

    today = today_in_tz(timezone_name)
    lines: list[str] = []
    for offset in range(7):
        day = monday + timedelta(days=offset)
        label = DAY_NAMES[offset]
        header = f"**{label[:3].upper()} {day.day}**"
        if day == today:
            header = f"▶ {header}"

        day_events = by_day.get(day, [])
        if day_events:
            body = "\n".join(format_event_line(ev) for ev in day_events)
        else:
            body = "_No events_"
        lines.append(f"{header}\n{body}")

    description = "\n\n".join(lines)
    # Discord embed description hard limit is 4096; keep a safety margin.
    if len(description) > 3900:
        description = description[:3890] + "\n\n_…truncated_"

    embed = discord.Embed(
        title=f"📅 Week of {monday.strftime('%b %d')} – {sunday.strftime('%b %d, %Y')}",
        description=description,
        color=discord.Color.from_rgb(88, 166, 255),
        timestamp=datetime.now(get_tz(timezone_name)),
    )
    embed.set_author(name=f"{guild_name} schedule")
    embed.set_footer(text=footer or f"Timezone: {timezone_name} · Use /event for details")
    return embed


def build_event_embed(event: Event, interested_mentions: Optional[list[str]] = None) -> discord.Embed:
    when = event.event_date.strftime("%A, %b %d, %Y")
    if event.event_time:
        when = f"{when} · {event.event_time}"

    embed = discord.Embed(
        title=event.title,
        description=event.description or "_No description_",
        color=discord.Color.from_rgb(88, 166, 255),
    )
    embed.add_field(name="When", value=when, inline=False)
    embed.add_field(name="Interested", value=str(event.interested_count), inline=True)
    embed.add_field(name="Event ID", value=str(event.id), inline=True)
    if interested_mentions:
        shown = ", ".join(interested_mentions[:15])
        if len(interested_mentions) > 15:
            shown += f" (+{len(interested_mentions) - 15} more)"
        embed.add_field(name="Who's interested", value=shown, inline=False)
    return embed
