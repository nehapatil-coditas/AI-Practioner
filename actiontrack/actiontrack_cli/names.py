"""Owner name extraction and disambiguation against a note's attendee list."""
import re

AMBIGUOUS = "ambiguous"
UNASSIGNED = "unassigned"


def parse_attendees(text: str) -> list[str]:
    """Extract attendee full names from a note's 'Attendees' section/line."""
    names: list[str] = []

    m = re.search(r"attendees\s*:\s*(.+)", text, re.IGNORECASE)
    if m:
        for part in re.split(r",|;", m.group(1)):
            name = part.strip().strip(".")
            if name:
                names.append(name)
        return names

    # Fallback: "## Attendees" heading followed by a bullet list.
    m = re.search(r"#+\s*attendees\s*\n((?:\s*[-*]\s*.+\n?)+)", text, re.IGNORECASE)
    if m:
        for line in m.group(1).splitlines():
            line = line.strip().lstrip("-*").strip()
            if line:
                names.append(line)
    return names


def resolve_owner(mention: str, attendees: list[str]) -> tuple[str | None, bool]:
    """Resolve a (possibly first-name-only) mention against attendees.

    Returns (resolved_full_name_or_None, is_ambiguous).
    """
    mention = mention.strip()
    if not mention:
        return None, False

    mention_lower = mention.lower()

    # Exact full-name match first.
    for full in attendees:
        if full.lower() == mention_lower:
            return full, False

    # First-name-only match against attendee first tokens.
    first_token = mention_lower.split()[0]
    matches = [
        full for full in attendees
        if full.lower().split()[0] == first_token
    ]

    if len(matches) == 1:
        return matches[0], False
    if len(matches) > 1:
        return None, True  # ambiguous: multiple attendees share this first name

    # No attendee match at all; fall back to the raw mention as given.
    return mention, False
