"""Module 08 — Followup Command.

Drafts (never sends) a per-owner follow-up email summarizing open/overdue
items, via a pluggable `DraftClient`. See
modules/08-followup-command/SPEC.md.

Email delivery itself is behind the `DraftClient` protocol so this module's
business logic (filtering, composing, ambiguous/unassigned exclusion,
--all handling) is testable without a real Gmail connection. Wiring a real
Gmail API client is a separate, environment-specific concern (OAuth
credentials) handled in the CLI layer, not here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from actiontrack.commands.list_cmd import effective_status
from actiontrack.storage import ActionItem, Storage

EMAIL_MAP_FILENAME = "emails.json"


class DraftClient(Protocol):
    def create_draft(self, to_email: str, subject: str, body: str) -> str:
        """Create a draft email (never sends it). Returns a reference
        (e.g. a draft id or link) for the caller to display."""
        ...


class FollowupError(Exception):
    """Raised for usage errors (e.g. neither an owner nor --all given)."""


class UnavailableDraftClient:
    """Default client used when no real email connector is configured.
    Always fails clearly rather than silently pretending to draft."""

    def create_draft(self, to_email: str, subject: str, body: str) -> str:
        raise RuntimeError(
            "Gmail connector not authorized — connect it and retry."
        )


@dataclass
class FollowupResult:
    owner: str
    outcome: str  # "drafted" | "skipped_no_items" | "skipped_no_email" | "failed"
    detail: str | None = None
    draft_ref: str | None = None


def _load_email_map(project_dir: Path) -> dict[str, str]:
    path = project_dir / ".actiontrack" / EMAIL_MAP_FILENAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _group_open_overdue_by_owner(
    project_dir: Path, today: date
) -> tuple[dict[str, list[ActionItem]], dict[str, str]]:
    with Storage(project_dir) as store:
        items = store.all_items()

    grouped: dict[str, list[ActionItem]] = {}
    status_by_owner: dict[str, str] = {}

    for item in items:
        if item.owner is None:
            continue
        if effective_status(item, today) not in ("open", "overdue"):
            continue
        grouped.setdefault(item.owner, []).append(item)
        status_by_owner[item.owner] = item.owner_status

    return grouped, status_by_owner


def compose_email(owner: str, items: list[ActionItem], today: date) -> tuple[str, str]:
    """Build (subject, body) for a follow-up email, overdue items first and
    clearly separated from items that are simply still open."""
    overdue = [i for i in items if effective_status(i, today) == "overdue"]
    open_items = [i for i in items if effective_status(i, today) == "open"]

    subject = f"Action items follow-up for {owner}"
    lines = [f"Hi {owner},", "", "Here's a summary of your open action items:"]

    if overdue:
        lines += ["", "OVERDUE:"]
        for item in overdue:
            due = item.due_date.isoformat() if item.due_date else "(no due date)"
            lines.append(f"- {item.task} (was due {due})")

    if open_items:
        lines += ["", "Still open:"]
        for item in open_items:
            due = item.due_date.isoformat() if item.due_date else "(no due date)"
            lines.append(f"- {item.task} (due {due})")

    lines += ["", "Thanks!"]
    return subject, "\n".join(lines)


def run_followup(
    project_dir: Path,
    owner: str | None,
    all_owners: bool,
    draft_client: DraftClient | None = None,
    today: date | None = None,
) -> list[FollowupResult]:
    """Draft follow-up emails. Exactly one of `owner` / `all_owners=True`
    must be given. `--all` automatically excludes ambiguous and unassigned
    owners; an explicit ambiguous-marker `owner` argument is still allowed
    (the caller is explicitly taking responsibility for that choice)."""
    if not all_owners and not owner:
        raise FollowupError("must provide an owner, or request --all")

    today = today or date.today()
    draft_client = draft_client or UnavailableDraftClient()
    email_map = _load_email_map(project_dir)
    grouped, status_by_owner = _group_open_overdue_by_owner(project_dir, today)

    if all_owners:
        targets = sorted(o for o in grouped if status_by_owner.get(o) != "ambiguous")
    else:
        targets = [_resolve_case_insensitive(owner, grouped)]

    results: list[FollowupResult] = []
    for target in targets:
        items = grouped.get(target, [])
        if not items:
            results.append(
                FollowupResult(
                    target, "skipped_no_items",
                    detail=f"no open or overdue items for {target}",
                )
            )
            continue

        email = email_map.get(target)
        if not email:
            results.append(
                FollowupResult(
                    target, "skipped_no_email",
                    detail=f"no email address on file for {target}; "
                    f"add one to .actiontrack/{EMAIL_MAP_FILENAME}",
                )
            )
            continue

        subject, body = compose_email(target, items, today)
        try:
            draft_ref = draft_client.create_draft(email, subject, body)
        except Exception as exc:
            results.append(FollowupResult(target, "failed", detail=str(exc)))
            continue

        results.append(FollowupResult(target, "drafted", draft_ref=draft_ref))

    return results


def _resolve_case_insensitive(owner: str, grouped: dict[str, list[ActionItem]]) -> str:
    for key in grouped:
        if key.lower() == owner.lower():
            return key
    return owner
