"""Helpers for parsing dates and 12-hour times."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_TIME_12_RE = re.compile(
    r"^(\d{1,2})(?::(\d{2}))?\s*([AaPp][Mm])$"
)
_TIME_24_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def parse_date(value: str) -> date:
    value = value.strip()
    match = _DATE_RE.match(value)
    if not match:
        raise ValueError("Date must be YYYY-MM-DD (example: 2026-09-17)")
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError as exc:
        raise ValueError("Date must be a real calendar day in YYYY-MM-DD form") from exc


def format_time_12h(hour: int, minute: int) -> str:
    """Format 24h hour/minute as `9:00 PM`."""
    ampm = "AM" if hour < 12 else "PM"
    hour12 = hour % 12
    if hour12 == 0:
        hour12 = 12
    return f"{hour12}:{minute:02d} {ampm}"


def parse_time_12h(value: str) -> str:
    """Validate 12-hour time and return normalized `9:00 PM` (also accepts 24h input)."""
    value = value.strip()
    match = _TIME_12_RE.match(value)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or "0")
        ampm = match.group(3).upper()
        if hour < 1 or hour > 12 or minute > 59:
            raise ValueError("Use 12-hour time like `9:00 PM` or `11:30 AM`")
        hour24 = hour % 12
        if ampm == "PM":
            hour24 += 12
        return format_time_12h(hour24, minute)

    match24 = _TIME_24_RE.match(value)
    if match24:
        hour = int(match24.group(1))
        minute = int(match24.group(2))
        return format_time_12h(hour, minute)

    raise ValueError("Use 12-hour time like `9:00 PM` or `11:30 AM`")


def convert_24h_time_if_needed(value: Optional[str]) -> Optional[str]:
    """Return 12h form when `value` is 24h `HH:MM`; otherwise None (already fine / unknown)."""
    if not value:
        return None
    text = value.strip()
    if _TIME_12_RE.match(text):
        return None
    match24 = _TIME_24_RE.match(text)
    if match24:
        return format_time_12h(int(match24.group(1)), int(match24.group(2)))
    return None


def time_to_minutes(value: Optional[str]) -> Optional[int]:
    """Convert a stored time string to minutes since midnight for sorting."""
    if not value:
        return None
    text = value.strip()
    match = _TIME_12_RE.match(text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or "0")
        ampm = match.group(3).upper()
        hour24 = hour % 12
        if ampm == "PM":
            hour24 += 12
        return hour24 * 60 + minute
    match24 = _TIME_24_RE.match(text)
    if match24:
        return int(match24.group(1)) * 60 + int(match24.group(2))
    # Try datetime parse fallbacks
    for fmt in ("%I:%M %p", "%I %p", "%H:%M"):
        try:
            parsed = datetime.strptime(text.upper(), fmt)
            return parsed.hour * 60 + parsed.minute
        except ValueError:
            continue
    return None


def event_time_sort_key(event_time: Optional[str], event_id: int = 0) -> tuple:
    minutes = time_to_minutes(event_time)
    if minutes is None:
        return (1, 24 * 60, event_id)
    return (0, minutes, event_id)
