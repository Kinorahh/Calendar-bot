"""Monday weekly snapshot poster."""

from __future__ import annotations

import logging
from datetime import datetime

import discord
from discord.ext import commands, tasks

from bot import config
from bot.formatting import (
    build_week_embed,
    get_tz,
    today_in_tz,
    week_end,
    week_start,
)

log = logging.getLogger(__name__)


class WeeklyCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._last_post_keys: set[str] = set()
        self.weekly_checker.start()

    def cog_unload(self) -> None:
        self.weekly_checker.cancel()

    @tasks.loop(minutes=1)
    async def weekly_checker(self) -> None:
        for settings in await self.bot.db.guilds_with_announcements():
            tz = get_tz(settings.timezone)
            now = datetime.now(tz)
            if now.weekday() != 0:  # Monday
                continue
            if now.hour != config.WEEKLY_POST_HOUR:
                continue

            key = f"{settings.guild_id}:{now.date().isoformat()}"
            if key in self._last_post_keys:
                continue

            channel_id = settings.announcement_channel_id
            if channel_id is None:
                continue
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except discord.HTTPException:
                    log.warning("Could not fetch announce channel %s", channel_id)
                    continue
            if not isinstance(channel, discord.TextChannel):
                continue

            monday = week_start(today_in_tz(settings.timezone))
            events = await self.bot.db.get_events_between(
                settings.guild_id, monday, week_end(monday)
            )
            guild = self.bot.get_guild(settings.guild_id)
            guild_name = guild.name if guild else "Server"
            embed = build_week_embed(
                guild_name=guild_name,
                monday=monday,
                events=events,
                timezone_name=settings.timezone,
                footer="This week's events · posted automatically every Monday",
            )
            try:
                await channel.send(
                    content="🗓️ **This week's events**",
                    embed=embed,
                )
                self._last_post_keys.add(key)
                # Bound memory: drop keys older than ~2 weeks of entries.
                if len(self._last_post_keys) > 500:
                    self._last_post_keys = set(list(self._last_post_keys)[-200:])
                log.info("Posted weekly snapshot for guild %s", settings.guild_id)
            except discord.HTTPException:
                log.exception("Failed weekly post for guild %s", settings.guild_id)

    @weekly_checker.before_loop
    async def before_weekly(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WeeklyCog(bot))
