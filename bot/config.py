"""Calendar Bot — Discord week calendar with live event updates."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()

_raw_guild = os.getenv("GUILD_ID", "").strip().strip('"').strip("'")
GUILD_ID: int | None
if _raw_guild:
    try:
        GUILD_ID = int(_raw_guild)
    except ValueError:
        GUILD_ID = None
        logging.getLogger(__name__).warning("Invalid GUILD_ID %r — ignoring", _raw_guild)
else:
    GUILD_ID = None

_raw_match_channel = os.getenv("MATCH_CHANNEL_ID", "").strip().strip('"').strip("'")
MATCH_CHANNEL_ID: int | None
if _raw_match_channel:
    try:
        MATCH_CHANNEL_ID = int(_raw_match_channel)
    except ValueError:
        MATCH_CHANNEL_ID = None
        logging.getLogger(__name__).warning(
            "Invalid MATCH_CHANNEL_ID %r — ignoring", _raw_match_channel
        )
else:
    MATCH_CHANNEL_ID = None

TIMEZONE = os.getenv("TIMEZONE", "America/New_York").strip()

try:
    WEEKLY_POST_HOUR = int(os.getenv("WEEKLY_POST_HOUR", "9"))
except ValueError:
    WEEKLY_POST_HOUR = 9

ADMIN_ROLE_NAMES = {
    name.strip().lower()
    for name in os.getenv("ADMIN_ROLE_NAMES", "Admin,Moderator,Mod,Calendar Admin").split(",")
    if name.strip()
}

# Prefer Postgres on Railway (DATABASE_URL). SQLite is for local/dev only.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or None

_default_db = Path(__file__).resolve().parent.parent / "data" / "calendar.db"
_env_db = os.getenv("DATABASE_PATH", "").strip()
DATABASE_PATH = Path(_env_db).expanduser() if _env_db else _default_db

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )


def resolve_sqlite_path() -> Path:
    """Use DATABASE_PATH, or fall back to ./data if the preferred path isn't writable."""
    preferred = DATABASE_PATH
    try:
        preferred.parent.mkdir(parents=True, exist_ok=True)
        probe = preferred.parent / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return preferred
    except OSError:
        fallback = _default_db
        fallback.parent.mkdir(parents=True, exist_ok=True)
        logging.getLogger(__name__).warning(
            "Cannot write %s — using %s instead", preferred, fallback
        )
        return fallback
