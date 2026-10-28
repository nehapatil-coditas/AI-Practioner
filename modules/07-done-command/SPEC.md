# Module 07 — Done Command (`actiontrack done <id>`)

## Use case

Once someone completes an action item (whether or not it was ever checked off in the original Markdown note), the team needs a quick way to mark it complete in the tracker so it stops showing as open/overdue and drops out of future follow-up emails.

## Responsibilities

- Accept an item ID and mark that item's stored status as `done` via Module 04 (Storage).
- Confirm the change to the user, or report a clear error if the ID doesn't exist.

## Inputs (CLI)

- `<id>` — the unique ID of a previously ingested action item (as shown by `actiontrack list`).

## Outputs (CLI)

- On success: confirmation message showing the item's owner/task and its new status.
- On failure (ID not found): clear error message, non-zero exit code, no partial/ambiguous state change.

## Behavior rules

- Marking an already-`done` item as done again is a harmless no-op (confirms it's done, doesn't error).
- This command never modifies the original Markdown note files — it only updates the local store (per requirements.md §6, out of scope).
- Status change takes effect immediately for subsequent `list` and `followup` commands (no caching/staleness).

## Edge cases this module must handle

- ID doesn't exist in the store → clear "no item with ID X" error, non-zero exit code.
- ID exists but belongs to an item with an ambiguous or null owner → still allowed to be marked done (completion doesn't require a resolved owner).
- Non-numeric or malformed ID input → clear error, no crash.

## Dependencies

- Reads/writes via Module 04 (Storage) only.

## Out of scope

- Any parsing, resolution, or filtering logic — purely a status-update operation.
- Editing the source Markdown files.

## Acceptance criteria

- Marking a known open item as done updates its status, and a subsequent `list` reflects the change.
- Marking a non-existent ID produces a clear error and does not alter the store.
- Marking an already-done item as done again succeeds without error or duplication.
