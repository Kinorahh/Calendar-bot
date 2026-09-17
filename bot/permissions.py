"""Permission helpers for calendar management."""

from __future__ import annotations

import discord

from bot import config
from bot.messaging import send_ephemeral
from bot.models import Event


def has_admin_role(member: discord.Member) -> bool:
    """True if the member has a role listed in ADMIN_ROLE_NAMES."""
    return any(role.name.lower() in config.ADMIN_ROLE_NAMES for role in member.roles)


def can_manage_interaction(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        return False
    return has_admin_role(interaction.user)


def is_match_participant(member: discord.Member, event: Event) -> bool:
    """Either listed player, or anyone with either listed role."""
    if not event.is_match:
        return False

    for side_type, side_id in (
        (event.match_a_type, event.match_a_id),
        (event.match_b_type, event.match_b_id),
    ):
        if side_id is None or side_type is None:
            continue
        if side_type == "user" and member.id == side_id:
            return True
        if side_type == "role" and any(role.id == side_id for role in member.roles):
            return True
    return False


def can_modify_event(interaction: discord.Interaction, event: Event) -> bool:
    """Admins can modify any event; match participants can modify their own match."""
    if not isinstance(interaction.user, discord.Member):
        return False
    if has_admin_role(interaction.user):
        return True
    return is_match_participant(interaction.user, event)


async def require_admin(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        await send_ephemeral(
            interaction, "This command can only be used in a server."
        )
        return False
    if not can_manage_interaction(interaction):
        await send_ephemeral(
            interaction,
            "Only users with an admin role "
            f"({', '.join(sorted(config.ADMIN_ROLE_NAMES))}) can use this command.",
        )
        return False
    return True


# Backwards-compatible alias used in older call sites.
require_manager = require_admin
