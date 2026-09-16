"""Single-form event creation (Discord modals cannot do multi-page Next steps)."""

from __future__ import annotations

import logging
import traceback
from typing import TYPE_CHECKING

import discord

from bot.parsers import parse_date, parse_time_24h

if TYPE_CHECKING:
    from bot.main import CalendarBot

log = logging.getLogger(__name__)


class EventInfoModal(discord.ui.Modal, title="New calendar event"):
    """One window: title, date, and time — then Submit once."""

    def __init__(self, bot: "CalendarBot", guild_id: int, user_id: int) -> None:
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id

        self.title_input = discord.ui.TextInput(
            label="Event title",
            placeholder="Game Night",
            max_length=100,
            required=True,
            style=discord.TextStyle.short,
        )
        self.date_input = discord.ui.TextInput(
            label="Date (YYYY-MM-DD only)",
            placeholder="2026-09-17",
            min_length=10,
            max_length=10,
            required=True,
            style=discord.TextStyle.short,
        )
        self.time_input = discord.ui.TextInput(
            label="Time (24-hour, e.g. 22:00)",
            placeholder="22:00",
            min_length=4,
            max_length=5,
            required=True,
            style=discord.TextStyle.short,
        )
        self.add_item(self.title_input)
        self.add_item(self.date_input)
        self.add_item(self.time_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        title = str(self.title_input.value).strip()
        try:
            event_date = parse_date(str(self.date_input.value))
            event_time = parse_time_24h(str(self.time_input.value))
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        try:
            event = await self.bot.db.add_event(
                guild_id=self.guild_id,
                title=title,
                event_date=event_date,
                event_time=event_time,
                description="",
                created_by=self.user_id,
            )
        except Exception:
            log.exception("Failed to save event")
            await interaction.response.send_message(
                "Could not save that event. Try again in a moment.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Added **{event.event_time} {event.title}** on "
            f"{event.event_date.isoformat()} (id `{event.id}`).",
            ephemeral=True,
        )
        try:
            updated = await self.bot.refresh_live_calendar(self.guild_id)
            if not updated:
                await interaction.followup.send(
                    "Event saved, but the posted calendar isn’t linked for auto-updates yet. "
                    "Run `/post_calendar` once (or click **This Week** on the existing "
                    "calendar message) — then new events will update it automatically.",
                    ephemeral=True,
                )
        except Exception:
            log.exception("Failed refreshing live calendar after add")

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.error("EventInfoModal error: %s\n%s", error, traceback.format_exc())
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    "Something went wrong saving the event.", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "Something went wrong saving the event.", ephemeral=True
                )
        except discord.HTTPException:
            pass


class EventAddProceedView(discord.ui.View):
    """Ephemeral Proceed button that opens the single event form."""

    def __init__(self, bot: "CalendarBot", guild_id: int, user_id: int) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This setup is only for the person who ran `/event add`.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Proceed", style=discord.ButtonStyle.primary)
    async def proceed(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            EventInfoModal(self.bot, self.guild_id, self.user_id)
        )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item
    ) -> None:
        log.error("EventAddProceedView error: %s\n%s", error, traceback.format_exc())
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    "Something went wrong opening the form.", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "Something went wrong opening the form.", ephemeral=True
                )
        except discord.HTTPException:
            pass
