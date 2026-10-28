"""Parse a single meeting-note markdown file into structured action items."""
import re
from dataclasses import dataclass, field

from . import dateparse, names

CHECKBOX_RE = re.compile(r"^\s*[-*]\s*\[( |x|X)\]\s*(.+?)\s*$")
OWNER_VERB_RE = re.compile(
    r"^(?P<owner>[A-Z][A-Za-z'\-]+(?:\s[A-Z][A-Za-z'\-]+)?)\s+"
    r"(?:to|will|should|needs to|has to|must)\s+(?P<rest>.+)$"
)
DUE_PHRASE_RE = re.compile(r"\s+(?:by|due)\s+(?P<due>[^,.;]+)\s*[.,;]?\s*$", re.IGNORECASE)


@dataclass
class RawItem:
    owner_mention: str | None
    task: str
    due_phrase: str | None
    done: bool
    raw_line: str


@dataclass
class NoteResult:
    path: str
    meeting_date: object = None
    attendees: list[str] = field(default_factory=list)
    items: list[RawItem] = field(default_factory=list)
    error: str | None = None


def parse_note_text(path: str, text: str) -> NoteResult:
    if not text.strip():
        return NoteResult(path=path, error="empty file")

    meeting_date = dateparse.extract_meeting_date(text)
    if meeting_date is None:
        return NoteResult(path=path, error="no parseable meeting date found")

    attendees = names.parse_attendees(text)

    items: list[RawItem] = []
    for line in text.splitlines():
        m = CHECKBOX_RE.match(line)
        if not m:
            continue
        checked = m.group(1).lower() == "x"
        body = m.group(2).strip()
        if not body:
            continue

        due_phrase = None
        due_match = DUE_PHRASE_RE.search(body)
        if due_match:
            due_phrase = due_match.group("due").strip()
            body = body[: due_match.start()].rstrip()

        owner_match = OWNER_VERB_RE.match(body)
        if owner_match:
            owner_mention = owner_match.group("owner").strip()
            task = owner_match.group("rest").strip()
        else:
            owner_mention = None
            task = body.strip()

        if not task:
            continue

        items.append(RawItem(
            owner_mention=owner_mention,
            task=task,
            due_phrase=due_phrase,
            done=checked,
            raw_line=line.strip(),
        ))

    return NoteResult(path=path, meeting_date=meeting_date, attendees=attendees, items=items)


def parse_note_file(path: str) -> NoteResult:
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except UnicodeDecodeError:
        return NoteResult(path=path, error="could not decode file as UTF-8 (binary/garbled content)")
    except OSError as exc:
        return NoteResult(path=path, error=f"could not read file: {exc}")
    return parse_note_text(path, text)
