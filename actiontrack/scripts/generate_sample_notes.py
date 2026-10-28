"""Generate the sample notes/ fixture used to exercise actiontrack.

Produces 30+ .md meeting notes: mostly well-formed, a handful deliberately
malformed, a few built specifically to exercise duplicate items, missing
owner/due-date, and the two-attendees-same-first-name ambiguity.
Re-run any time to regenerate the fixture from scratch.
"""
import os
import random
from datetime import date, timedelta

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "notes")

ATTENDEE_POOL = [
    "Priya Sharma", "Priya Verma", "Rahul Mehta", "Ananya Gupta",
    "Karan Singh", "Meera Iyer", "Vikram Rao", "Sara Khan", "Diego Alvarez",
]

TASK_TEMPLATES = [
    ("{owner} to send the revised quote", "by Friday"),
    ("{owner} to update the project roadmap", "by next Tuesday"),
    ("{owner} to review the vendor contract", "by Monday"),
    ("{owner} to schedule the client call", "by tomorrow"),
    ("{owner} to follow up with legal", "by EOD Friday"),
    ("{owner} to prepare the Q3 budget summary", "by next Wednesday"),
    ("{owner} to fix the staging deployment issue", None),
    ("{owner} to circulate the meeting recording", "by today"),
    ("{owner} to onboard the new vendor", "by March 5"),
    ("{owner} to close out the open support tickets", "by Thursday"),
]

random.seed(42)


def fmt_date(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def note_body(meeting_date: date, attendees: list[str], items: list[str]) -> str:
    lines = [
        f"# Weekly Sync",
        f"Date: {fmt_date(meeting_date)}",
        f"Attendees: {', '.join(attendees)}",
        "",
        "## Notes",
        "Discussed project status, blockers, and upcoming milestones. "
        "Team agreed to keep iterating on the current plan and revisit priorities "
        "next week. Several follow-ups were identified during the call.",
        "",
        "## Action Items",
    ]
    lines.extend(items)
    lines.append("")
    return "\n".join(lines)


def make_items(n: int, start_date: date) -> tuple[list[str], list[str]]:
    attendees = random.sample(ATTENDEE_POOL, k=random.choice([3, 4, 5]))
    lines = []
    for _ in range(n):
        template, due = random.choice(TASK_TEMPLATES)
        owner = random.choice(attendees).split()[0] if random.random() > 0.15 else None
        done = random.random() < 0.25
        box = "x" if done else " "
        if owner:
            text = template.format(owner=owner)
        else:
            text = template.split(" to ", 1)[1].capitalize() if " to " in template else template
        if due:
            text = f"{text} {due}"
        lines.append(f"- [{box}] {text}")
    return attendees, lines


def write(name: str, content: str, binary: bytes | None = None) -> None:
    path = os.path.join(OUT_DIR, name)
    if binary is not None:
        with open(path, "wb") as f:
            f.write(binary)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    base_date = date(2026, 1, 5)
    count = 0

    # 20 well-formed, varied notes.
    for i in range(20):
        meeting_date = base_date + timedelta(days=i * 3)
        attendees, items = make_items(random.choice([2, 3, 4]), meeting_date)
        write(f"note_{i+1:02d}.md", note_body(meeting_date, attendees, items))
        count += 1

    # One long, messy note: inconsistent bullets/whitespace, many items.
    messy_date = base_date + timedelta(days=61)
    messy_attendees = ["Rahul Mehta", "Ananya Gupta", "Vikram Rao", "Sara Khan"]
    messy_items = [
        "-   [ ]   Rahul   to   update   the  roadmap   by Friday",
        "* [x] Ananya to archive last quarter's reports",
        "  - [ ] Vikram to escalate the outage ticket by tomorrow",
        "- [X] Sara to send the client recap",
        "- [ ] Rahul to re-run the migration script by next Tuesday",
        "",
        "Random paragraph of unrelated notes mixed into the list to stress the parser "
        "with noisy, inconsistent meeting minutes that ramble for a while before "
        "getting back to action items, which happens often in real meetings.",
        "",
        "- [ ] Vikram to draft the postmortem by Monday",
    ]
    write("note_long_messy.md", note_body(messy_date, messy_attendees, messy_items))
    count += 1

    # Ambiguous owner: two attendees share first name "Priya".
    amb_date = base_date + timedelta(days=64)
    write("note_ambiguous_owner.md", note_body(
        amb_date,
        ["Priya Sharma", "Priya Verma", "Karan Singh"],
        ["- [ ] Priya to review the contract by Tuesday",
         "- [ ] Karan to send the follow-up notes by Friday"],
    ))
    count += 1

    # Item with no owner at all.
    no_owner_date = base_date + timedelta(days=67)
    write("note_no_owner.md", note_body(
        no_owner_date,
        ["Meera Iyer", "Diego Alvarez"],
        ["- [ ] Send the invoice to the client by Friday",
         "- [ ] Meera to prepare the demo by Monday"],
    ))
    count += 1

    # Item with no due date.
    no_due_date = base_date + timedelta(days=70)
    write("note_no_due_date.md", note_body(
        no_due_date,
        ["Rahul Mehta", "Sara Khan"],
        ["- [ ] Rahul to update the internal wiki",
         "- [ ] Sara to review the hiring pipeline by Thursday"],
    ))
    count += 1

    # Duplicate item repeated verbatim across three separate meetings.
    dup_task = "- [ ] Priya to send the revised quote by Friday"
    for j, offset in enumerate([73, 76, 80]):
        d = base_date + timedelta(days=offset)
        write(f"note_duplicate_{j+1}.md", note_body(
            d, ["Priya Sharma", "Karan Singh"],
            [dup_task, "- [ ] Karan to confirm the meeting room by tomorrow"],
        ))
        count += 1

    # Malformed: no date at all.
    write("note_malformed_no_date.md",
          "# Quick Chat\n\nAttendees: Rahul Mehta, Sara Khan\n\n"
          "## Action Items\n- [ ] Rahul to send notes by Friday\n")
    count += 1

    # Malformed: empty file.
    write("note_malformed_empty.md", "")
    count += 1

    # Malformed: binary/garbled content that isn't valid UTF-8.
    write("note_malformed_binary.md", content="", binary=b"\xff\xfe\x00\x01Garbled\xdebinary\xffcontent\x00\x01")
    count += 1

    print(f"Wrote {count} sample note files to {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    main()
