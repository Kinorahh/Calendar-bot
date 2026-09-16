"""Calendar Bot — Discord week calendar with live event updates."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = os.getenv("GUILD_ID", "").strip() or None
TIMEZONE = os.getenv("TIMEZONE", "America/New_York").strip()
WEEKLY_POST_HOUR = int(os.getenv("WEEKLY_POST_HOUR", "9"))
ADMIN_ROLE_NAMES = {
    name.strip().lower()
    for name in os.getenv("ADMIN_ROLE_NAMES", "Admin,Moderator,Mod,Calendar Admin").split(",")
    if name.strip()
}

_default_db = Path(__file__).resolve().parent.parent / "data" / "calendar.db"
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(_default_db))).expanduser()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
