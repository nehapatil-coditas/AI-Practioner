"""Module 05 — Ingest Command.

Orchestrates Modules 01-04 for every .md file in a folder: parse, resolve
dates, resolve owners, deduplicate/merge against what's already known, and
persist. See modules/05-ingest-command/SPEC.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import fuzz

from actiontrack.date_resolution import resolve_due_date, resolve_meeting_date
from actiontrack.note_parsing import MalformedNote, ParsedNote, parse_note
from actiontrack.owner_resolution import OwnerDirectory
from actiontrack.storage import ActionItem, SourceOccurrence, Storage

# A task is considered the same recurring item as an existing one when its
# text is at least this similar (0-100, rapidfuzz token_sort_ratio) to an
# existing item's task text under the same resolved owner.
DEDUP_SIMILARITY_THRESHOLD = 82

# Stripped off task text before dedup comparison only — a due-date clause
# mentioned in one occurrence but not another (e.g. dropped once an item is
# marked done) shouldn't make an otherwise-identical task look dissimilar.
_DUE_SUFFIX_RE = re.compile(r"(?i)\s*[,—-]?\s*\b(?:by|due|before|on)\s+.+$")


def _core_task_text(task: str) -> str:
    return _DUE_SUFFIX_RE.sub("", task).strip().lower()


class IngestError(Exception):
    """Raised for conditions that stop the whole ingest run (bad folder)."""


@dataclass
class SkippedFile:
    filename: str
    reason: str


@dataclass
class FlaggedItem:
    description: str
    source_file: str


@dataclass
class IngestSummary:
    files_processed: int = 0
    files_skipped: list[SkippedFile] = field(default_factory=list)
    items_new: int = 0
    occurrences_merged: int = 0
    ambiguous_owners: list[FlaggedItem] = field(default_factory=list)
    unassigned_owners: list[FlaggedItem] = field(default_factory=list)
    unresolved_due_dates: list[FlaggedItem] = field(default_factory=list)


def run_ingest(folder: Path, project_dir: Path) -> IngestSummary:
    """Ingest every .md file in `folder`, persisting results under
    `project_dir`/.actiontrack/. Idempotent: re-running on an unchanged
    folder does not create duplicate stored items."""
    if not folder.exists() or not folder.is_dir():
        raise IngestError(f"folder not found: {folder}")

    summary = IngestSummary()
    md_files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".md")

    parsed_notes: list[ParsedNote] = []
    for path in md_files:
        result = parse_note(path)
        if isinstance(result, MalformedNote):
            summary.files_skipped.append(SkippedFile(path.name, result.reason))
            continue
        parsed_notes.append(result)
        summary.files_processed += 1

    with Storage(project_dir) as storage:
        directory = storage.load_owner_directory()

        # Pre-register every full attendee name across the WHOLE folder
        # before resolving any individual owner. This makes ambiguity
        # detection independent of file processing order: a name that only
        # becomes ambiguous because of a file processed later still applies
        # to items from earlier files in this same run.
        for note in parsed_notes:
            directory.register_many(
                [a for a in note.attendees if len(a.split()) >= 2]
            )

        working_items = storage.all_items()

        for note in parsed_notes:
            meeting_date = resolve_meeting_date(note.raw_meeting_date).date

            for raw_item in note.action_items:
                owner_resolution = directory.resolve(raw_item.raw_owner, note.attendees)
                due_resolution = resolve_due_date(raw_item.raw_due_phrase, meeting_date)
                status = "done" if raw_item.done else "open"
                source_name = note.source_path.name

                if due_resolution.date is None:
                    summary.unresolved_due_dates.append(
                        FlaggedItem(f"{raw_item.raw_task!r}: {due_resolution.reason}", source_name)
                    )
                if owner_resolution.status == "ambiguous":
                    summary.ambiguous_owners.append(
                        FlaggedItem(owner_resolution.identity, source_name)
                    )
                elif owner_resolution.status == "unassigned":
                    summary.unassigned_owners.append(
                        FlaggedItem(raw_item.raw_task, source_name)
                    )

                occurrence = SourceOccurrence(source_name, meeting_date)
                duplicate = _find_duplicate(working_items, owner_resolution.identity, raw_item.raw_task)

                if duplicate is not None:
                    already_seen = any(
                        occ.source_file == source_name for occ in duplicate.source_occurrences
                    )
                    if not already_seen:
                        duplicate.source_occurrences.append(occurrence)
                        summary.occurrences_merged += 1
                    duplicate.status = status
                    if due_resolution.date is not None:
                        duplicate.due_date = due_resolution.date
                        duplicate.due_date_reason = None
                    storage.update_item(duplicate)
                else:
                    item = ActionItem(
                        owner=owner_resolution.identity,
                        owner_status=owner_resolution.status,
                        task=raw_item.raw_task,
                        due_date=due_resolution.date,
                        due_date_reason=due_resolution.reason,
                        meeting_date=meeting_date,
                        status=status,
                        source_occurrences=[occurrence],
                    )
                    item.id = storage.insert_item(item)
                    working_items.append(item)
                    summary.items_new += 1

        storage.save_owner_directory(directory)

    return summary


def _find_duplicate(
    existing_items: list[ActionItem], owner: str | None, task: str
) -> ActionItem | None:
    norm_owner = (owner or "").strip().lower()
    best: ActionItem | None = None
    best_score = 0.0

    task_core = _core_task_text(task)
    for existing in existing_items:
        if (existing.owner or "").strip().lower() != norm_owner:
            continue
        score = fuzz.token_sort_ratio(task_core, _core_task_text(existing.task))
        if score >= DEDUP_SIMILARITY_THRESHOLD and score > best_score:
            best = existing
            best_score = score

    return best
