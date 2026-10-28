from datetime import date
from pathlib import Path

import pytest

from actiontrack.commands.list_cmd import ListError, list_items
from actiontrack.storage import ActionItem, Storage


def seed(tmp_path: Path, **overrides) -> int:
    defaults = dict(
        owner="Priya Sharma",
        owner_status="confirmed",
        task="send the quote",
        due_date=date(2026, 3, 6),
        status="open",
    )
    defaults.update(overrides)
    with Storage(tmp_path) as store:
        return store.insert_item(ActionItem(**defaults))


def test_list_no_filters_returns_all(tmp_path: Path) -> None:
    seed(tmp_path, owner="Priya Sharma")
    seed(tmp_path, owner="Raj Kumar")
    items = list_items(tmp_path, today=date(2026, 1, 1))
    assert len(items) == 2


def test_list_filter_by_owner(tmp_path: Path) -> None:
    seed(tmp_path, owner="Priya Sharma")
    seed(tmp_path, owner="Raj Kumar")
    items = list_items(tmp_path, owner="Priya Sharma", today=date(2026, 1, 1))
    assert len(items) == 1
    assert items[0].owner == "Priya Sharma"


def test_overdue_is_computed_dynamically() -> None:
    pass  # covered below with tmp_path fixture


def test_open_item_past_due_shows_as_overdue(tmp_path: Path) -> None:
    seed(tmp_path, status="open", due_date=date(2026, 3, 1))
    items = list_items(tmp_path, today=date(2026, 3, 10))
    assert items[0].status == "overdue"


def test_done_item_past_due_never_shows_as_overdue(tmp_path: Path) -> None:
    seed(tmp_path, status="done", due_date=date(2026, 3, 1))
    items = list_items(tmp_path, today=date(2026, 3, 10))
    assert items[0].status == "done"


def test_open_item_future_due_shows_as_open(tmp_path: Path) -> None:
    seed(tmp_path, status="open", due_date=date(2026, 3, 20))
    items = list_items(tmp_path, today=date(2026, 3, 10))
    assert items[0].status == "open"


def test_status_filter_overdue(tmp_path: Path) -> None:
    seed(tmp_path, status="open", due_date=date(2026, 3, 1))  # overdue
    seed(tmp_path, status="open", due_date=date(2026, 3, 20))  # open
    seed(tmp_path, status="done", due_date=date(2026, 3, 1))  # done

    items = list_items(tmp_path, status="overdue", today=date(2026, 3, 10))
    assert len(items) == 1
    assert items[0].status == "overdue"


def test_status_filter_open_excludes_overdue(tmp_path: Path) -> None:
    seed(tmp_path, status="open", due_date=date(2026, 3, 1))  # overdue
    seed(tmp_path, status="open", due_date=date(2026, 3, 20))  # open

    items = list_items(tmp_path, status="open", today=date(2026, 3, 10))
    assert len(items) == 1
    assert items[0].status == "open"


def test_due_before_filter_excludes_items_with_no_due_date(tmp_path: Path) -> None:
    seed(tmp_path, due_date=date(2026, 3, 1))
    seed(tmp_path, due_date=None)

    items = list_items(tmp_path, due_before=date(2026, 3, 10), today=date(2026, 1, 1))
    assert len(items) == 1


def test_unassigned_and_no_due_date_render_correctly(tmp_path: Path) -> None:
    seed(tmp_path, owner=None, owner_status="unassigned", due_date=None)
    items = list_items(tmp_path, today=date(2026, 1, 1))
    assert items[0].owner == "(unassigned)"
    assert items[0].due_date == "(no due date)"


def test_no_matching_items_returns_empty_list(tmp_path: Path) -> None:
    seed(tmp_path, owner="Priya Sharma")
    items = list_items(tmp_path, owner="Nobody Here", today=date(2026, 1, 1))
    assert items == []


def test_empty_store_returns_empty_list(tmp_path: Path) -> None:
    items = list_items(tmp_path, today=date(2026, 1, 1))
    assert items == []


def test_invalid_status_raises(tmp_path: Path) -> None:
    with pytest.raises(ListError):
        list_items(tmp_path, status="not-a-status", today=date(2026, 1, 1))


def test_combined_filters(tmp_path: Path) -> None:
    seed(tmp_path, owner="Priya Sharma", status="open", due_date=date(2026, 3, 1))  # overdue
    seed(tmp_path, owner="Priya Sharma", status="done", due_date=date(2026, 3, 1))
    seed(tmp_path, owner="Raj Kumar", status="open", due_date=date(2026, 3, 1))  # overdue

    items = list_items(tmp_path, owner="Priya Sharma", status="overdue", today=date(2026, 3, 10))
    assert len(items) == 1
