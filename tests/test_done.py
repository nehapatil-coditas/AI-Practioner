from pathlib import Path

import pytest

from actiontrack.commands.done import ItemNotFoundError, mark_done
from actiontrack.storage import ActionItem, Storage


def test_mark_done_updates_status(tmp_path: Path) -> None:
    with Storage(tmp_path) as store:
        item_id = store.insert_item(ActionItem(task="send the quote", status="open"))

    item = mark_done(tmp_path, item_id)
    assert item.status == "done"

    with Storage(tmp_path) as store:
        assert store.get_item(item_id).status == "done"


def test_mark_done_nonexistent_id_raises_clear_error(tmp_path: Path) -> None:
    with Storage(tmp_path):
        pass
    with pytest.raises(ItemNotFoundError):
        mark_done(tmp_path, 999)


def test_mark_done_already_done_is_harmless(tmp_path: Path) -> None:
    with Storage(tmp_path) as store:
        item_id = store.insert_item(ActionItem(task="x", status="done"))

    item = mark_done(tmp_path, item_id)
    assert item.status == "done"


def test_mark_done_item_with_ambiguous_owner_allowed(tmp_path: Path) -> None:
    with Storage(tmp_path) as store:
        item_id = store.insert_item(
            ActionItem(task="x", owner="Priya (ambiguous)", owner_status="ambiguous", status="open")
        )

    item = mark_done(tmp_path, item_id)
    assert item.status == "done"
