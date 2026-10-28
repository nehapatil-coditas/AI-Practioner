"""Resolve meeting dates and relative due-date phrases to absolute calendar dates."""
import re
from datetime import date, timedelta

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_MEETING_DATE_PATTERNS = [
    r"\d{4}-\d{2}-\d{2}",              # 2026-03-05
    r"\d{1,2}/\d{1,2}/\d{4}",          # 03/05/2026
    r"[A-Za-z]+ \d{1,2},? \d{4}",      # March 5, 2026 / March 5 2026
]

_MEETING_DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%B %d, %Y",
    "%B %d %Y",
    "%b %d, %Y",
    "%b %d %Y",
]


def extract_meeting_date(text: str) -> date | None:
    """Find and parse the meeting date from a note's raw text.

    Looks at explicit 'Date:' lines first, then falls back to scanning the
    first ~10 lines for anything date-shaped.
    """
    lines = text.splitlines()[:15]
    head = "\n".join(lines)

    m = re.search(r"date\s*:\s*(.+)", head, re.IGNORECASE)
    candidates = [m.group(1).strip()] if m else []
    candidates += [head]

    for candidate in candidates:
        for pattern in _MEETING_DATE_PATTERNS:
            found = re.search(pattern, candidate)
            if not found:
                continue
            raw = found.group(0)
            for fmt in _MEETING_DATE_FORMATS:
                try:
                    from datetime import datetime
                    return datetime.strptime(raw, fmt).date()
                except ValueError:
                    continue
    return None


_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def resolve_due_date(phrase: str, meeting_date: date) -> date | None:
    """Resolve a free-text due-date phrase relative to the meeting's own date.

    Returns None if the phrase can't be confidently resolved (best-effort
    only, per requirements.md section 9).
    """
    if not phrase:
        return None
    p = phrase.strip().lower().strip(".,!? ")
    p = re.sub(r"^(by|due|on)\s+", "", p)
    p = re.sub(r"^(eod|end of day)\s*", "", p).strip()
    if not p:
        return None

    if p in ("today",):
        return meeting_date
    if p in ("tomorrow",):
        return meeting_date + timedelta(days=1)
    if p in ("eod", "end of day"):
        return meeting_date

    is_next = p.startswith("next ")
    weekday_part = p[5:].strip() if is_next else p
    if weekday_part in WEEKDAYS:
        target = WEEKDAYS.index(weekday_part)
        current = meeting_date.weekday()
        days_ahead = (target - current) % 7
        if days_ahead == 0:
            days_ahead = 0 if not is_next else 7
        if is_next:
            days_ahead += 7 if days_ahead < 7 else 0
        return meeting_date + timedelta(days=days_ahead)

    # explicit absolute date e.g. "2026-03-05", "03/05/2026"
    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", p)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
    slash = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", p)
    if slash:
        try:
            return date(int(slash.group(3)), int(slash.group(1)), int(slash.group(2)))
        except ValueError:
            return None

    # "March 5" / "march 5th" (no year) -> assume meeting year, roll fwd if past
    md = re.match(r"^([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?$", p)
    if md and md.group(1) in _MONTHS:
        month = _MONTHS[md.group(1)]
        day = int(md.group(2))
        try:
            candidate = date(meeting_date.year, month, day)
        except ValueError:
            return None
        if candidate < meeting_date:
            try:
                candidate = date(meeting_date.year + 1, month, day)
            except ValueError:
                return None
        return candidate

    return None
