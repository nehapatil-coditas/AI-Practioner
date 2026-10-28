from datetime import date
from pathlib import Path

import pytest

from actiontrack.owner_resolution import OwnerDirectory
from actiontrack.storage import (
    ActionItem,
    ItemNotFoundError,
    SourceOccurrence,
    Storage,
    StorageError,
)


def make_item(**overrides) -> ActionItem:
    defaults = dict(
        owner="Priya Sharma",
        owner_status="confirmed",
        task="send the revised quote",
        due_date=date(2026, 3, 6),
        due_date_reason=None,
        meeting_date=date(2026, 3, 2),
        status="open",
        source_occurrences=[SourceOccurrence("2026-03-02-standup.md", date(2026, 3, 2))],
    )
    defaults.update(overrides)
    return ActionItem(**defaults)


def test_insert_and_get_item(tmp_path: Path) -> None:
    store = Storage(tmp_path)
    item_id = store.insert_item(make_item())

    fetched = store.get_item(item_id)
    assert fetched is not None
    assert fetched.id == item_id
    assert fetched.owner == "Priya Sharma"
    assert fetched.task == "send the revised quote"
    assert fetched.due_date == date(2026, 3, 6)
    assert fetched.meeting_date == date(2026, 3, 2)
    assert fetched.status == "open"
    assert len(fetched.source_occurrences) == 1
    assert fetched.source_occurrences[0].source_file == "2026-03-02-standup.md"
    store.close()


def test_store_persists_across_connections(tmp_path: Path) -> None:
    store1 = Storage(tmp_path)
    item_id = store1.insert_item(make_item())
    store1.close()

    store2 = Storage(tmp_path)
    fetched = store2.get_item(item_id)
    assert fetched is not None
    assert fetched.owner == "Priya Sharma"
    store2.close()


def test_mark_done(tmp_path: Path) -> None:
    store = Storage(tmp_path)
    item_id = store.insert_item(make_item(status="open"))

    updated = store.mark_done(item_id)
    assert updated.status == "done"

    fetched = store.get_item(item_id)
    assert fetched.status == "done"


def test_mark_done_nonexistent_id_raises(tmp_path: Path) -> None:
    store = Storage(tmp_path)
    with pytest.raises(ItemNotFoundError):
        store.mark_done(9999)


def test_mark_done_twice_is_harmless(tmp_path: Path) -> None:
    store = Storage(tmp_path)
    item_id = store.insert_item(make_item(status="open"))
    store.mark_done(item_id)
    updated_again = store.mark_done(item_id)
    assert updated_again.status == "done"


def test_update_item(tmp_path: Path) -> None:
    store = Storage(tmp_path)
    item_id = store.insert_item(make_item())

    item = store.get_item(item_id)
    item.due_date = date(2026, 3, 10)
    item.source_occurrences.append(
        SourceOccurrence("2026-03-09-followup.md", date(2026, 3, 9))
    )
    store.update_item(item)

    fetched = store.get_item(item_id)
    assert fetched.due_date == date(2026, 3, 10)
    assert len(fetched.source_occurrences) == 2


def test_update_nonexistent_item_raises(tmp_path: Path) -> None:
    store = Storage(tmp_path)
    ghost = make_item()
    ghost.id = 9999
    with pytest.raises(ItemNotFoundError):
        store.update_item(ghost)


def test_list_items_no_filters_returns_all(tmp_path: Path) -> None:
    store = Storage(tmp_path)
    store.insert_item(make_item(owner="Priya Sharma"))
    store.insert_item(make_item(owner="Raj Kumar"))

    items = store.list_items()
    assert len(items) == 2


def test_list_items_filter_by_owner_case_insensitive(tmp_path: Path) -> None:
    store = Storage(tmp_path)
    store.insert_item(make_item(owner="Priya Sharma"))
    store.insert_item(make_item(owner="Raj Kumar"))

    items = store.list_items(owner="priya sharma")
    assert len(items) == 1
    assert items[0].owner == "Priya Sharma"


def test_list_items_filter_by_status(tmp_path: Path) -> None:
    store = Storage(tmp_path)
    store.insert_item(make_item(status="open"))
    store.insert_item(make_item(status="done"))

    open_items = store.list_items(status="open")
    assert len(open_items) == 1
    assert open_items[0].status == "open"


def test_list_items_filter_by_due_before(tmp_path: Path) -> None:
    store = Storage(tmp_path)
    store.insert_item(make_item(due_date=date(2026, 3, 1)))
    store.insert_item(make_item(due_date=date(2026, 3, 20)))
    store.insert_item(make_item(due_date=None))

    items = store.list_items(due_before=date(2026, 3, 10))
    assert len(items) == 1
    assert items[0].due_date == date(2026, 3, 1)


def test_list_items_combined_filters(tmp_path: Path) -> None:
    store = Storage(tmp_path)
    store.insert_item(make_item(owner="Priya Sharma", status="open", due_date=date(2026, 3, 1)))
    store.insert_item(make_item(owner="Priya Sharma", status="done", due_date=date(2026, 3, 1)))
    store.insert_item(make_item(owner="Raj Kumar", status="open", due_date=date(2026, 3, 1)))

    items = store.list_items(owner="Priya Sharma", status="open")
    assert len(items) == 1


def test_items_with_null_owner_and_due_date_are_storable(tmp_path: Path) -> None:
    store = Storage(tmp_path)
    item_id = store.insert_item(
        make_item(owner=None, owner_status="unassigned", due_date=None, due_date_reason="no due date mentioned")
    )
    fetched = store.get_item(item_id)
    assert fetched.owner is None
    assert fetched.due_date is None
    assert fetched.due_date_reason == "no due date mentioned"

    # Unfiltered and status-filtered listing still includes them.
    assert len(store.list_items()) == 1
    assert len(store.list_items(status="open")) == 1
    # due_before filtering excludes items with no due date (neither match nor error).
    assert store.list_items(due_before=date(2026, 12, 31)) == []


def test_get_nonexistent_item_returns_none(tmp_path: Path) -> None:
    store = Storage(tmp_path)
    assert store.get_item(12345) is None


def test_owner_directory_round_trip(tmp_path: Path) -> None:
    store = Storage(tmp_path)
    directory = OwnerDirectory()
    directory.resolve("Priya", attendees=["Priya Sharma", "Raj Kumar"])
    store.save_owner_directory(directory)

    reloaded = store.load_owner_directory()
    result = reloaded.resolve("Priya", attendees=[])
    assert result.status == "confirmed"
    assert result.identity == "Priya Sharma"


def test_owner_directory_defaults_to_empty_when_unset(tmp_path: Path) -> None:
    store = Storage(tmp_path)
    directory = store.load_owner_directory()
    result = directory.resolve("Kavya", attendees=[])
    assert result.status == "confirmed"
    assert result.identity == "Kavya"


def test_owner_directory_save_overwrites_previous(tmp_path: Path) -> None:
    store = Storage(tmp_path)
    d1 = OwnerDirectory()
    d1.register("Priya Sharma")
    store.save_owner_directory(d1)

    d2 = OwnerDirectory()
    d2.register("Priya Sharma")
    d2.register("Priya Patel")
    store.save_owner_directory(d2)

    reloaded = store.load_owner_directory()
    result = reloaded.resolve("Priya", attendees=[])
    assert result.status == "ambiguous"


def test_store_creates_actiontrack_folder(tmp_path: Path) -> None:
    Storage(tmp_path)
    assert (tmp_path / ".actiontrack").is_dir()
    assert (tmp_path / ".actiontrack" / "store.db").is_file()


def test_corrupted_store_file_raises_clear_error(tmp_path: Path) -> None:
    store_dir = tmp_path / ".actiontrack"
    store_dir.mkdir()
    db_path = store_dir / "store.db"
    db_path.write_bytes(b"this is not a sqlite database at all, just garbage bytes")

    with pytest.raises(StorageError):
        Storage(tmp_path)


def test_idempotent_reinsert_does_not_happen_automatically(tmp_path: Path) -> None:
    # Storage itself doesn't dedupe (that's Module 05's job) — this just
    # confirms insert_item is a plain insert, so the guard against
    # duplicates must live in the ingest orchestrator, not here.
    store = Storage(tmp_path)
    store.insert_item(make_item())
    store.insert_item(make_item())
    assert len(store.list_items()) == 2
