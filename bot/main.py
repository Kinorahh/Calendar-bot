"""Bot entrypoint."""

from __future__ import annotations

import logging
import traceback

import discord
from discord import app_commands
from discord.ext import commands

from bot import config
from bot.db import create_database
from bot.formatting import (
    build_week_embed,
    today_in_tz,
    week_end,
    week_start,
)
from bot.messaging import send_ephemeral
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
        self.db = create_database(
            database_url=config.DATABASE_URL,
            sqlite_path=None if config.DATABASE_URL else config.resolve_sqlite_path(),
        )

    async def setup_hook(self) -> None:
        await self.db.connect()
        self.add_view(PersistentWeekCalendarView(self))

        for ext in COGS:
            await self.load_extension(ext)
            log.info("Loaded extension %s", ext)

        try:
            if config.GUILD_ID is not None:
                # Guild-only sync (instant). Also clear globals so Discord
                # doesn't show every command twice.
                guild = discord.Object(id=config.GUILD_ID)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                if self.application_id is not None:
                    await self.http.bulk_upsert_global_commands(self.application_id, [])
                log.info(
                    "Synced %s guild-only commands to %s (cleared global duplicates): %s",
                    len(synced),
                    config.GUILD_ID,
                    ", ".join(self._command_sig(cmd) for cmd in synced),
                )
            else:
                synced = await self.tree.sync()
                log.info(
                    "Synced %s global commands: %s",
                    len(synced),
                    ", ".join(self._command_sig(cmd) for cmd in synced),
                )
        except Exception:
            log.exception("Command sync failed — bot will still run")

    @staticmethod
    def _command_sig(cmd: app_commands.AppCommand) -> str:
        try:
            options = (
                ", ".join(opt.name for opt in cmd.options) if cmd.options else "no options"
            )
            return f"/{cmd.name} ({options})"
        except Exception:
            return f"/{getattr(cmd, 'name', '?')}"

    async def close(self) -> None:
        await self.db.close()
        await super().close()

    async def on_ready(self) -> None:
        log.info("Logged in as %s (%s)", self.user, self.user and self.user.id)
        log.info("Database: %s", self.db.path)

    async def refresh_live_calendar(
        self, guild_id: int, *, force_this_week: bool = False
    ) -> bool:
        """Edit the posted live calendar message for a guild, if configured.

        Returns True if the message was updated.
        When force_this_week is True, jump to the current week (used each Monday).
        """
        settings = await self.db.get_settings(guild_id)
        if not settings.calendar_channel_id or not settings.calendar_message_id:
            log.info(
                "No live calendar linked for guild %s — run /post_calendar "
                "or click This Week on the posted calendar once",
                guild_id,
            )
            return False

        channel = self.get_channel(settings.calendar_channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(settings.calendar_channel_id)
            except discord.HTTPException:
                log.warning("Live calendar channel missing for guild %s", guild_id)
                await self.db.clear_calendar_message(guild_id)
                return False

        if not isinstance(channel, discord.TextChannel):
            return False

        try:
            message = await channel.fetch_message(settings.calendar_message_id)
        except discord.NotFound:
            log.warning("Live calendar message missing for guild %s", guild_id)
            await self.db.clear_calendar_message(guild_id)
            return False
        except discord.HTTPException:
            log.exception("Failed fetching live calendar message for guild %s", guild_id)
            return False

        monday = week_start(today_in_tz(settings.timezone))
        if not force_this_week:
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
            log.info(
                "Refreshed live calendar guild=%s channel=%s message=%s week=%s events=%s",
                guild_id,
                settings.calendar_channel_id,
                settings.calendar_message_id,
                monday.isoformat(),
                len(events),
            )
            return True
        except discord.HTTPException:
            log.exception("Failed editing live calendar for guild %s", guild_id)
            return False


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
        try:
            await send_ephemeral(
                interaction, "Something went wrong running that command."
            )
        except discord.HTTPException:
            log.exception("Failed to send command error response")

    bot.run(config.DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
