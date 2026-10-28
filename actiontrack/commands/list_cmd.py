"""Module 06 — List Command.

Filters and displays stored action items, computing 'overdue' dynamically
against the real current date (never stored). See
modules/06-list-command/SPEC.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from actiontrack.storage import ActionItem, Storage


class ListError(Exception):
    """Raised for bad filter input (e.g. an unparsable --due-before date)."""


@dataclass
class DisplayItem:
    id: int
    owner: str
    task: str
    due_date: str
    status: str
    source_files: str


def effective_status(item: ActionItem, today: date) -> str:
    """The status to display: 'overdue' is computed on the fly, never
    stored, so it's always accurate regardless of when `ingest` last ran."""
    if item.status == "open" and item.due_date is not None and item.due_date < today:
        return "overdue"
    return item.status


def list_items(
    project_dir: Path,
    owner: str | None = None,
    status: str | None = None,
    due_before: date | None = None,
    today: date | None = None,
) -> list[DisplayItem]:
    """Read and filter stored items. `status` here may be 'open', 'done', or
    'overdue' (the dynamic, computed one) — unlike Storage.list_items, which
    only knows the stored 'open'/'done' states."""
    if status is not None and status not in ("open", "done", "overdue"):
        raise ListError(f"invalid status: {status!r} (expected open, done, or overdue)")

    today = today or date.today()

    with Storage(project_dir) as store:
        stored_status = status if status in ("open", "done") else None
        items = store.list_items(owner=owner, status=stored_status, due_before=due_before)

    if status == "overdue":
        items = [i for i in items if effective_status(i, today) == "overdue"]
    elif status == "open":
        # Storage's 'open' includes items that are actually overdue; the
        # plain 'open' filter should exclude those (overdue is its own
        # bucket), per spec.
        items = [i for i in items if effective_status(i, today) == "open"]

    return [_to_display(i, today) for i in items]


def _to_display(item: ActionItem, today: date) -> DisplayItem:
    return DisplayItem(
        id=item.id,
        owner=item.owner or "(unassigned)",
        task=item.task,
        due_date=item.due_date.isoformat() if item.due_date else "(no due date)",
        status=effective_status(item, today),
        source_files=", ".join(occ.source_file for occ in item.source_occurrences),
    )
