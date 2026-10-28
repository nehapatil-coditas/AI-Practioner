"""Module 07 — Done Command.

Marks a stored action item as done by ID. See modules/07-done-command/SPEC.md.
"""

from __future__ import annotations

from pathlib import Path

from actiontrack.storage import ActionItem, ItemNotFoundError, Storage

__all__ = ["ItemNotFoundError", "mark_done"]


def mark_done(project_dir: Path, item_id: int) -> ActionItem:
    """Mark the item with `item_id` as done. Raises ItemNotFoundError if it
    doesn't exist. Marking an already-done item done again is harmless."""
    with Storage(project_dir) as store:
        return store.mark_done(item_id)
