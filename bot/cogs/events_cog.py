"""Event create / edit / remove / view commands."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.add_wizard import EventAddProceedView
from bot.formatting import build_event_embed
from bot.messaging import send_ephemeral
from bot.parsers import parse_date, parse_time_12h
from bot.permissions import require_manager
from bot.views import EventInterestView


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    event = app_commands.Group(name="event", description="Manage and view calendar events")

    @event.command(
        name="add",
        description="Add an event with a private form (mods/admins)",
    )
    async def add(self, interaction: discord.Interaction) -> None:
        if not await require_manager(interaction):
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

    @event.command(name="edit", description="Edit an existing event (mods/admins)")
    @app_commands.describe(
        event_id="Event id shown on the calendar",
        title="New title",
        date="New date as YYYY-MM-DD only",
        time="New time in 12-hour format, e.g. 9:00 PM",
        clear_time="Remove the time from the event",
        description="New description",
    )
    async def edit(
        self,
        interaction: discord.Interaction,
        event_id: int,
        title: str | None = None,
        date: str | None = None,
        time: str | None = None,
        clear_time: bool = False,
        description: str | None = None,
    ) -> None:
        if not await require_manager(interaction):
            return
        assert interaction.guild is not None

        existing = await self.bot.db.get_event(event_id)
        if existing is None or existing.guild_id != interaction.guild.id:
            await send_ephemeral(interaction, "Event not found in this server.")
            return

        event_date = None
        if date is not None:
            try:
                event_date = parse_date(date)
            except ValueError as exc:
                await send_ephemeral(interaction, str(exc))
                return

        parsed_time = None
        if time is not None and not clear_time:
            try:
                parsed_time = parse_time_12h(time)
            except ValueError as exc:
                await send_ephemeral(interaction, str(exc))
                return

        updated = await self.bot.db.update_event(
            event_id,
            title=title,
            event_date=event_date,
            event_time=parsed_time,
            clear_time=clear_time,
            description=description,
        )
        assert updated is not None
        await send_ephemeral(
            interaction, f"Updated **{updated.title}** (id `{updated.id}`)."
        )
        await self.bot.refresh_live_calendar(interaction.guild.id)

    @event.command(name="remove", description="Remove an event (mods/admins)")
    @app_commands.describe(event_id="Event id shown on the calendar")
    async def remove(self, interaction: discord.Interaction, event_id: int) -> None:
        if not await require_manager(interaction):
            return
        assert interaction.guild is not None

        existing = await self.bot.db.get_event(event_id)
        if existing is None or existing.guild_id != interaction.guild.id:
            await send_ephemeral(interaction, "Event not found in this server.")
            return

        await self.bot.db.delete_event(event_id)
        await send_ephemeral(
            interaction, f"Removed **{existing.title}** (id `{event_id}`)."
        )
        await self.bot.refresh_live_calendar(interaction.guild.id)

    @event.command(name="view", description="View an event and mark yourself interested")
    @app_commands.describe(event_id="Event id shown on the calendar")
    async def view(self, interaction: discord.Interaction, event_id: int) -> None:
        if interaction.guild is None:
            await send_ephemeral(interaction, "Use this command in a server.")
            return

        event = await self.bot.db.get_event(event_id)
        if event is None or event.guild_id != interaction.guild.id:
            await send_ephemeral(interaction, "Event not found in this server.")
            return

        user_ids = await self.bot.db.list_interested_user_ids(event_id)
        mentions = [f"<@{uid}>" for uid in user_ids]
        embed = build_event_embed(event, mentions)
        view = EventInterestView(self.bot, event_id)
        await send_ephemeral(interaction, embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventsCog(bot))
