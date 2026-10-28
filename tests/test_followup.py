import json
from datetime import date
from pathlib import Path

import pytest

from actiontrack.commands.followup import FollowupError, run_followup
from actiontrack.storage import ActionItem, Storage


class FakeDraftClient:
    def __init__(self):
        self.created: list[tuple[str, str, str]] = []

    def create_draft(self, to_email: str, subject: str, body: str) -> str:
        self.created.append((to_email, subject, body))
        return f"draft-for-{to_email}"


class FailingDraftClient:
    def create_draft(self, to_email: str, subject: str, body: str) -> str:
        raise RuntimeError("Gmail connector not authorized — connect it and retry.")


def set_emails(tmp_path: Path, mapping: dict[str, str]) -> None:
    store_dir = tmp_path / ".actiontrack"
    store_dir.mkdir(parents=True, exist_ok=True)
    (store_dir / "emails.json").write_text(json.dumps(mapping), encoding="utf-8")


def seed(tmp_path: Path, **overrides) -> int:
    defaults = dict(
        owner="Priya Sharma",
        owner_status="confirmed",
        task="send the quote",
        due_date=date(2026, 3, 1),
        status="open",
    )
    defaults.update(overrides)
    with Storage(tmp_path) as store:
        return store.insert_item(ActionItem(**defaults))


def test_followup_drafts_email_for_owner_with_items(tmp_path: Path) -> None:
    seed(tmp_path, owner="Priya Sharma", due_date=date(2026, 3, 1))  # overdue
    set_emails(tmp_path, {"Priya Sharma": "priya@example.com"})
    client = FakeDraftClient()

    results = run_followup(tmp_path, owner="Priya Sharma", all_owners=False, draft_client=client, today=date(2026, 3, 10))

    assert len(results) == 1
    assert results[0].outcome == "drafted"
    assert len(client.created) == 1
    to_email, subject, body = client.created[0]
    assert to_email == "priya@example.com"
    assert "OVERDUE" in body
    assert "send the quote" in body


def test_followup_separates_overdue_and_open(tmp_path: Path) -> None:
    seed(tmp_path, owner="Priya Sharma", task="overdue task", due_date=date(2026, 3, 1))
    seed(tmp_path, owner="Priya Sharma", task="future task", due_date=date(2026, 3, 20))
    set_emails(tmp_path, {"Priya Sharma": "priya@example.com"})
    client = FakeDraftClient()

    run_followup(tmp_path, owner="Priya Sharma", all_owners=False, draft_client=client, today=date(2026, 3, 10))

    body = client.created[0][2]
    overdue_idx = body.index("OVERDUE")
    open_idx = body.index("Still open")
    overdue_task_idx = body.index("overdue task")
    future_task_idx = body.index("future task")
    assert overdue_idx < overdue_task_idx < open_idx < future_task_idx


def test_followup_excludes_done_items(tmp_path: Path) -> None:
    seed(tmp_path, owner="Priya Sharma", task="done task", status="done", due_date=date(2026, 3, 1))
    set_emails(tmp_path, {"Priya Sharma": "priya@example.com"})
    client = FakeDraftClient()

    results = run_followup(tmp_path, owner="Priya Sharma", all_owners=False, draft_client=client, today=date(2026, 3, 10))
    assert results[0].outcome == "skipped_no_items"
    assert client.created == []


def test_followup_no_items_creates_no_draft(tmp_path: Path) -> None:
    client = FakeDraftClient()
    results = run_followup(tmp_path, owner="Nobody", all_owners=False, draft_client=client, today=date(2026, 3, 10))
    assert results[0].outcome == "skipped_no_items"
    assert client.created == []


def test_followup_missing_email_is_reported(tmp_path: Path) -> None:
    seed(tmp_path, owner="Priya Sharma", due_date=date(2026, 3, 1))
    client = FakeDraftClient()

    results = run_followup(tmp_path, owner="Priya Sharma", all_owners=False, draft_client=client, today=date(2026, 3, 10))
    assert results[0].outcome == "skipped_no_email"
    assert client.created == []


def test_followup_all_excludes_ambiguous_and_unassigned(tmp_path: Path) -> None:
    seed(tmp_path, owner="Priya Sharma", owner_status="confirmed", due_date=date(2026, 3, 1))
    seed(tmp_path, owner="Priya (ambiguous)", owner_status="ambiguous", due_date=date(2026, 3, 1))
    seed(tmp_path, owner=None, owner_status="unassigned", due_date=date(2026, 3, 1))
    set_emails(tmp_path, {"Priya Sharma": "priya@example.com", "Priya (ambiguous)": "noone@example.com"})
    client = FakeDraftClient()

    results = run_followup(tmp_path, owner=None, all_owners=True, draft_client=client, today=date(2026, 3, 10))

    drafted_owners = {r.owner for r in results if r.outcome == "drafted"}
    assert drafted_owners == {"Priya Sharma"}
    assert all(to != "noone@example.com" for to, _, _ in client.created)


def test_followup_explicit_ambiguous_owner_still_allowed(tmp_path: Path) -> None:
    seed(tmp_path, owner="Priya (ambiguous)", owner_status="ambiguous", due_date=date(2026, 3, 1))
    set_emails(tmp_path, {"Priya (ambiguous)": "someone@example.com"})
    client = FakeDraftClient()

    results = run_followup(
        tmp_path, owner="Priya (ambiguous)", all_owners=False, draft_client=client, today=date(2026, 3, 10)
    )
    assert results[0].outcome == "drafted"


def test_followup_requires_owner_or_all(tmp_path: Path) -> None:
    with pytest.raises(FollowupError):
        run_followup(tmp_path, owner=None, all_owners=False, draft_client=FakeDraftClient())


def test_followup_all_with_no_eligible_owners_reports_nothing(tmp_path: Path) -> None:
    client = FakeDraftClient()
    results = run_followup(tmp_path, owner=None, all_owners=True, draft_client=client, today=date(2026, 3, 10))
    assert results == []


def test_followup_continues_after_one_owner_fails(tmp_path: Path) -> None:
    seed(tmp_path, owner="Priya Sharma", due_date=date(2026, 3, 1))
    seed(tmp_path, owner="Raj Kumar", due_date=date(2026, 3, 1))
    set_emails(tmp_path, {"Priya Sharma": "priya@example.com", "Raj Kumar": "raj@example.com"})

    class PartialFailClient:
        def create_draft(self, to_email, subject, body):
            if "raj" in to_email:
                raise RuntimeError("API hiccup")
            return "draft-ok"

    results = run_followup(tmp_path, owner=None, all_owners=True, draft_client=PartialFailClient(), today=date(2026, 3, 10))
    outcomes = {r.owner: r.outcome for r in results}
    assert outcomes["Priya Sharma"] == "drafted"
    assert outcomes["Raj Kumar"] == "failed"


def test_followup_unavailable_gmail_connector_reports_clearly(tmp_path: Path) -> None:
    seed(tmp_path, owner="Priya Sharma", due_date=date(2026, 3, 1))
    set_emails(tmp_path, {"Priya Sharma": "priya@example.com"})

    results = run_followup(
        tmp_path, owner="Priya Sharma", all_owners=False, draft_client=FailingDraftClient(), today=date(2026, 3, 10)
    )
    assert results[0].outcome == "failed"
    assert "not authorized" in results[0].detail


def test_followup_case_insensitive_owner_match(tmp_path: Path) -> None:
    seed(tmp_path, owner="Priya Sharma", due_date=date(2026, 3, 1))
    set_emails(tmp_path, {"Priya Sharma": "priya@example.com"})
    client = FakeDraftClient()

    results = run_followup(tmp_path, owner="priya sharma", all_owners=False, draft_client=client, today=date(2026, 3, 10))
    assert results[0].outcome == "drafted"
