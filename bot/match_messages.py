"""Helpers for match announcement / ping messages."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from bot.models import Event

if TYPE_CHECKING:
    from bot.main import CalendarBot

log = logging.getLogger(__name__)

MATCH_PING_ALLOWED = discord.AllowedMentions(users=True, roles=True, everyone=False)


def match_side_mention(side_type: str | None, side_id: int | None) -> str:
    if side_id is None or side_type is None:
        return "Unknown"
    if side_type == "role":
        return f"<@&{side_id}>"
    return f"<@{side_id}>"


def format_match_ping_from_event(event: Event) -> str:
    nice_date = event.event_date.strftime("%A, %B %d, %Y")
    side_a = match_side_mention(event.match_a_type, event.match_a_id)
    side_b = match_side_mention(event.match_b_type, event.match_b_id)
    return (
        "**Match Scheduled**\n"
        f"{side_a} vs {side_b}\n\n"
        f"**Date:** {nice_date}\n"
        f"**Time:** {event.event_time or 'TBD'}\n"
        f"**Calendar ID:** #{event.id}"
    )


async def sync_match_ping_message(bot: "CalendarBot", event: Event) -> None:
    """Edit the stored match ping message to match the event (no new notification)."""
    if not event.is_match or not event.ping_channel_id or not event.ping_message_id:
        return

    channel = bot.get_channel(event.ping_channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(event.ping_channel_id)
        except discord.HTTPException:
            log.warning("Match ping channel missing for event #%s", event.id)
            await bot.db.clear_ping_message(event.id)
            return

    if not isinstance(channel, discord.TextChannel):
        return

    try:
        message = await channel.fetch_message(event.ping_message_id)
    except discord.NotFound:
        await bot.db.clear_ping_message(event.id)
        return
    except discord.HTTPException:
        log.exception("Failed fetching match ping for event #%s", event.id)
        return

    try:
        await message.edit(
            content=format_match_ping_from_event(event),
            allowed_mentions=MATCH_PING_ALLOWED,
        )
    except discord.HTTPException:
        log.exception("Failed editing match ping for event #%s", event.id)


async def delete_match_ping_message(bot: "CalendarBot", event: Event) -> None:
    """Delete the stored match ping message, if any."""
    if not event.ping_channel_id or not event.ping_message_id:
        return

    channel = bot.get_channel(event.ping_channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(event.ping_channel_id)
        except discord.HTTPException:
            await bot.db.clear_ping_message(event.id)
            return

    if not isinstance(channel, discord.TextChannel):
        return

    try:
        message = await channel.fetch_message(event.ping_message_id)
        await message.delete()
    except discord.NotFound:
        pass
    except discord.HTTPException:
        log.exception("Failed deleting match ping for event #%s", event.id)
    finally:
        try:
            await bot.db.clear_ping_message(event.id)
        except Exception:
            log.exception("Failed clearing ping ids for event #%s", event.id)
