"""Event create / edit / remove / view commands."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.add_wizard import EventDraft, EventNameModal
from bot.formatting import build_event_embed
from bot.parsers import parse_date, parse_time_24h
from bot.permissions import require_manager
from bot.views import EventInterestView


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    event = app_commands.Group(name="event", description="Manage and view calendar events")

    @event.command(
        name="add",
        description="Add an event with a private step-by-step form (mods/admins)",
    )
    async def add(self, interaction: discord.Interaction) -> None:
        if not await require_manager(interaction):
            return
        assert interaction.guild is not None

        draft = EventDraft(guild_id=interaction.guild.id, user_id=interaction.user.id)
        # Responding with a modal must be the first (and immediate) response.
        await interaction.response.send_modal(EventNameModal(self.bot, draft))


    @event.command(name="edit", description="Edit an existing event (mods/admins)")
    @app_commands.describe(
        event_id="Event id shown on the calendar",
        title="New title",
        date="New date YYYY-MM-DD or MM/DD/YYYY",
        time="New time in 24-hour format, e.g. 22:00",
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
            await interaction.response.send_message(
                "Event not found in this server.", ephemeral=True
            )
            return

        event_date = None
        if date is not None:
            try:
                event_date = parse_date(date)
            except ValueError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return

        parsed_time = None
        if time is not None and not clear_time:
            try:
                parsed_time = parse_time_24h(time)
            except ValueError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
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
        await interaction.response.send_message(
            f"Updated **{updated.title}** (id `{updated.id}`).", ephemeral=True
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
            await interaction.response.send_message(
                "Event not found in this server.", ephemeral=True
            )
            return

        await self.bot.db.delete_event(event_id)
        await interaction.response.send_message(
            f"Removed **{existing.title}** (id `{event_id}`).", ephemeral=True
        )
        await self.bot.refresh_live_calendar(interaction.guild.id)

    @event.command(name="view", description="View an event and mark yourself interested")
    @app_commands.describe(event_id="Event id shown on the calendar")
    async def view(self, interaction: discord.Interaction, event_id: int) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Use this command in a server.", ephemeral=True
            )
            return

        event = await self.bot.db.get_event(event_id)
        if event is None or event.guild_id != interaction.guild.id:
            await interaction.response.send_message(
                "Event not found in this server.", ephemeral=True
            )
            return

        user_ids = await self.bot.db.list_interested_user_ids(event_id)
        mentions = [f"<@{uid}>" for uid in user_ids]
        embed = build_event_embed(event, mentions)
        view = EventInterestView(self.bot, event_id)
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventsCog(bot))
