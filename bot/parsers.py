"""Helpers for parsing dates and 24-hour times."""

from __future__ import annotations

import re
from datetime import date, time

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def parse_date(value: str) -> date:
    value = value.strip()
    match = _DATE_RE.match(value)
    if not match:
        raise ValueError("Date must be YYYY-MM-DD (example: 2026-09-17)")
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError as exc:
        raise ValueError("Date must be a real calendar day in YYYY-MM-DD form") from exc


def parse_time_24h(value: str) -> str:
    """Validate HH:MM (24-hour) and return zero-padded HH:MM."""
    value = value.strip()
    match = _TIME_RE.match(value)
    if not match:
        raise ValueError("Use 24-hour time with a colon, e.g. 22:00 or 09:30")
    hour = int(match.group(1))
    minute = int(match.group(2))
    return time(hour, minute).strftime("%H:%M")
