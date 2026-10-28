# Module 04 — Storage

## Use case

Parsed, resolved action items need to persist locally between CLI invocations so that `list` and `done` can operate instantly without re-reading and re-parsing every note file, and so `ingest` can run incrementally as new notes are added. This module is the single source of truth for everything the other commands read and write.

## Responsibilities

- Persist action items locally, each with:
  - Unique ID
  - Owner (resolved identity string, ambiguous marker, or null)
  - Task description
  - Due date (resolved absolute date, or null) + reason if null
  - Meeting date (resolved absolute date, or null)
  - Source file(s) — the list of meeting notes this item (or its duplicates) appeared in, most recent last
  - Status: `open` or `done` (overdue is computed dynamically at read time by Module 06, not stored as a static status — see note below)
  - Duplicate/merge metadata: when an item was merged from multiple occurrences, retain references to all source occurrences
- Persist the accumulated "known people" identity picture used by Module 03 across ingest runs (attendee names, confirmed full identities, and which first names are known-ambiguous).
- Provide read/write operations needed by the commands:
  - Insert new item / update existing item (for `ingest` merges)
  - Query items with filters (owner, status, due-before) — for `list`
  - Update a single item's status to `done` by ID — for `done`
  - Fetch open/overdue items grouped by owner — for `followup`
- Guarantee **idempotent** writes: re-ingesting the same notes folder must not create duplicate rows for items already stored.

## Inputs

- Structured, resolved action item records from Module 05 (Ingest Command), which itself orchestrates Modules 01–03.
- Query parameters from Module 06 (List Command), Module 07 (Done Command), Module 08 (Followup Command).

## Outputs

- Persisted records on disk, local to the project (e.g. a `.actiontrack/` folder in the working directory).
- Query results (filtered lists of items) returned to calling commands.
- Confirmation/failure of write operations (e.g. "ID not found" when marking done).

## Behavior rules

- Storage location: a `.actiontrack/` folder in the directory where the tool is run (exact file format — SQLite vs. JSON — is a build-time decision, not fixed by this spec, but must be a single local file/folder requiring no external database service).
- **Status is stored as only `open`/`done`.** "Overdue" is not a stored state — it's `open` + due date in the past, computed at query time (by Module 06) so it's always accurate relative to the real current date, independent of when `ingest` last ran.
- Every write (insert, update, merge, status change) must be safe to run repeatedly and must not corrupt existing data on a partial/failed run (e.g. a crash mid-ingest should not leave the store in a broken state for subsequent commands).
- The store must support looking up an item by its stable ID across multiple `ingest` runs, so that merging (Module 05/01) and status updates (`done`) reference the same row reliably even as new notes are added later.

## Edge cases this module must handle

- Marking `done` on an ID that doesn't exist → return a clear "not found" error, not a silent no-op or crash.
- Concurrent/successive `ingest` runs on a folder where some notes were edited since the last run → updates existing records sensibly rather than duplicating (exact re-ingestion semantics for edited notes to be confirmed during build, but duplication must be avoided).
- Store file missing/corrupted (e.g. deleted mid-use, invalid JSON) → commands fail with a clear, actionable error rather than crashing with a raw stack trace.
- Items with null owner and/or null due date must be storable and queryable without special-casing that breaks filters (see Module 06 edge cases).

## Dependencies

- Written to by Module 05 (Ingest Command).
- Read/written by Module 06 (List Command — read only), Module 07 (Done Command — read + write status), Module 08 (Followup Command — read only).
- Supplies/receives the identity knowledge used by Module 03 (Owner Resolution) during ingest.

## Out of scope

- Parsing or resolving any data itself — it only stores and retrieves what other modules give it.
- Network/remote storage, multi-user sync, or external database servers.

## Acceptance criteria

- Running `ingest` twice on an unchanged folder results in the same number of stored items (no duplicates).
- An item marked `done` via Module 07 remains `done` across subsequent `list`/`ingest` runs until explicitly changed.
- Deleting/corrupting the store file produces a clear error on the next command rather than a crash.
- Items with null owner/due date are stored and retrievable without errors.
