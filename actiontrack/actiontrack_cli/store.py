"""Local JSON-backed persistence for tracked action items."""
import json
import os
import re
from datetime import date


def _normalize_task(text: str) -> str:
    t = text.lower().strip()
    t = re.sub(r"[.,;:!?'\"]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def dedup_key(owner_key: str, task: str) -> str:
    return f"{owner_key.lower()}::{_normalize_task(task)}"


class Store:
    def __init__(self, path: str):
        self.path = path
        self._data = self._load()

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {"next_id": 1, "items": {}}
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, default=str)

    def find_by_key(self, key: str) -> dict | None:
        for item in self._data["items"].values():
            if item["dedup_key"] == key:
                return item
        return None

    def add_item(self, owner: str, owner_status: str, task: str, due_date,
                 done: bool, source_file: str, meeting_date, key: str) -> dict:
        item_id = str(self._data["next_id"])
        self._data["next_id"] += 1
        item = {
            "id": item_id,
            "owner": owner,
            "owner_status": owner_status,  # "resolved" | "ambiguous" | "unassigned"
            "task": task,
            "due_date": due_date.isoformat() if isinstance(due_date, date) else due_date,
            "status": "done" if done else "open",
            "sources": [{"file": source_file, "meeting_date": meeting_date.isoformat()}],
            "dedup_key": key,
        }
        self._data["items"][item_id] = item
        return item

    def merge_into(self, item: dict, done: bool, source_file: str, meeting_date) -> None:
        if not any(s["file"] == source_file for s in item["sources"]):
            item["sources"].append({"file": source_file, "meeting_date": meeting_date.isoformat()})
        if done and item["status"] != "done":
            item["status"] = "done"

    def mark_done(self, item_id: str) -> bool:
        item = self._data["items"].get(item_id)
        if not item:
            return False
        item["status"] = "done"
        return True

    def all_items(self) -> list[dict]:
        return list(self._data["items"].values())

    def get(self, item_id: str) -> dict | None:
        return self._data["items"].get(item_id)
