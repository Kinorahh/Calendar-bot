"""Bot entrypoint."""

from __future__ import annotations

import logging
import traceback

import discord
from discord import app_commands
from discord.ext import commands

from bot import config
from bot.db import Database
from bot.formatting import (
    build_week_embed,
    today_in_tz,
    week_end,
    week_start,
)
from bot.views import PersistentWeekCalendarView

log = logging.getLogger(__name__)

COGS = (
    "bot.cogs.calendar_cog",
    "bot.cogs.events_cog",
    "bot.cogs.weekly_cog",
)


class CalendarBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents)
        self.db = Database(config.DATABASE_PATH)

    async def setup_hook(self) -> None:
        await self.db.connect()
        self.add_view(PersistentWeekCalendarView(self))

        for ext in COGS:
            await self.load_extension(ext)

        # Global sync can take up to ~1 hour to reach Discord clients.
        synced = await self.tree.sync()
        log.info(
            "Synced %s global commands: %s",
            len(synced),
            ", ".join(self._command_sig(cmd) for cmd in synced),
        )

        # Guild sync is instant — set GUILD_ID in Railway while testing.
        if config.GUILD_ID:
            guild = discord.Object(id=int(config.GUILD_ID))
            # Clear stale guild copies (e.g. old /event add with options), then resync.
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info(
                "Synced %s guild commands to %s: %s",
                len(synced),
                config.GUILD_ID,
                ", ".join(self._command_sig(cmd) for cmd in synced),
            )

    @staticmethod
    def _command_sig(cmd: app_commands.AppCommand) -> str:
        options = ", ".join(opt.name for opt in cmd.options) if cmd.options else "no options"
        return f"/{cmd.name} ({options})"

    async def close(self) -> None:
        await self.db.close()
        await super().close()

    async def on_ready(self) -> None:
        log.info("Logged in as %s (%s)", self.user, self.user and self.user.id)

    async def refresh_live_calendar(self, guild_id: int) -> None:
        """Edit the posted live calendar message for a guild, if configured."""
        settings = await self.db.get_settings(guild_id)
        if not settings.calendar_channel_id or not settings.calendar_message_id:
            return

        channel = self.get_channel(settings.calendar_channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(settings.calendar_channel_id)
            except discord.HTTPException:
                log.warning("Live calendar channel missing for guild %s", guild_id)
                await self.db.clear_calendar_message(guild_id)
                return

        if not isinstance(channel, discord.TextChannel):
            return

        try:
            message = await channel.fetch_message(settings.calendar_message_id)
        except discord.NotFound:
            await self.db.clear_calendar_message(guild_id)
            return
        except discord.HTTPException:
            log.exception("Failed fetching live calendar message for guild %s", guild_id)
            return

        monday = week_start(today_in_tz(settings.timezone))
        viewed = PersistentWeekCalendarView.parse_monday(message)
        if viewed is not None:
            monday = viewed

        events = await self.db.get_events_between(guild_id, monday, week_end(monday))
        guild = self.get_guild(guild_id)
        guild_name = guild.name if guild else "Server"
        embed = build_week_embed(
            guild_name=guild_name,
            monday=monday,
            events=events,
            timezone_name=settings.timezone,
            footer=PersistentWeekCalendarView.footer_for(monday, settings.timezone),
        )
        view = PersistentWeekCalendarView(self)
        try:
            await message.edit(embed=embed, view=view)
        except discord.HTTPException:
            log.exception("Failed editing live calendar for guild %s", guild_id)


def main() -> None:
    config.configure_logging()
    if not config.DISCORD_TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN is not set. Copy .env.example to .env or set Railway variables."
        )

    bot = CalendarBot()

    @bot.tree.error
    async def on_app_command_error(
        interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        log.error("Command error: %s\n%s", error, traceback.format_exc())
        message = "Something went wrong running that command."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    bot.run(config.DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
