"""Interactive Discord views for week navigation and event interest."""

from __future__ import annotations

import re
from datetime import date
from typing import TYPE_CHECKING, Optional

import discord

from bot.formatting import (
    build_event_embed,
    build_week_embed,
    shift_week,
    today_in_tz,
    week_end,
    week_start,
)
from bot.messaging import TEMP_MESSAGE_SECONDS, send_ephemeral

if TYPE_CHECKING:
    from bot.db import Database
    from bot.main import CalendarBot


_MONDAY_RE = re.compile(r"monday:(?P<iso>\d{4}-\d{2}-\d{2})")


class PersistentWeekCalendarView(discord.ui.View):
    """Persistent controls for the live calendar message (survives restarts)."""

    def __init__(self, bot: discord.Client) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @property
    def db(self) -> "Database":
        return self.bot.db  # type: ignore[attr-defined]

    @staticmethod
    def footer_for(monday: date, timezone_name: str) -> str:
        return f"Live calendar · monday:{monday.isoformat()} · {timezone_name}"

    @classmethod
    def parse_monday(cls, message: discord.Message) -> Optional[date]:
        embed = message.embeds[0] if message.embeds else None
        if embed is None or not embed.footer or not embed.footer.text:
            return None
        match = _MONDAY_RE.search(embed.footer.text)
        if not match:
            return None
        try:
            return date.fromisoformat(match.group("iso"))
        except ValueError:
            return None

    async def _current_monday(self, interaction: discord.Interaction) -> date:
        assert interaction.guild is not None
        settings = await self.db.get_settings(interaction.guild.id)
        if interaction.message is not None:
            parsed = self.parse_monday(interaction.message)
            if parsed is not None:
                return parsed
        return week_start(today_in_tz(settings.timezone))

    async def _remember_live_message(self, interaction: discord.Interaction) -> None:
        """Keep DB pointed at this calendar message so event edits can refresh it."""
        if interaction.guild is None or interaction.message is None:
            return
        # Ephemeral /calendar replies should not become the live calendar target.
        if interaction.message.flags.ephemeral:
            return
        channel_id = interaction.channel_id
        if channel_id is None:
            return
        await self.db.upsert_settings(
            interaction.guild.id,
            calendar_channel_id=channel_id,
            calendar_message_id=interaction.message.id,
        )

    async def _render(self, interaction: discord.Interaction, monday: date) -> None:
        assert interaction.guild is not None
        await self._remember_live_message(interaction)
        settings = await self.db.get_settings(interaction.guild.id)
        events = await self.db.get_events_between(
            interaction.guild.id, monday, week_end(monday)
        )
        embed = build_week_embed(
            guild_name=interaction.guild.name,
            monday=monday,
            events=events,
            timezone_name=settings.timezone,
            footer=self.footer_for(monday, settings.timezone),
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def _require_week_nav(self, interaction: discord.Interaction) -> bool:
        from bot.permissions import can_manage_interaction

        if not can_manage_interaction(interaction):
            await send_ephemeral(
                interaction,
                "Only mods/admins can browse other weeks.",
            )
            return False
        return True

    @discord.ui.button(
        label="◀ Prev",
        style=discord.ButtonStyle.secondary,
        custom_id="calendar:prev",
    )
    async def prev_week(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not await self._require_week_nav(interaction):
            return
        monday = await self._current_monday(interaction)
        await self._render(interaction, shift_week(monday, -1))

    @discord.ui.button(
        label="This Week",
        style=discord.ButtonStyle.primary,
        custom_id="calendar:today",
    )
    async def this_week(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        assert interaction.guild is not None
        settings = await self.db.get_settings(interaction.guild.id)
        monday = week_start(today_in_tz(settings.timezone))
        await self._render(interaction, monday)

    @discord.ui.button(
        label="Next ▶",
        style=discord.ButtonStyle.secondary,
        custom_id="calendar:next",
    )
    async def next_week(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not await self._require_week_nav(interaction):
            return
        monday = await self._current_monday(interaction)
        await self._render(interaction, shift_week(monday, 1))


class WeekCalendarView(PersistentWeekCalendarView):
    """Same controls for ephemeral /calendar replies (not restart-persistent)."""

    def __init__(self, bot: discord.Client, monday: date, guild_id: int) -> None:
        super().__init__(bot)
        self.timeout = TEMP_MESSAGE_SECONDS
        self.monday = monday
        self.guild_id = guild_id
        # Ephemeral replies should not reuse the persistent custom_ids.
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.custom_id:
                child.custom_id = None


class EventInterestView(discord.ui.View):
    def __init__(self, bot: discord.Client, event_id: int) -> None:
        super().__init__(timeout=TEMP_MESSAGE_SECONDS)
        self.bot = bot
        self.event_id = event_id

    @property
    def db(self) -> "Database":
        return self.bot.db  # type: ignore[attr-defined]

    @discord.ui.button(label="⭐ Interested", style=discord.ButtonStyle.success)
    async def toggle(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        event = await self.db.get_event(self.event_id)
        if event is None:
            await send_ephemeral(interaction, "That event no longer exists.")
            return

        interested, count = await self.db.toggle_interest(
            self.event_id, interaction.user.id
        )
        event.interested_count = count
        user_ids = await self.db.list_interested_user_ids(self.event_id)
        mentions = [f"<@{uid}>" for uid in user_ids]
        embed = build_event_embed(event, mentions)

        status = "marked as interested" if interested else "removed your interest"
        await interaction.response.edit_message(embed=embed, view=self)
        await send_ephemeral(
            interaction,
            f"You {status} in **{event.title}** ({count} interested).",
        )

        refresher = getattr(self.bot, "refresh_live_calendar", None)
        if callable(refresher) and interaction.guild is not None:
            await refresher(interaction.guild.id)
