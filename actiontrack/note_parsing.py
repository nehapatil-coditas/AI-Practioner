"""Module 01 — Note Parsing.

Reads a single Markdown meeting note and extracts the raw facts in it:
meeting date (raw string), attendees (raw names), and action-item lines
(raw owner / raw task / raw due-date phrase / done marker).

This module does not interpret dates or resolve owner identities — it only
extracts what is literally present in the text. See modules/01-note-parsing/SPEC.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Matches "- [ ] text", "- [x] text", "- [X] text" (also tolerates "*"/"+" bullets).
_CHECKBOX_RE = re.compile(r"^\s*[-*+]\s*\[( |x|X)\]\s*(.*)$")

_FENCE_RE = re.compile(r"^\s*```")
_HTML_COMMENT_START_RE = re.compile(r"<!--")
_HTML_COMMENT_END_RE = re.compile(r"-->")

# Looks for a meeting date near the top of the file, e.g. "Date: 2026-03-05",
# "# Meeting Notes - March 5, 2026", or a bare date on its own line.
_DATE_FIELD_RE = re.compile(r"(?im)^[ \t]*(?:date|meeting date)[ \t]*:[ \t]*(.+)$")

# A date-like token anywhere in a line (used as fallback meeting-date search
# and for filename-based fallback).
_DATE_TOKEN_RE = re.compile(
    r"""(?ix)
    (\d{4}-\d{2}-\d{2})                                   # 2026-03-05
    | (\d{1,2}/\d{1,2}/\d{2,4})                            # 3/5/2026 or 3/5/26
    | ((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)
       [a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4})      # March 5, 2026 / Mar 5 2026
    | (\d{1,2}(?:st|nd|rd|th)?\s+
       (?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s*\d{4})  # 5th March 2026
    """
)

# Attendee list line, e.g. "Attendees: Priya, Raj, Kavya" or "Attendees:" with
# a following bulleted list.
_ATTENDEES_FIELD_RE = re.compile(r"(?im)^[ \t]*attendees[ \t]*:[ \t]*(.*)$")

# "@name:" mention-style owner, e.g. "@anita: audit colour contrast..."
_OWNER_MENTION_RE = re.compile(r"^@(?P<owner>[A-Za-z][A-Za-z.'-]*)\s*[:\-]\s*(?P<rest>.+)$")

# Leading owner name before a separator like "to", ":", "-", "will", etc.
# e.g. "Priya to send..." / "Raj: review..." / "Kavya - update the doc"
_OWNER_WITH_SEPARATOR_RE = re.compile(
    r"""(?ix)
    ^\s*
    (?P<owner>[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*)?)   # 1-2 capitalized words
    \s*
    (?:to\b|will\b|:|-|–|—)
    \s*
    (?P<rest>.+)$
    """
)

# Words that look like an owner slot but aren't a real person's name — these
# always resolve to "no owner" rather than being tracked as a fake identity.
_NON_OWNER_WORDS = {
    "someone", "anyone", "somebody", "everyone", "everybody", "nobody",
    "team", "tbd", "whoever", "we", "owner",
}

# Bare "Name verb..." with no separator, e.g. "Raj reviewed the contract".
# Only applied when the leading word isn't a common imperative task-starter
# (those indicate no owner was named at all, e.g. "Send the invoice...").
_OWNER_BARE_RE = re.compile(
    r"""(?x)
    ^\s*
    (?P<owner>[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*)?)   # 1-2 capitalized words
    \s+
    (?P<rest>[a-z].+)$                                      # rest starts lowercase (a verb)
    """
)

_IMPERATIVE_STARTERS = {
    "send", "update", "review", "follow", "schedule", "prepare", "draft",
    "share", "create", "finalize", "complete", "set", "fix", "investigate",
    "discuss", "confirm", "check", "arrange", "organize", "write", "book",
    "plan", "test", "deploy", "merge", "close", "open", "add", "remove",
    "research", "call", "email", "contact", "setup", "coordinate", "reach",
}

# Raw due-date phrase: text following the LAST "by"/"due"/"before"/"on" in
# the task text. Using the last (not first) occurrence matters because these
# are common words that often appear earlier in a sentence for unrelated
# reasons (e.g. "audit colour contrast on the dashboard by Mon" — "on" here
# isn't introducing a date, "by Mon" is).
_DUE_KEYWORD_RE = re.compile(r"(?i)\b(?:by|due|before|on)\s+")


@dataclass
class RawActionItem:
    """One checkbox line as literally found in a note, unresolved."""

    raw_owner: str | None
    raw_task: str
    raw_due_phrase: str | None
    done: bool
    line_number: int
    line_text: str


@dataclass
class ParsedNote:
    """Successful parse result for one note file."""

    source_path: Path
    raw_meeting_date: str | None
    attendees: list[str] = field(default_factory=list)
    action_items: list[RawActionItem] = field(default_factory=list)
    skipped_lines: list[tuple[int, str, str]] = field(default_factory=list)
    # skipped_lines: (line_number, line_text, reason) for broken checkbox
    # lines that were skipped individually without failing the whole file.


@dataclass
class MalformedNote:
    """Failure result when a file cannot be parsed at all."""

    source_path: Path
    reason: str


ParseResult = ParsedNote | MalformedNote


def parse_note(path: Path) -> ParseResult:
    """Parse a single Markdown meeting note file.

    Returns a ParsedNote on success (best-effort — missing date/attendees/
    items are not failures) or a MalformedNote when the file cannot be
    processed safely at all.
    """
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        return MalformedNote(path, f"could not read file: {exc}")

    if len(raw_bytes) == 0:
        return MalformedNote(path, "file is empty")

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return MalformedNote(path, f"could not decode file as UTF-8: {exc}")

    if not text.strip():
        return MalformedNote(path, "file contains no readable content")

    lines = text.splitlines()

    raw_meeting_date = _extract_meeting_date(text, lines, path)
    attendees = _extract_attendees(text, lines)
    action_items, skipped_lines = _extract_action_items(lines)

    return ParsedNote(
        source_path=path,
        raw_meeting_date=raw_meeting_date,
        attendees=attendees,
        action_items=action_items,
        skipped_lines=skipped_lines,
    )


def _extract_meeting_date(text: str, lines: list[str], path: Path) -> str | None:
    # 1. Explicit "Date:" / "Meeting Date:" field anywhere in the file.
    match = _DATE_FIELD_RE.search(text)
    if match:
        return match.group(1).strip()

    # 2. A date-like token in one of the first few lines (e.g. in a heading).
    for line in lines[:5]:
        token_match = _DATE_TOKEN_RE.search(line)
        if token_match:
            return token_match.group(0).strip()

    # 3. Fallback: a date-like token in the filename.
    filename_match = _DATE_TOKEN_RE.search(path.stem.replace("_", " ").replace("-", "-"))
    if filename_match:
        return filename_match.group(0).strip()
    iso_in_name = re.search(r"\d{4}-\d{2}-\d{2}", path.stem)
    if iso_in_name:
        return iso_in_name.group(0)

    return None


def _extract_attendees(text: str, lines: list[str]) -> list[str]:
    match = _ATTENDEES_FIELD_RE.search(text)
    if not match:
        return []

    inline = match.group(1).strip()
    if inline:
        return _split_names(inline)

    # "Attendees:" with names as a following bulleted list.
    start_idx = text[: match.end()].count("\n")
    names: list[str] = []
    for line in lines[start_idx + 1 :]:
        stripped = line.strip()
        if not stripped:
            if names:
                break
            continue
        bullet_match = re.match(r"^[-*]\s*(.+)$", stripped)
        if bullet_match:
            names.append(bullet_match.group(1).strip())
            continue
        break
    return names


def _split_names(inline: str) -> list[str]:
    inline = inline.strip()
    if inline.startswith("[") and inline.endswith("]"):
        inline = inline[1:-1]
    parts = re.split(r",|;|\band\b", inline)
    return [p.strip() for p in parts if p.strip()]


def _excluded_line_mask(lines: list[str]) -> list[bool]:
    """Flags lines that must never be scanned for action items: fenced code
    blocks, HTML comments, and blockquoted lines. Notes sometimes embed
    example/template checkboxes or quoted third-party text inside these —
    they aren't real action items agreed in the meeting."""
    excluded = [False] * len(lines)
    in_fence = False
    in_comment = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        if _FENCE_RE.match(line):
            excluded[i] = True
            in_fence = not in_fence
            continue
        if in_fence:
            excluded[i] = True
            continue

        if in_comment:
            excluded[i] = True
            if _HTML_COMMENT_END_RE.search(line):
                in_comment = False
            continue
        if _HTML_COMMENT_START_RE.search(line):
            excluded[i] = True
            if not _HTML_COMMENT_END_RE.search(line):
                in_comment = True
            continue

        if stripped.startswith(">"):
            excluded[i] = True
            continue

    return excluded


def _extract_action_items(
    lines: list[str],
) -> tuple[list[RawActionItem], list[tuple[int, str, str]]]:
    items: list[RawActionItem] = []
    skipped: list[tuple[int, str, str]] = []
    excluded = _excluded_line_mask(lines)

    for i, line in enumerate(lines, start=1):
        if excluded[i - 1]:
            continue

        checkbox_match = _CHECKBOX_RE.match(line)
        if not checkbox_match:
            continue

        marker, content = checkbox_match.groups()
        content = content.strip()

        if not content:
            skipped.append((i, line, "checkbox has no task text"))
            continue

        done = marker.lower() == "x"
        raw_owner, raw_task = _split_owner_and_task(content)
        raw_due_phrase = _extract_due_phrase(raw_task)

        items.append(
            RawActionItem(
                raw_owner=raw_owner,
                raw_task=raw_task,
                raw_due_phrase=raw_due_phrase,
                done=done,
                line_number=i,
                line_text=line,
            )
        )

    return items, skipped


def _split_owner_and_task(content: str) -> tuple[str | None, str]:
    mention_match = _OWNER_MENTION_RE.match(content)
    if mention_match:
        owner = mention_match.group("owner").strip().capitalize()
        return owner, mention_match.group("rest").strip()

    match = _OWNER_WITH_SEPARATOR_RE.match(content)
    if match:
        owner = match.group("owner").strip()
        rest = match.group("rest").strip()
        if owner.lower() in _NON_OWNER_WORDS:
            return None, rest
        return owner, rest

    bare_match = _OWNER_BARE_RE.match(content)
    if bare_match:
        owner = bare_match.group("owner").strip()
        if owner.split()[0].lower() not in _IMPERATIVE_STARTERS:
            return owner, bare_match.group("rest").strip()

    return None, content


def _extract_due_phrase(task_text: str) -> str | None:
    matches = list(_DUE_KEYWORD_RE.finditer(task_text))
    if not matches:
        return None
    phrase = task_text[matches[-1].end() :].strip().rstrip(".!")
    return phrase or None
