"""Monday live calendar week advance."""

from __future__ import annotations

import logging
from datetime import datetime

from discord.ext import commands, tasks

from bot.formatting import get_tz

log = logging.getLogger(__name__)


class WeeklyCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._last_advance_keys: set[str] = set()
        self.weekly_checker.start()

    def cog_unload(self) -> None:
        self.weekly_checker.cancel()

    @tasks.loop(minutes=1)
    async def weekly_checker(self) -> None:
        await self._advance_live_calendars()

    async def _advance_live_calendars(self) -> None:
        """On Monday, snap the posted live calendar to the new week automatically."""
        for settings in await self.bot.db.guilds_with_live_calendar():
            tz = get_tz(settings.timezone)
            now = datetime.now(tz)
            if now.weekday() != 0:  # Monday
                continue
            # Advance early Monday morning so the calendar is current all week.
            if now.hour != 0:
                continue

            key = f"advance:{settings.guild_id}:{now.date().isoformat()}"
            if key in self._last_advance_keys:
                continue

            try:
                updated = await self.bot.refresh_live_calendar(
                    settings.guild_id, force_this_week=True
                )
                if updated:
                    self._last_advance_keys.add(key)
                    log.info(
                        "Advanced live calendar to current week for guild %s",
                        settings.guild_id,
                    )
            except Exception:
                log.exception(
                    "Failed advancing live calendar for guild %s", settings.guild_id
                )

            if len(self._last_advance_keys) > 500:
                self._last_advance_keys = set(list(self._last_advance_keys)[-200:])

    @weekly_checker.before_loop
    async def before_weekly(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WeeklyCog(bot))
