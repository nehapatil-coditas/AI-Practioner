"""actiontrack CLI entrypoint."""
import argparse
import glob
import os
import sys
from datetime import date, datetime

from . import names as names_mod
from . import parser as parser_mod
from . import store as store_mod
from . import followup as followup_mod

DEFAULT_STORE = os.path.join(".actiontrack", "store.json")
DEFAULT_CONTACTS = "contacts.yaml"


def cmd_ingest(args: argparse.Namespace) -> int:
    st = store_mod.Store(args.store)
    md_files = sorted(glob.glob(os.path.join(args.folder, "**", "*.md"), recursive=True))

    ingested_files = 0
    skipped: list[tuple[str, str]] = []
    new_items = 0
    merged_items = 0
    ambiguous_count = 0
    unassigned_count = 0

    for path in md_files:
        result = parser_mod.parse_note_file(path)
        if result.error:
            skipped.append((path, result.error))
            continue
        ingested_files += 1

        for raw in result.items:
            if raw.owner_mention is None:
                owner, owner_status = names_mod.UNASSIGNED, "unassigned"
            else:
                resolved, ambiguous = names_mod.resolve_owner(raw.owner_mention, result.attendees)
                if ambiguous:
                    owner, owner_status = names_mod.AMBIGUOUS, "ambiguous"
                else:
                    owner, owner_status = resolved, "resolved"

            if owner_status == "unassigned":
                unassigned_count += 1
            elif owner_status == "ambiguous":
                ambiguous_count += 1

            due_date = None
            if raw.due_phrase:
                due_date = parser_mod.dateparse.resolve_due_date(raw.due_phrase, result.meeting_date)

            key_owner_part = raw.owner_mention or names_mod.UNASSIGNED
            key = store_mod.dedup_key(key_owner_part, raw.task)

            existing = st.find_by_key(key)
            if existing:
                st.merge_into(existing, raw.done, path, result.meeting_date)
                merged_items += 1
            else:
                st.add_item(owner, owner_status, raw.task, due_date, raw.done,
                            path, result.meeting_date, key)
                new_items += 1

    st.save()

    print(f"Scanned {len(md_files)} file(s).")
    print(f"Ingested {ingested_files} file(s): {new_items} new item(s), {merged_items} merged into existing items.")
    if unassigned_count:
        print(f"  {unassigned_count} item(s) had no resolvable owner (owner=unassigned).")
    if ambiguous_count:
        print(f"  {ambiguous_count} item(s) had an ambiguous owner (multiple attendees share a first name).")
    if skipped:
        print(f"Skipped {len(skipped)} malformed file(s):")
        for path, reason in skipped:
            print(f"  - {path}: {reason}")
    return 0


def _resolve_owner_filter(name: str, items: list[dict]) -> str | None:
    name_lower = name.strip().lower()
    exact = {it["owner"] for it in items if it.get("owner") and it["owner"].lower() == name_lower}
    if exact:
        return next(iter(exact))

    first_token = name_lower.split()[0] if name_lower else ""
    candidates = sorted({
        it["owner"] for it in items
        if it.get("owner") and it["owner"] not in (names_mod.AMBIGUOUS, names_mod.UNASSIGNED)
        and it["owner"].lower().split()[0] == first_token
    })
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        print(f"'{name}' is ambiguous among stored owners: {', '.join(candidates)}. "
              f"Use a full name to disambiguate.", file=sys.stderr)
        return None
    return name  # no match found; caller will just get zero results


def _item_status_view(item: dict, today: date) -> str:
    if item["status"] == "done":
        return "done"
    if followup_mod.is_overdue(item, today):
        return "overdue"
    return "open"


def cmd_list(args: argparse.Namespace) -> int:
    st = store_mod.Store(args.store)
    items = st.all_items()
    today = date.today()

    if args.owner:
        resolved = _resolve_owner_filter(args.owner, items)
        if resolved is None:
            return 1
        items = [it for it in items if it.get("owner") == resolved]

    if args.status:
        items = [it for it in items if _item_status_view(it, today) == args.status]

    if args.due_before:
        try:
            cutoff = datetime.strptime(args.due_before, "%Y-%m-%d").date()
        except ValueError:
            print(f"--due-before must be YYYY-MM-DD, got: {args.due_before}", file=sys.stderr)
            return 1
        items = [it for it in items if it["due_date"] and date.fromisoformat(it["due_date"]) < cutoff]

    if not items:
        print("No items match.")
        return 0

    header = f"{'ID':<5} {'OWNER':<20} {'STATUS':<9} {'DUE':<12} TASK"
    print(header)
    print("-" * len(header))
    for it in sorted(items, key=lambda x: int(x["id"])):
        owner = it["owner"] or "-"
        due = it["due_date"] or "-"
        status = _item_status_view(it, today)
        print(f"{it['id']:<5} {owner:<20} {status:<9} {due:<12} {it['task']}")
    return 0


def cmd_done(args: argparse.Namespace) -> int:
    st = store_mod.Store(args.store)
    if not st.mark_done(args.id):
        print(f"No item with id '{args.id}'.", file=sys.stderr)
        return 1
    st.save()
    print(f"Item {args.id} marked done.")
    return 0


def cmd_followup(args: argparse.Namespace) -> int:
    st = store_mod.Store(args.store)
    items = st.all_items()
    today = date.today()

    owner = _resolve_owner_filter(args.owner, items)
    if owner is None:
        return 1

    owner_items = [it for it in items if it.get("owner") == owner]
    if not owner_items:
        print(f"No tracked items for '{args.owner}'.")
        return 0

    overdue = [it for it in owner_items if followup_mod.is_overdue(it, today)]
    open_items = [it for it in owner_items if it["status"] == "open" and it not in overdue]

    if not overdue and not open_items:
        print(f"{owner} has no open or overdue items. No draft created.")
        return 0

    contacts = followup_mod.ContactBook(args.contacts)
    email_addr = contacts.lookup(owner)
    if not email_addr:
        print(f"No email on file for '{owner}' in {args.contacts}. "
              f"Add an entry and re-run. No draft created.", file=sys.stderr)
        return 1

    subject, body = followup_mod.build_followup_body(owner, overdue, open_items)
    client = followup_mod.GmailDraftClient(drafts_dir=args.drafts_dir)
    out_path = client.create_draft(email_addr, subject, body)
    print(f"Draft created for {owner} <{email_addr}> ({len(overdue)} overdue, {len(open_items)} open).")
    print(f"Saved (not sent): {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="actiontrack", description="Track action items from meeting notes.")
    p.add_argument("--store", default=DEFAULT_STORE, help="Path to the local JSON store.")
    sub = p.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Parse all .md notes in a folder and update the store.")
    p_ingest.add_argument("folder")
    p_ingest.set_defaults(func=cmd_ingest)

    p_list = sub.add_parser("list", help="List tracked items.")
    p_list.add_argument("--owner")
    p_list.add_argument("--status", choices=["open", "done", "overdue"])
    p_list.add_argument("--due-before", dest="due_before", metavar="YYYY-MM-DD")
    p_list.set_defaults(func=cmd_list)

    p_done = sub.add_parser("done", help="Mark an item done.")
    p_done.add_argument("id")
    p_done.set_defaults(func=cmd_done)

    p_followup = sub.add_parser("followup", help="Draft a Gmail follow-up for an owner. Never sends.")
    p_followup.add_argument("owner")
    p_followup.add_argument("--contacts", default=DEFAULT_CONTACTS)
    p_followup.add_argument("--drafts-dir", default="drafts")
    p_followup.set_defaults(func=cmd_followup)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
