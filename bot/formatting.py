"""Week helpers and Discord embed formatting for the calendar."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

import discord

from bot.models import Event
from bot.parsers import event_time_sort_key

DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
SCHEDULE_AUTHOR = "P6M Weekly Schedule"


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


def week_label(monday: date) -> str:
    sunday = week_end(monday)
    return f"{monday.strftime('%b %d')} – {sunday.strftime('%b %d, %Y')}"


def timezone_abbrev(tz_name: str, when: Optional[datetime] = None) -> str:
    """Short zone name like EST/EDT for the given IANA timezone."""
    moment = when or datetime.now(get_tz(tz_name))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=get_tz(tz_name))
    else:
        moment = moment.astimezone(get_tz(tz_name))
    abbrev = moment.strftime("%Z") or tz_name
    return abbrev


def format_last_updated(tz_name: str) -> str:
    now = datetime.now(get_tz(tz_name))
    # Windows-safe 12h clock without leading zero tricks that break on Windows.
    hour12 = now.hour % 12 or 12
    return f"{now.strftime('%b %d')}, {hour12}:{now.strftime('%M %p')}"


def live_calendar_footer(monday: date, timezone_name: str) -> str:
    return (
        f"Live Calendar - Week of {week_label(monday)} - "
        f"Timezone: {timezone_abbrev(timezone_name)} - "
        f"Last updated {format_last_updated(timezone_name)}"
    )


def format_event_line(event: Event) -> str:
    time_bit = f"**{event.event_time}** " if event.event_time else ""
    interest = f" · ⭐ {event.interested_count}" if event.interested_count else ""
    return f"• {time_bit}{event.title}{interest} `(#{event.id})`"


def build_week_embed(
    *,
    guild_name: str,
    monday: date,
    events: Iterable[Event],
    timezone_name: str,
    footer: Optional[str] = None,
) -> discord.Embed:
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

        day_events = sorted(
            by_day.get(day, []),
            key=lambda ev: event_time_sort_key(ev.event_time, ev.id),
        )
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
        title=f"📅 Week of {week_label(monday)}",
        description=description,
        color=discord.Color.from_rgb(88, 166, 255),
    )
    embed.set_author(name=SCHEDULE_AUTHOR)
    embed.set_footer(
        text=footer
        or (
            f"Timezone: {timezone_abbrev(timezone_name)} - "
            f"Last updated {format_last_updated(timezone_name)}"
        )
    )
    return embed


def build_event_embed(event: Event, interested_mentions: Optional[list[str]] = None) -> discord.Embed:
    when = event.event_date.strftime("%A, %b %d, %Y")
    if event.event_time:
        when = f"**{event.event_time}** · {when}"

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
