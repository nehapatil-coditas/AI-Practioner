"""Module 02 — Date Resolution.

Resolves raw date strings/phrases (from Module 01) into absolute calendar
dates. Relative phrases ("Friday", "next week", "tomorrow", "end of month")
are always resolved against a given anchor date — the note's own meeting
date, never the date the tool happens to run on. See
modules/02-date-resolution/SPEC.md.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

_ISO_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_SLASH_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$")
_MONTH_DAY_YEAR_RE = re.compile(r"(?i)^([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})$")
_DAY_MONTH_YEAR_RE = re.compile(r"(?i)^(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\.?,?\s*(\d{4})$")
_IN_N_DAYS_RE = re.compile(r"(?i)^in\s+(\d+)\s+days?$")
_NEXT_WEEKDAY_RE = re.compile(r"(?i)^next\s+(\w+)$")
_LEADING_WEEKDAY_RE = re.compile(
    r"(?i)^(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"mon|tue|tues|wed|thu|thurs|fri|sat|sun)\.?,?\s+"
)
_MONTH_DAY_NO_YEAR_RE = re.compile(r"(?i)^([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?$")
_DAY_MONTH_NO_YEAR_RE = re.compile(r"(?i)^(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\.?$")


@dataclass
class DateResolution:
    """Result of attempting to resolve a date. `date` is None on failure,
    in which case `reason` explains why."""

    date: date | None
    reason: str | None = None

    @property
    def resolved(self) -> bool:
        return self.date is not None


def resolve_meeting_date(raw_meeting_date: str | None) -> DateResolution:
    """Resolve a note's raw meeting-date string to an absolute date.

    Meeting dates are never relative, so only explicit-date parsing applies.
    """
    if not raw_meeting_date or not raw_meeting_date.strip():
        return DateResolution(None, "no meeting date found in note")

    parsed = _parse_explicit_date(raw_meeting_date.strip())
    if parsed is None:
        return DateResolution(None, f"meeting date phrase not understood: '{raw_meeting_date}'")
    return DateResolution(parsed)


def resolve_due_date(raw_due_phrase: str | None, anchor_date: date | None) -> DateResolution:
    """Resolve a raw due-date phrase to an absolute date.

    Explicit dates ("Nov 5", "2026-11-05") resolve regardless of the anchor.
    Relative phrases ("Friday", "next week", "tomorrow", "end of month") are
    resolved relative to `anchor_date` (the note's own meeting date) and
    require it to be known.
    """
    if not raw_due_phrase or not raw_due_phrase.strip():
        return DateResolution(None, "no due date mentioned")

    phrase = raw_due_phrase.strip()

    explicit = _parse_explicit_date(phrase)
    if explicit is not None:
        return DateResolution(explicit)

    if anchor_date is None:
        return DateResolution(None, "meeting date unknown, cannot resolve relative phrase")

    relative = _parse_relative_phrase(phrase, anchor_date)
    if relative is not None:
        return DateResolution(relative)

    return DateResolution(None, f"phrase not understood: '{phrase}'")


def _parse_explicit_date(text: str) -> date | None:
    text = text.strip().rstrip(".!,")
    if not text:
        return None

    # Tolerate a leading weekday name, e.g. "Monday, 14 September 2026".
    text = _LEADING_WEEKDAY_RE.sub("", text).strip()

    match = _ISO_RE.match(text)
    if match:
        year, month, day = (int(x) for x in match.groups())
        return _safe_date(year, month, day)

    match = _MONTH_DAY_YEAR_RE.match(text)
    if match:
        month_name, day_str, year_str = match.groups()
        month = _MONTHS.get(month_name.lower())
        if month:
            return _safe_date(int(year_str), month, int(day_str))

    match = _DAY_MONTH_YEAR_RE.match(text)
    if match:
        day_str, month_name, year_str = match.groups()
        month = _MONTHS.get(month_name.lower())
        if month:
            return _safe_date(int(year_str), month, int(day_str))

    match = _SLASH_RE.match(text)
    if match:
        first, second, year_str = (int(x) for x in match.groups())
        year = _normalize_year(year_str)
        # Deterministic convention: MM/DD/YYYY. If the first number can't be
        # a valid month (>12), it must be DD/MM/YYYY instead. We never guess
        # beyond this single, documented rule.
        if first <= 12:
            resolved = _safe_date(year, first, second)
            if resolved is not None:
                return resolved
        if second <= 12:
            return _safe_date(year, second, first)
        return None

    return None


def _normalize_year(year: int) -> int:
    return 2000 + year if year < 100 else year


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _anchored_year_date(anchor: date, month: int, day: int) -> date | None:
    """A month+day with no year is assumed to fall in the anchor's year,
    rolling into the next year if that date would already be in the past
    relative to the anchor — mirroring the bare-weekday 'next occurrence'
    convention used elsewhere in this module."""
    candidate = _safe_date(anchor.year, month, day)
    if candidate is None:
        return None
    if candidate < anchor:
        candidate = _safe_date(anchor.year + 1, month, day)
    return candidate


def _parse_relative_phrase(phrase: str, anchor: date) -> date | None:
    phrase = _LEADING_WEEKDAY_RE.sub("", phrase.strip())
    lower = phrase.lower().strip().rstrip(".!,")

    match = _MONTH_DAY_NO_YEAR_RE.match(lower)
    if match:
        month = _MONTHS.get(match.group(1))
        if month:
            return _anchored_year_date(anchor, month, int(match.group(2)))

    match = _DAY_MONTH_NO_YEAR_RE.match(lower)
    if match:
        month = _MONTHS.get(match.group(2))
        if month:
            return _anchored_year_date(anchor, month, int(match.group(1)))

    if lower in ("today", "eod", "eod today"):
        return anchor
    if lower in ("tomorrow", "eod tomorrow"):
        return anchor + timedelta(days=1)

    match = _IN_N_DAYS_RE.match(lower)
    if match:
        return anchor + timedelta(days=int(match.group(1)))

    if lower in ("end of month", "eom", "end of the month"):
        last_day = calendar.monthrange(anchor.year, anchor.month)[1]
        return date(anchor.year, anchor.month, last_day)

    if lower in ("end of week", "eow", "end of the week"):
        return _next_weekday_on_or_after(anchor, 4)  # Friday = end of business week

    if lower == "next week":
        return anchor + timedelta(days=7)

    match = _NEXT_WEEKDAY_RE.match(lower)
    if match:
        weekday_name = match.group(1)
        if weekday_name in _WEEKDAYS:
            # "next Friday" always skips the current week, even when the
            # nearest Friday hasn't happened yet this week.
            target = _WEEKDAYS[weekday_name]
            days_ahead = (target - anchor.weekday()) % 7
            days_ahead = 7 if days_ahead == 0 else days_ahead + 7
            return anchor + timedelta(days=days_ahead)

    if lower in _WEEKDAYS:
        # Bare weekday name = next occurrence on or after the anchor date,
        # including the anchor day itself (e.g. meeting is Friday, item says
        # "by Friday" -> due that same day).
        return _next_weekday_on_or_after(anchor, _WEEKDAYS[lower])

    return None


def _next_weekday_on_or_after(anchor: date, target_weekday: int) -> date:
    days_ahead = (target_weekday - anchor.weekday()) % 7
    return anchor + timedelta(days=days_ahead)
