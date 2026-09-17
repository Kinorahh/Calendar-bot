"""Match creation wizard (Proceed → date/time modal)."""

from __future__ import annotations

import logging
import traceback
from typing import TYPE_CHECKING, Union

import discord

from bot.messaging import schedule_delete, send_ephemeral
from bot.parsers import parse_date, parse_time_12h

if TYPE_CHECKING:
    from bot.main import CalendarBot

log = logging.getLogger(__name__)

MentionableSide = Union[discord.Member, discord.User, discord.Role]


def side_kind(side: MentionableSide) -> str:
    if isinstance(side, discord.Role):
        return "role"
    return "user"


def side_display_name(side: MentionableSide) -> str:
    if isinstance(side, discord.Role):
        return side.name
    if isinstance(side, discord.Member):
        return side.display_name
    return side.name


def side_mention(side: MentionableSide) -> str:
    return side.mention


def side_storage(side: MentionableSide) -> tuple[str, int]:
    return side_kind(side), side.id


class MatchInfoModal(discord.ui.Modal, title="New match"):
    """Date and time only — title is auto-generated from the two sides."""

    def __init__(
        self,
        bot: "CalendarBot",
        guild_id: int,
        user_id: int,
        side_a: MentionableSide,
        side_b: MentionableSide,
        calendar_channel_id: int | None,
    ) -> None:
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id
        self.side_a = side_a
        self.side_b = side_b
        self.calendar_channel_id = calendar_channel_id

        self.date_input = discord.ui.TextInput(
            label="Date (YYYY-MM-DD only)",
            placeholder="2026-09-17",
            min_length=10,
            max_length=10,
            required=True,
            style=discord.TextStyle.short,
        )
        self.time_input = discord.ui.TextInput(
            label="Time (12-hour, e.g. 9:00 PM)",
            placeholder="9:00 PM",
            min_length=4,
            max_length=8,
            required=True,
            style=discord.TextStyle.short,
        )
        self.add_item(self.date_input)
        self.add_item(self.time_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            event_date = parse_date(str(self.date_input.value))
            event_time = parse_time_12h(str(self.time_input.value))
        except ValueError as exc:
            await send_ephemeral(interaction, str(exc))
            return

        name_a = side_display_name(self.side_a)
        name_b = side_display_name(self.side_b)
        title = f"{name_a} vs {name_b}"
        match_a_type, match_a_id = side_storage(self.side_a)
        match_b_type, match_b_id = side_storage(self.side_b)

        try:
            event = await self.bot.db.add_event(
                guild_id=self.guild_id,
                title=title,
                event_date=event_date,
                event_time=event_time,
                description="",
                created_by=self.user_id,
                match_a_type=match_a_type,
                match_a_id=match_a_id,
                match_b_type=match_b_type,
                match_b_id=match_b_id,
            )
        except Exception:
            log.exception("Failed to save match")
            await send_ephemeral(
                interaction, "Could not save that match. Try again in a moment."
            )
            return

        await send_ephemeral(
            interaction,
            f"Scheduled **{event.title}** for "
            f"{event.event_date.isoformat()} at {event.event_time} (id `{event.id}`).",
        )

        try:
            updated = await self.bot.refresh_live_calendar(self.guild_id)
            if not updated:
                await send_ephemeral(
                    interaction,
                    "Match saved, but the posted calendar isn’t linked for auto-updates yet. "
                    "Run `/post_calendar` once (or click **This Week** on the existing "
                    "calendar message) — then new events will update it automatically.",
                )
        except Exception:
            log.exception("Failed refreshing live calendar after match create")

        # Embeds never notify — a normal message content mention is required to ping.
        ping = (
            f"{side_mention(self.side_a)} vs {side_mention(self.side_b)} "
            f"— match scheduled for **{event.event_date.isoformat()}** at **{event.event_time}**"
        )
        target_channel: discord.abc.Messageable | None = None
        if self.calendar_channel_id is not None:
            channel = self.bot.get_channel(self.calendar_channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(self.calendar_channel_id)
                except discord.HTTPException:
                    channel = None
            if isinstance(channel, discord.TextChannel):
                target_channel = channel
        if target_channel is None and interaction.channel is not None:
            if isinstance(interaction.channel, discord.TextChannel):
                target_channel = interaction.channel

        if target_channel is not None:
            try:
                message = await target_channel.send(
                    ping,
                    allowed_mentions=discord.AllowedMentions(
                        users=True,
                        roles=True,
                        everyone=False,
                    ),
                )
                # Notification still delivers; message cleans itself up after 2 minutes.
                schedule_delete(message, 120)
            except discord.HTTPException:
                log.exception("Failed sending match ping message")

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.error("MatchInfoModal error: %s\n%s", error, traceback.format_exc())
        try:
            await send_ephemeral(interaction, "Something went wrong saving the match.")
        except discord.HTTPException:
            pass


class MatchCreateProceedView(discord.ui.View):
    """Ephemeral Proceed button that opens the match date/time form."""

    def __init__(
        self,
        bot: "CalendarBot",
        guild_id: int,
        user_id: int,
        side_a: MentionableSide,
        side_b: MentionableSide,
        calendar_channel_id: int | None,
    ) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id
        self.side_a = side_a
        self.side_b = side_b
        self.calendar_channel_id = calendar_channel_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await send_ephemeral(
                interaction,
                "This setup is only for the person who ran `/create match`.",
            )
            return False
        return True

    @discord.ui.button(label="Proceed", style=discord.ButtonStyle.primary)
    async def proceed(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            MatchInfoModal(
                self.bot,
                self.guild_id,
                self.user_id,
                self.side_a,
                self.side_b,
                self.calendar_channel_id,
            )
        )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item
    ) -> None:
        log.error("MatchCreateProceedView error: %s\n%s", error, traceback.format_exc())
        try:
            await send_ephemeral(interaction, "Something went wrong opening the form.")
        except discord.HTTPException:
            pass
