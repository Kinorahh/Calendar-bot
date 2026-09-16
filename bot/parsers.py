"""Helpers for parsing dates and 24-hour times."""

from __future__ import annotations

import re
from datetime import date, datetime, time

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def parse_date(value: str) -> date:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError("Use YYYY-MM-DD or MM/DD/YYYY (example: 2026-09-17)")


def parse_time_24h(value: str) -> str:
    """Validate HH:MM (24-hour) and return zero-padded HH:MM."""
    value = value.strip()
    match = _TIME_RE.match(value)
    if not match:
        raise ValueError("Use 24-hour time with a colon, e.g. 22:00 or 09:30")
    hour = int(match.group(1))
    minute = int(match.group(2))
    return time(hour, minute).strftime("%H:%M")
