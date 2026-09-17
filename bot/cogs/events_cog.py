"""Event create / edit / remove / view commands."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot import config
from bot.add_wizard import EventAddProceedView
from bot.match_messages import delete_match_ping_message, sync_match_ping_message
from bot.messaging import send_ephemeral
from bot.parsers import parse_date, parse_time_12h
from bot.permissions import can_modify_event, require_admin


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    event = app_commands.Group(name="event", description="Manage and view calendar events")

    @event.command(
        name="add",
        description="Add an event with a private form (admins)",
    )
    async def add(self, interaction: discord.Interaction) -> None:
        if not await require_admin(interaction):
            return
        assert interaction.guild is not None

        view = EventAddProceedView(
            self.bot, interaction.guild.id, interaction.user.id
        )
        await send_ephemeral(
            interaction,
            "Click **Proceed** to input event information "
            "(title, date as `YYYY-MM-DD`, and time like `9:00 PM`).",
            view=view,
        )

    @event.command(
        name="edit",
        description="Edit an event's date or time (admins or match participants)",
    )
    @app_commands.describe(
        event_id="Event id shown on the calendar",
        date="New date as YYYY-MM-DD only",
        time="New time in 12-hour format, e.g. 9:00 PM",
    )
    async def edit(
        self,
        interaction: discord.Interaction,
        event_id: int,
        date: str | None = None,
        time: str | None = None,
    ) -> None:
        if interaction.guild is None:
            await send_ephemeral(interaction, "Use this command in a server.")
            return

        existing = await self.bot.db.get_event(event_id)
        if existing is None or existing.guild_id != interaction.guild.id:
            await send_ephemeral(interaction, "Event not found in this server.")
            return

        if not can_modify_event(interaction, existing):
            await send_ephemeral(
                interaction,
                "Only users with an admin role "
                f"({', '.join(sorted(config.ADMIN_ROLE_NAMES))}) "
                "or participants of this match can edit it.",
            )
            return

        if date is None and time is None:
            await send_ephemeral(
                interaction, "Provide a new `date` and/or `time` to update."
            )
            return

        event_date = None
        if date is not None:
            try:
                event_date = parse_date(date)
            except ValueError as exc:
                await send_ephemeral(interaction, str(exc))
                return

        parsed_time = None
        if time is not None:
            try:
                parsed_time = parse_time_12h(time)
            except ValueError as exc:
                await send_ephemeral(interaction, str(exc))
                return

        updated = await self.bot.db.update_event(
            event_id,
            event_date=event_date,
            event_time=parsed_time,
        )
        assert updated is not None
        await send_ephemeral(
            interaction, f"Updated **{updated.title}** (id `{updated.id}`)."
        )
        await self.bot.refresh_live_calendar(interaction.guild.id)
        if updated.is_match:
            await sync_match_ping_message(self.bot, updated)

    @event.command(
        name="remove",
        description="Remove an event (admins or match participants)",
    )
    @app_commands.describe(event_id="Event id shown on the calendar")
    async def remove(self, interaction: discord.Interaction, event_id: int) -> None:
        if interaction.guild is None:
            await send_ephemeral(interaction, "Use this command in a server.")
            return

        existing = await self.bot.db.get_event(event_id)
        if existing is None or existing.guild_id != interaction.guild.id:
            await send_ephemeral(interaction, "Event not found in this server.")
            return

        if not can_modify_event(interaction, existing):
            await send_ephemeral(
                interaction,
                "Only users with an admin role "
                f"({', '.join(sorted(config.ADMIN_ROLE_NAMES))}) "
                "or participants of this match can remove it.",
            )
            return

        await delete_match_ping_message(self.bot, existing)
        await self.bot.db.delete_event(event_id)
        await send_ephemeral(
            interaction, f"Removed **{existing.title}** (id `{event_id}`)."
        )
        await self.bot.refresh_live_calendar(interaction.guild.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventsCog(bot))
