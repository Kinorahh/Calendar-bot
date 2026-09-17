"""Create commands (matches)."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot import config
from bot.match_wizard import (
    MatchCreateProceedView,
    side_display_name,
    side_kind,
)
from bot.messaging import send_ephemeral


class CreateCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    create = app_commands.Group(name="create", description="Create calendar entries")

    @create.command(
        name="match",
        description="Schedule a match between two users or two roles",
    )
    @app_commands.describe(
        side_a="First player or role",
        side_b="Second player or role (same kind as side_a)",
    )
    async def match(
        self,
        interaction: discord.Interaction,
        side_a: discord.User | discord.Role,
        side_b: discord.User | discord.Role,
    ) -> None:
        if interaction.guild is None:
            await send_ephemeral(interaction, "Use this command in a server.")
            return

        if config.MATCH_CHANNEL_ID is None:
            await send_ephemeral(
                interaction,
                "Match channel is not configured. Set `MATCH_CHANNEL_ID` in Railway.",
            )
            return

        if interaction.channel_id != config.MATCH_CHANNEL_ID:
            await send_ephemeral(
                interaction,
                f"Use `/create match` in <#{config.MATCH_CHANNEL_ID}> only.",
            )
            return

        # Prefer guild Member objects when available (for display names).
        resolved_a: discord.User | discord.Member | discord.Role = side_a
        resolved_b: discord.User | discord.Member | discord.Role = side_b
        if isinstance(side_a, discord.User) and not isinstance(side_a, discord.Role):
            member_a = interaction.guild.get_member(side_a.id)
            if member_a is not None:
                resolved_a = member_a
        if isinstance(side_b, discord.User) and not isinstance(side_b, discord.Role):
            member_b = interaction.guild.get_member(side_b.id)
            if member_b is not None:
                resolved_b = member_b

        if side_kind(resolved_a) != side_kind(resolved_b):
            await send_ephemeral(
                interaction,
                "Both sides must be the same kind — two users, or two roles.",
            )
            return

        if resolved_a.id == resolved_b.id:
            await send_ephemeral(interaction, "Pick two different players or roles.")
            return

        view = MatchCreateProceedView(
            self.bot,
            interaction.guild.id,
            interaction.user.id,
            resolved_a,
            resolved_b,
            config.MATCH_CHANNEL_ID,
        )
        await send_ephemeral(
            interaction,
            f"Click **Proceed** to schedule **{side_display_name(resolved_a)} vs "
            f"{side_display_name(resolved_b)}** "
            "(date as `YYYY-MM-DD`, and time like `9:00 PM`).",
            view=view,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CreateCog(bot))
