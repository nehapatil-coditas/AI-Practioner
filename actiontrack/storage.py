"""Module 04 — Storage.

Local SQLite persistence for action items and the accumulated owner
directory, living in a `.actiontrack/` folder. This is the single source of
truth read/written by every command. See modules/04-storage/SPEC.md.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from actiontrack.owner_resolution import OwnerDirectory

STORE_DIR_NAME = ".actiontrack"
STORE_FILE_NAME = "store.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT,
    owner_status TEXT NOT NULL DEFAULT 'unassigned',
    task TEXT NOT NULL,
    due_date TEXT,
    due_date_reason TEXT,
    meeting_date TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done')),
    source_occurrences TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS owner_directory (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    data TEXT NOT NULL
);
"""


class StorageError(Exception):
    """Raised when the store file can't be opened/read, or on bad input."""


class ItemNotFoundError(StorageError):
    """Raised when an operation references an item ID that doesn't exist."""


@dataclass
class SourceOccurrence:
    source_file: str
    meeting_date: date | None

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "meeting_date": self.meeting_date.isoformat() if self.meeting_date else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SourceOccurrence":
        raw_date = data.get("meeting_date")
        return cls(
            source_file=data["source_file"],
            meeting_date=date.fromisoformat(raw_date) if raw_date else None,
        )


@dataclass
class ActionItem:
    task: str
    owner: str | None = None
    owner_status: str = "unassigned"  # "confirmed" | "ambiguous" | "unassigned"
    due_date: date | None = None
    due_date_reason: str | None = None
    meeting_date: date | None = None
    status: str = "open"  # "open" | "done"
    source_occurrences: list[SourceOccurrence] = field(default_factory=list)
    id: int | None = None


class Storage:
    """SQLite-backed store living at `<project_dir>/.actiontrack/store.db`."""

    def __init__(self, project_dir: Path):
        store_dir = project_dir / STORE_DIR_NAME
        store_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = store_dir / STORE_FILE_NAME

        try:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        except sqlite3.DatabaseError as exc:
            raise StorageError(
                f"could not open or initialize store at {self.db_path}: {exc}"
            ) from exc

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ---- items: writes ----

    def insert_item(self, item: ActionItem) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO items
                (owner, owner_status, task, due_date, due_date_reason,
                 meeting_date, status, source_occurrences)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._item_to_row_values(item),
        )
        self._conn.commit()
        return cursor.lastrowid

    def update_item(self, item: ActionItem) -> None:
        if item.id is None:
            raise StorageError("cannot update an item with no id")
        cursor = self._conn.execute(
            """
            UPDATE items
            SET owner = ?, owner_status = ?, task = ?, due_date = ?,
                due_date_reason = ?, meeting_date = ?, status = ?,
                source_occurrences = ?
            WHERE id = ?
            """,
            (*self._item_to_row_values(item), item.id),
        )
        self._conn.commit()
        if cursor.rowcount == 0:
            raise ItemNotFoundError(f"no item with id {item.id}")

    def mark_done(self, item_id: int) -> ActionItem:
        item = self.get_item(item_id)
        if item is None:
            raise ItemNotFoundError(f"no item with id {item_id}")
        item.status = "done"
        self.update_item(item)
        return item

    # ---- items: reads ----

    def get_item(self, item_id: int) -> ActionItem | None:
        row = self._conn.execute(
            "SELECT * FROM items WHERE id = ?", (item_id,)
        ).fetchone()
        return self._row_to_item(row) if row else None

    def all_items(self) -> list[ActionItem]:
        rows = self._conn.execute("SELECT * FROM items ORDER BY id").fetchall()
        return [self._row_to_item(row) for row in rows]

    def list_items(
        self,
        owner: str | None = None,
        status: str | None = None,
        due_before: date | None = None,
    ) -> list[ActionItem]:
        """Read-only filtered query. `status` here is the stored status
        ('open'/'done') — dynamic 'overdue' computation is Module 06's job,
        done on top of these results."""
        clauses: list[str] = []
        params: list[object] = []

        if owner is not None:
            clauses.append("LOWER(owner) = LOWER(?)")
            params.append(owner)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if due_before is not None:
            clauses.append("due_date IS NOT NULL AND due_date < ?")
            params.append(due_before.isoformat())

        query = "SELECT * FROM items"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id"

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_item(row) for row in rows]

    def items_by_owner(self, owner: str) -> list[ActionItem]:
        return self.list_items(owner=owner)

    # ---- owner directory persistence ----

    def load_owner_directory(self) -> OwnerDirectory:
        row = self._conn.execute(
            "SELECT data FROM owner_directory WHERE id = 1"
        ).fetchone()
        if row is None:
            return OwnerDirectory()
        return OwnerDirectory.from_dict(json.loads(row["data"]))

    def save_owner_directory(self, directory: OwnerDirectory) -> None:
        data = json.dumps(directory.to_dict())
        self._conn.execute(
            """
            INSERT INTO owner_directory (id, data) VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET data = excluded.data
            """,
            (data,),
        )
        self._conn.commit()

    # ---- internal helpers ----

    @staticmethod
    def _item_to_row_values(item: ActionItem) -> tuple:
        return (
            item.owner,
            item.owner_status,
            item.task,
            item.due_date.isoformat() if item.due_date else None,
            item.due_date_reason,
            item.meeting_date.isoformat() if item.meeting_date else None,
            item.status,
            json.dumps([occ.to_dict() for occ in item.source_occurrences]),
        )

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> ActionItem:
        return ActionItem(
            id=row["id"],
            owner=row["owner"],
            owner_status=row["owner_status"],
            task=row["task"],
            due_date=date.fromisoformat(row["due_date"]) if row["due_date"] else None,
            due_date_reason=row["due_date_reason"],
            meeting_date=date.fromisoformat(row["meeting_date"]) if row["meeting_date"] else None,
            status=row["status"],
            source_occurrences=[
                SourceOccurrence.from_dict(d) for d in json.loads(row["source_occurrences"])
            ],
        )
