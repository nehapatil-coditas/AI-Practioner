from pathlib import Path

import pytest

from actiontrack.commands.ingest import IngestError, run_ingest
from actiontrack.storage import Storage


def write(folder: Path, name: str, content: str) -> None:
    (folder / name).write_text(content, encoding="utf-8")


def test_ingest_basic_folder(tmp_path: Path) -> None:
    notes = tmp_path / "notes"
    notes.mkdir()
    write(
        notes,
        "2026-03-02-standup.md",
        """\
Date: 2026-03-02
Attendees: Priya Sharma, Raj Kumar

- [ ] Priya to send the revised quote by Friday
- [x] Raj reviewed the contract
""",
    )

    summary = run_ingest(notes, tmp_path)
    assert summary.files_processed == 1
    assert summary.items_new == 2
    assert not summary.files_skipped

    with Storage(tmp_path) as store:
        items = store.all_items()
    assert len(items) == 2
    priya_item = next(i for i in items if i.owner == "Priya Sharma")
    assert priya_item.status == "open"
    raj_item = next(i for i in items if i.owner == "Raj Kumar")
    assert raj_item.status == "done"


def test_ingest_ignores_non_md_files(tmp_path: Path) -> None:
    notes = tmp_path / "notes"
    notes.mkdir()
    write(notes, "2026-03-02-standup.md", "- [ ] Priya to send the quote\n")
    write(notes, "agenda.txt", "- [ ] This should not be ingested\n")

    summary = run_ingest(notes, tmp_path)
    assert summary.files_processed == 1

    with Storage(tmp_path) as store:
        assert len(store.all_items()) == 1


def test_ingest_skips_malformed_files_without_crashing(tmp_path: Path) -> None:
    notes = tmp_path / "notes"
    notes.mkdir()
    write(notes, "2026-03-02-standup.md", "- [ ] Priya to send the quote\n")
    (notes / "empty.md").write_text("", encoding="utf-8")
    (notes / "binary.md").write_bytes(b"\xff\xfe\x00\x01broken\x80")

    summary = run_ingest(notes, tmp_path)
    assert summary.files_processed == 1
    assert len(summary.files_skipped) == 2
    skipped_names = {s.filename for s in summary.files_skipped}
    assert skipped_names == {"empty.md", "binary.md"}

    with Storage(tmp_path) as store:
        assert len(store.all_items()) == 1


def test_ingest_folder_not_found_raises(tmp_path: Path) -> None:
    with pytest.raises(IngestError):
        run_ingest(tmp_path / "does-not-exist", tmp_path)


def test_ingest_empty_folder_reports_zero(tmp_path: Path) -> None:
    notes = tmp_path / "notes"
    notes.mkdir()
    summary = run_ingest(notes, tmp_path)
    assert summary.files_processed == 0
    assert summary.items_new == 0


def test_ingest_merges_duplicate_task_across_meetings(tmp_path: Path) -> None:
    notes = tmp_path / "notes"
    notes.mkdir()
    write(
        notes,
        "2026-03-02-weekly.md",
        """\
Date: 2026-03-02
Attendees: Anita Desai

- [ ] Anita to share updated wireframes by Thursday
""",
    )
    write(
        notes,
        "2026-03-09-weekly.md",
        """\
Date: 2026-03-09
Attendees: Anita Desai

- [ ] Anita to share updated wireframes by Thursday
""",
    )
    write(
        notes,
        "2026-03-16-weekly.md",
        """\
Date: 2026-03-16
Attendees: Anita Desai

- [x] Anita to share updated wireframes
""",
    )

    summary = run_ingest(notes, tmp_path)
    assert summary.items_new == 1
    assert summary.occurrences_merged == 2

    with Storage(tmp_path) as store:
        items = store.all_items()
    assert len(items) == 1
    item = items[0]
    assert item.status == "done"  # latest mention wins
    assert len(item.source_occurrences) == 3


def test_ingest_is_idempotent(tmp_path: Path) -> None:
    notes = tmp_path / "notes"
    notes.mkdir()
    write(
        notes,
        "2026-03-02-standup.md",
        "Date: 2026-03-02\nAttendees: Priya Sharma\n\n- [ ] Priya to send the quote by Friday\n",
    )

    run_ingest(notes, tmp_path)
    with Storage(tmp_path) as store:
        first_count = len(store.all_items())

    run_ingest(notes, tmp_path)
    with Storage(tmp_path) as store:
        second_count = len(store.all_items())
        items = store.all_items()

    assert first_count == second_count == 1
    # Re-ingesting the same file shouldn't duplicate the source occurrence.
    assert len(items[0].source_occurrences) == 1


def test_ingest_does_not_merge_different_owners_with_similar_task(tmp_path: Path) -> None:
    notes = tmp_path / "notes"
    notes.mkdir()
    write(
        notes,
        "2026-03-02-standup.md",
        "Attendees: Priya Sharma, Raj Kumar\n\n"
        "- [ ] Priya to review the design doc\n"
        "- [ ] Raj to review the design doc\n",
    )

    summary = run_ingest(notes, tmp_path)
    assert summary.items_new == 2
    assert summary.occurrences_merged == 0


def test_ambiguous_owner_detected_mid_run_applies_to_earlier_file_too(tmp_path: Path) -> None:
    # File A (processed first, alphabetically/chronologically) only mentions
    # one "Priya" via attendee list resolution from directory fallback (no
    # local attendee list at all). File B's attendee list later reveals a
    # second, distinct Priya. Because we pre-register all attendees across
    # the whole folder before resolving any owner, file A's bare "Priya"
    # should already come out ambiguous.
    notes = tmp_path / "notes"
    notes.mkdir()
    write(
        notes,
        "2026-03-01-a.md",
        "Date: 2026-03-01\n\n- [ ] Priya to send the quote\n",
    )
    write(
        notes,
        "2026-03-02-b.md",
        "Date: 2026-03-02\nAttendees: Priya Sharma, Priya Patel\n\n- [ ] Priya to review the quote\n",
    )

    summary = run_ingest(notes, tmp_path)
    assert len(summary.ambiguous_owners) == 2

    with Storage(tmp_path) as store:
        items = store.all_items()
    assert all(item.owner_status == "ambiguous" for item in items)


def test_unassigned_owner_tracked_in_summary(tmp_path: Path) -> None:
    notes = tmp_path / "notes"
    notes.mkdir()
    write(notes, "2026-03-02-standup.md", "- [ ] Send the follow-up email by Monday\n")

    summary = run_ingest(notes, tmp_path)
    assert len(summary.unassigned_owners) == 1

    with Storage(tmp_path) as store:
        items = store.all_items()
    assert items[0].owner is None
    assert items[0].owner_status == "unassigned"


def test_unresolved_due_date_tracked_in_summary(tmp_path: Path) -> None:
    notes = tmp_path / "notes"
    notes.mkdir()
    write(notes, "2026-03-02-standup.md", "- [ ] Priya to send the quote ASAP\n")

    summary = run_ingest(notes, tmp_path)
    assert len(summary.unresolved_due_dates) == 1

    with Storage(tmp_path) as store:
        items = store.all_items()
    assert items[0].due_date is None


def test_ingest_adding_new_file_later_only_adds_new_items(tmp_path: Path) -> None:
    notes = tmp_path / "notes"
    notes.mkdir()
    write(notes, "2026-03-02-standup.md", "- [ ] Priya to send the quote\n")
    run_ingest(notes, tmp_path)

    write(notes, "2026-03-09-standup.md", "- [ ] Raj to review the contract\n")
    summary = run_ingest(notes, tmp_path)

    assert summary.files_processed == 2
    assert summary.items_new == 1  # only the new file's item

    with Storage(tmp_path) as store:
        assert len(store.all_items()) == 2
