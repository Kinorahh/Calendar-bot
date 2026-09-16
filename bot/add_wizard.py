"""Step-by-step ephemeral wizard for /event add."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Optional

import discord

from bot.parsers import parse_date, parse_time_24h

if TYPE_CHECKING:
    from bot.main import CalendarBot


@dataclass
class EventDraft:
    guild_id: int
    user_id: int
    title: Optional[str] = None
    event_date: Optional[date] = None
    event_time: Optional[str] = None
    description: str = ""


class EventNameModal(discord.ui.Modal, title="Event name"):
    name = discord.ui.TextInput(
        label="Event name",
        placeholder="Game Night",
        max_length=100,
        required=True,
    )

    def __init__(self, bot: "CalendarBot", draft: EventDraft) -> None:
        super().__init__()
        self.bot = bot
        self.draft = draft

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.draft.title = str(self.name.value).strip()
        view = EventAddWizardView(self.bot, self.draft, step="date")
        await interaction.response.send_message(
            f"**Step 2/3 — Date**\n"
            f"Name: **{self.draft.title}**\n\n"
            f"Click **Next** and enter the date (`YYYY-MM-DD` or `MM/DD/YYYY`).",
            view=view,
            ephemeral=True,
        )


class EventDateModal(discord.ui.Modal, title="Event date"):
    date_input = discord.ui.TextInput(
        label="Date",
        placeholder="2026-09-17",
        max_length=10,
        required=True,
    )

    def __init__(self, bot: "CalendarBot", draft: EventDraft) -> None:
        super().__init__()
        self.bot = bot
        self.draft = draft

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            self.draft.event_date = parse_date(str(self.date_input.value))
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        view = EventAddWizardView(self.bot, self.draft, step="time")
        await interaction.response.send_message(
            f"**Step 3/3 — Time**\n"
            f"Name: **{self.draft.title}**\n"
            f"Date: **{self.draft.event_date.isoformat()}**\n\n"
            f"Click **Next** and enter the time in 24-hour format (`22:00`).",
            view=view,
            ephemeral=True,
        )


class EventTimeModal(discord.ui.Modal, title="Event time"):
    time_input = discord.ui.TextInput(
        label="Time (24-hour)",
        placeholder="22:00",
        max_length=5,
        required=True,
    )

    def __init__(self, bot: "CalendarBot", draft: EventDraft) -> None:
        super().__init__()
        self.bot = bot
        self.draft = draft

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            self.draft.event_time = parse_time_24h(str(self.time_input.value))
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        assert self.draft.title and self.draft.event_date and self.draft.event_time
        event = await self.bot.db.add_event(
            guild_id=self.draft.guild_id,
            title=self.draft.title,
            event_date=self.draft.event_date,
            event_time=self.draft.event_time,
            description=self.draft.description,
            created_by=self.draft.user_id,
        )
        await interaction.response.send_message(
            f"Added **{event.event_time} {event.title}** on "
            f"{event.event_date.isoformat()} (id `{event.id}`).",
            ephemeral=True,
        )
        await self.bot.refresh_live_calendar(self.draft.guild_id)


class EventAddWizardView(discord.ui.View):
    """Ephemeral Next button that opens the modal for the current step."""

    def __init__(self, bot: "CalendarBot", draft: EventDraft, step: str) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.draft = draft
        self.step = step

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.draft.user_id:
            await interaction.response.send_message(
                "This setup is only for the person who ran `/event add`.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_step(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self.step == "name":
            await interaction.response.send_modal(EventNameModal(self.bot, self.draft))
        elif self.step == "date":
            await interaction.response.send_modal(EventDateModal(self.bot, self.draft))
        elif self.step == "time":
            await interaction.response.send_modal(EventTimeModal(self.bot, self.draft))
        else:
            await interaction.response.send_message(
                "This wizard step expired. Run `/event add` again.",
                ephemeral=True,
            )
