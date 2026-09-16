"""Private, auto-expiring command replies (not the live calendar)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, Union

import discord

log = logging.getLogger(__name__)

# How long private bot replies stick around before deletion.
TEMP_MESSAGE_SECONDS = 120


def schedule_delete(
    message: discord.Message, delay: float = TEMP_MESSAGE_SECONDS
) -> None:
    """Delete a message after `delay` seconds (best-effort)."""

    async def _runner() -> None:
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except (discord.NotFound, discord.HTTPException):
            pass
        except Exception:
            log.exception("Failed deleting temporary message %s", getattr(message, "id", "?"))

    asyncio.create_task(_runner(), name=f"calbot-del-{getattr(message, 'id', 0)}")


async def send_ephemeral(
    interaction: discord.Interaction,
    content: Optional[str] = None,
    *,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None,
    delete_after: float = TEMP_MESSAGE_SECONDS,
    **kwargs: Any,
) -> Union[discord.InteractionMessage, discord.WebhookMessage]:
    """Send a private reply and auto-delete it after `delete_after` seconds."""
    kwargs.setdefault("ephemeral", True)
    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed
    if view is not None:
        kwargs["view"] = view

    if interaction.response.is_done():
        message = await interaction.followup.send(**kwargs, wait=True)
    else:
        await interaction.response.send_message(**kwargs)
        message = await interaction.original_response()

    if delete_after and delete_after > 0:
        schedule_delete(message, delete_after)
    return message
