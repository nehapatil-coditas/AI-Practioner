# Module 08 — Followup Command (`actiontrack followup <owner>` / `--all`)

## Use case

Follow-up emails chasing people on their open action items get written late or skipped entirely. This command drafts that email automatically — summarizing one person's open and overdue items — and puts it in Gmail as a draft, so a human only needs to glance over it and hit send.

## Responsibilities

- Given an owner, gather all their `open` and `overdue` items (via Module 04/06 logic).
- Compose a single email draft body summarizing those items, clearly separating overdue from open.
- Create the draft in Gmail via the Gmail MCP connector.
- **Never send** the email — draft creation only.
- Support `--all`: loop through every owner currently having open/overdue items and create one draft per owner, skipping ambiguous/unassigned owners, then print a summary.

## Inputs (CLI)

- `<owner>` — a single owner's resolved identity (or an ambiguous-marker identity, explicitly, if the user specifically requests it — see Edge Cases).
- `--all` — alternative mode, no owner argument; applies to all owners with open/overdue items.

## Outputs

- A new Gmail draft (created via MCP), addressed to the owner, containing:
  - A summary of overdue items (task, original due date, source meeting date/file).
  - A summary of still-open (not yet overdue) items.
- CLI confirmation that a draft was created (and, ideally, a reference/link if the Gmail MCP response provides one).
- With `--all`: a summary listing which owners got drafts created, and which were skipped (and why — e.g. "no open items," "ambiguous owner").

## Behavior rules

- Only `open` and `overdue` items are included — `done` items are never mentioned in a follow-up draft.
- If the owner has zero open/overdue items, no draft is created; the tool reports this clearly instead.
- The email must clearly distinguish **overdue** items (flagged prominently, e.g. listed first or marked "OVERDUE") from items that are simply still open but not yet due.
- `--all` **excludes** ambiguous owners automatically (the tool cannot confidently address a single real person) and excludes unassigned/null-owner items entirely (no email address to draft to).
- Running `followup <owner>` with an explicit ambiguous-marker identity (e.g. `"Priya (ambiguous)"`) as the literal argument is still permitted — the user is explicitly taking responsibility for that choice — but plain `--all` never does this automatically.
- If the Gmail MCP connector is unavailable or unauthorized, the command fails clearly with an actionable message (e.g. "Gmail connector not authorized — connect it and retry") rather than silently skipping or crashing.

## Edge cases this module must handle

- Owner name given doesn't match any known identity → clear "no such owner" error, no draft created.
- Owner has items but all are `done` → reports "nothing to follow up on," no draft.
- `--all` run when no owners have any open/overdue items → reports "nothing to follow up on," no drafts created, not an error.
- `--all` run where some owners succeed and others fail (e.g. Gmail API hiccup on one) → continues processing remaining owners, reports per-owner success/failure in the final summary rather than aborting the whole run.
- Owner's identity needs an actual email address to draft to — if no email address is resolvable for a confirmed identity (e.g. attendee lists only ever had first names, no email captured), the tool reports this clearly per owner rather than creating a broken/unaddressed draft.

## Dependencies

- Reads open/overdue items from Module 04 (Storage), using the same overdue computation logic as Module 06 (List Command).
- Uses the Gmail MCP connector to create drafts (external dependency — must be authorized in the user's environment before this command can succeed).

## Out of scope

- Sending email under any circumstance.
- Editing/deleting existing drafts.
- Any UI beyond CLI confirmation output.

## Acceptance criteria

- Running `followup <owner>` for someone with a mix of overdue and open items creates exactly one Gmail draft, correctly separating the two categories.
- Running `followup <owner>` for someone with no open/overdue items creates no draft and says so.
- Running `followup --all` creates one draft per eligible owner, skips ambiguous/unassigned owners, and reports a clear per-owner summary.
- If the Gmail connector isn't authorized, the command reports this clearly instead of failing silently or crashing.
