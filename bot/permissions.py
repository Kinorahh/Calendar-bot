"""Permission helpers for calendar management."""

from __future__ import annotations

import discord

from bot import config


def can_manage_events(member: discord.Member) -> bool:
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        return True
    return any(role.name.lower() in config.ADMIN_ROLE_NAMES for role in member.roles)


async def require_manager(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "This command can only be used in a server.", ephemeral=True
        )
        return False
    if not can_manage_events(interaction.user):
        await interaction.response.send_message(
            "Only mods/admins can manage calendar events.", ephemeral=True
        )
        return False
    return True
