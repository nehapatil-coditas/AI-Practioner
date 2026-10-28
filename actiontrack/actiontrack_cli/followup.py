"""Build and create (draft-only) follow-up emails per owner.

Gmail integration note
-----------------------
This CLI has no direct access to the Gmail MCP connector (that connector is
only reachable from inside an MCP-enabled agent session, not from an
arbitrary standalone script). `GmailDraftClient.create_draft` is therefore
the integration seam: swap its body for a call into the Gmail MCP
connector's draft-creation tool (or the Gmail API `users.drafts.create`
endpoint) when running inside an environment that has it wired up. The
default implementation below writes the draft to a local `drafts/` folder
as a plain `.eml` file so the command is fully testable without network
access, and it NEVER sends anything either way.
"""
import os
import yaml
from email.message import EmailMessage
from datetime import date


class ContactBook:
    def __init__(self, path: str):
        self.path = path
        self._contacts: dict[str, str] = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            self._contacts = {str(k).strip().lower(): str(v).strip() for k, v in raw.items()}

    def lookup(self, full_name: str) -> str | None:
        return self._contacts.get(full_name.strip().lower())


class GmailDraftClient:
    """Draft-only client. Default backend: local .eml file. Never sends."""

    def __init__(self, drafts_dir: str = "drafts"):
        self.drafts_dir = drafts_dir

    def create_draft(self, to_addr: str, subject: str, body: str) -> str:
        os.makedirs(self.drafts_dir, exist_ok=True)
        msg = EmailMessage()
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.set_content(body)

        safe_name = to_addr.replace("@", "_at_").replace(".", "_")
        out_path = os.path.join(self.drafts_dir, f"{safe_name}.eml")
        with open(out_path, "wb") as f:
            f.write(bytes(msg))
        return out_path


def build_followup_body(owner: str, overdue: list[dict], open_items: list[dict]) -> tuple[str, str]:
    subject = f"Action items follow-up: {owner}"
    lines = [f"Hi {owner.split()[0]},", "", "Here's a quick roundup of your open action items:", ""]

    if overdue:
        lines.append("OVERDUE:")
        for it in overdue:
            due = it["due_date"] or "no due date"
            lines.append(f"  - {it['task']} (due {due})")
        lines.append("")

    if open_items:
        lines.append("OPEN:")
        for it in open_items:
            due = it["due_date"] or "no due date"
            lines.append(f"  - {it['task']} (due {due})")
        lines.append("")

    lines.append("Could you share a status update when you get a chance?")
    lines.append("")
    lines.append("Thanks!")
    return subject, "\n".join(lines)


def is_overdue(item: dict, today: date) -> bool:
    if item["status"] != "open" or not item["due_date"]:
        return False
    return date.fromisoformat(item["due_date"]) < today
