# Module 06 — List Command (`actiontrack list`)

## Use case

Once items are ingested, the team needs a quick way to see what's outstanding — everything, or narrowed to a specific person, status, or deadline — without digging back through meeting notes.

## Responsibilities

- Read all stored action items from Module 04 (Storage).
- Apply requested filters.
- Compute **overdue** status dynamically (at the moment `list` runs), not from a stored static value.
- Render a readable table to the terminal: ID, owner, task, due date, status, source file(s).

## Inputs (CLI flags)

- `--owner <name>` — show only items belonging to the given owner. Must work with resolved full identities and should give a helpful result (or clear note) if the given name matches an ambiguous marker or multiple people.
- `--status open|done|overdue` — filter by status.
- `--due-before <date>` — show only items with a resolved due date earlier than the given date.
- No flags → show all items.
- Flags are combinable (e.g. `--owner Priya --status overdue`).

## Outputs (CLI)

- A table of matching items with columns: ID, Owner, Task, Due Date, Status, Source File(s).
- Items with no owner render as `(unassigned)`.
- Items with no resolved due date render as `(no due date)`.
- If no items match the filters, a clear "no matching items" message (not a blank table with no explanation).

## Behavior rules

- **Overdue computation**: an item is displayed as `overdue` when its stored status is `open` AND its resolved due date is earlier than the current real-world date (the date `list` is actually run), regardless of when it was ingested. An item stored as `open` with a due date in the future shows as `open`, not `overdue`.
- Items with status `done` never show as `overdue`, even if their due date has passed.
- `--due-before` compares only against items that have a resolved due date; items with no due date are excluded from a `--due-before` filtered result (they neither match nor error).
- `--owner` matching should use the same identity resolution conventions as Module 03 (case-insensitive, matches the resolved identity string); if the given name corresponds to more than one resolved identity or an ambiguous marker exists under that first name, the tool should show results with a note clarifying which identity/ambiguity group was matched, rather than silently picking one.

## Edge cases this module must handle

- `--owner` value matches an ambiguous-marker identity (e.g. `--owner "Priya (ambiguous)"`) → returns those ambiguous items; also works if the user passes just `--owner Priya` by matching against ambiguous entries and noting the ambiguity in output.
- `--due-before` given an unparsable date string → clear error, no crash.
- Combination of filters that yields zero results → clear "no matching items" message.
- Store is empty (no `ingest` run yet) → clear message instructing the user to run `ingest` first, not an empty/confusing table.
- Items with null owner/due date appear correctly in unfiltered `list` and in `--status` filters, labeled per above.

## Dependencies

- Reads from Module 04 (Storage) only. Does not call Modules 01/02/03 directly (all resolution already happened during `ingest`), except for interpreting `--due-before`'s input date string, which reuses the same date-parsing capability as Module 02 for explicit dates.

## Out of scope

- Writing/modifying any stored data (read-only command).
- Sorting behavior beyond a sensible default (e.g. by due date ascending, overdue first) — exact default sort order is a build-time detail.

## Acceptance criteria

- Running `list` with no flags after a sample ingest shows all items with correct statuses, including dynamically computed overdue items.
- `--owner`, `--status`, and `--due-before` each filter correctly alone and in combination.
- An item due yesterday with status `open` shows as `overdue`; the same item marked `done` does not.
- Items with `(unassigned)` owner or `(no due date)` display correctly and don't break other filters.
