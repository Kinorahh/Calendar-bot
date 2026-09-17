"""Setup and live calendar commands."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.formatting import build_week_embed, today_in_tz, week_end, week_start
from bot.messaging import send_ephemeral
from bot.permissions import require_admin
from bot.views import PersistentWeekCalendarView


class CalendarCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="post_calendar",
        description="Post a live calendar message that updates when events change (admins)",
    )
    @app_commands.describe(channel="Channel for the live calendar (defaults to current)")
    async def post_calendar(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        if not await require_admin(interaction):
            return
        assert interaction.guild is not None

        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await send_ephemeral(interaction, "Pick a text channel for the live calendar.")
            return

        await interaction.response.defer(ephemeral=True)

        settings = await self.bot.db.get_settings(interaction.guild.id)
        monday = week_start(today_in_tz(settings.timezone))
        events = await self.bot.db.get_events_between(
            interaction.guild.id, monday, week_end(monday)
        )
        embed = build_week_embed(
            guild_name=interaction.guild.name,
            monday=monday,
            events=events,
            timezone_name=settings.timezone,
            footer=PersistentWeekCalendarView.footer_for(monday, settings.timezone),
        )
        view = PersistentWeekCalendarView(self.bot)
        # Public live calendar — this is the one message that stays in the channel.
        message = await target.send(embed=embed, view=view)
        await self.bot.db.upsert_settings(
            interaction.guild.id,
            calendar_channel_id=target.id,
            calendar_message_id=message.id,
        )
        await send_ephemeral(
            interaction,
            f"Live calendar posted in {target.mention}. It will refresh when events change.",
        )

    setup_group = app_commands.Group(
        name="setup", description="Configure the calendar bot (admins)"
    )

    @setup_group.command(
        name="timezone",
        description="Set the server timezone used for weeks and Monday advance",
    )
    @app_commands.describe(timezone="IANA timezone, e.g. America/New_York")
    async def timezone_cmd(
        self, interaction: discord.Interaction, timezone: str
    ) -> None:
        if not await require_admin(interaction):
            return
        assert interaction.guild is not None
        from zoneinfo import ZoneInfo

        try:
            ZoneInfo(timezone)
        except Exception:
            await send_ephemeral(
                interaction,
                "Invalid timezone. Use an IANA name like `America/New_York` or `America/Chicago`.",
            )
            return

        await self.bot.db.upsert_settings(interaction.guild.id, timezone_name=timezone)
        await send_ephemeral(interaction, f"Timezone set to `{timezone}`.")

    @setup_group.command(name="status", description="Show current calendar bot settings")
    async def status(self, interaction: discord.Interaction) -> None:
        if not await require_admin(interaction):
            return
        assert interaction.guild is not None

        settings = await self.bot.db.get_settings(interaction.guild.id)
        live = (
            f"<#{settings.calendar_channel_id}> (msg `{settings.calendar_message_id}`)"
            if settings.calendar_channel_id and settings.calendar_message_id
            else "_not set — use /post_calendar_"
        )
        await send_ephemeral(
            interaction,
            f"**Timezone:** `{settings.timezone}`\n"
            f"**Live calendar:** {live}",
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CalendarCog(bot))
