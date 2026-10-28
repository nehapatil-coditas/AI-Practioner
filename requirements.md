# actiontrack — Requirements

## 1. Overview

`actiontrack` is a CLI tool that reads a team's Markdown meeting notes, extracts action items from them, tracks their status over time, and drafts (but never sends) follow-up emails per owner via the Gmail MCP connector.

Problem it solves: action items buried in meeting notes get lost, and follow-up emails to the responsible people are written late or not at all.

## 2. Inputs

### 2.1 Meeting note format

- Plain Markdown (`.md`) files, one per meeting, stored in a folder (e.g. `notes/`).
- Each note is expected to contain:
  - A **date** (meeting date), typically near the top of the file (e.g. in a header line or front matter).
  - A list of **attendees**.
  - **Action items** written as GitHub-style task list lines, e.g.:
    - `- [ ] Priya to send the revised quote by Friday`
    - `- [x] Raj reviewed the contract`
  - Free-form notes/discussion text elsewhere in the file (not parsed for action items beyond the checkbox lines).
- Notes are not guaranteed to be clean: formatting varies between files, some are long, and some are deliberately malformed (missing date, broken checkbox syntax, truncated files, etc.).
- A sample `notes/` folder with 30+ files (including several long/messy and a few malformed ones) will be provided for testing.

### 2.2 Action item line parsing

From each checkbox line, the tool must extract:
- **Owner** — the person named at the start of the line (e.g. "Priya" in "Priya to send...").
- **Task description** — the remaining text describing what needs to be done.
- **Due date (raw)** — any date phrase present in the line (explicit like "by Nov 5", or relative like "by Friday", "next week", "EOD tomorrow").
- **Completion marker** — `[x]` (or `[X]`) means done; `[ ]` means open.

## 3. Commands

### 3.1 `actiontrack ingest <folder>`

- Parses every `.md` file in `<folder>` (non-recursive by default) for action items.
- For each action item found, stores:
  - Unique ID
  - Owner (resolved, see §4.2)
  - Task description
  - Due date (resolved to an absolute calendar date, see §4.1), or null if unresolvable
  - Source file (path/filename of the meeting note)
  - Meeting date
  - Status: `open`, `done`, or `overdue` (derived — see §4.3)
- Deduplicates items that are substantively the same task repeated across multiple meetings (see §4.4) rather than creating duplicate entries.
- Is **idempotent and incremental**: re-running `ingest` on the same folder (e.g. after new notes are added) updates the store without creating duplicate entries for previously-ingested items.
- At the end of the run, prints a summary: number of files processed, number of items ingested, number of files skipped due to malformed content, and number of duplicates merged.
- Malformed files are skipped (not fatal) and reported individually (filename + reason), per §4.5.

### 3.2 `actiontrack list`

- Displays stored action items in a readable table (ID, owner, task, due date, status, source file).
- Filters (combinable):
  - `--owner <name>` — items for a given owner (supports disambiguation per §4.2).
  - `--status open|done|overdue` — filter by status.
  - `--due-before <date>` — items due before the given date.
- "Overdue" = status is `open` **and** due date is before the current date (today). This is computed dynamically at list/query time, not just at ingest time, so an item's overdue status stays accurate as time passes.
- Items with no owner or no resolvable due date are still listed (see §4.5), with those fields shown as `(unassigned)` / `(no due date)`.

### 3.3 `actiontrack done <id>`

- Marks the action item with the given ID as `done`.
- Errors clearly if the ID does not exist.

### 3.4 `actiontrack followup <owner>`

- Gathers all `open` and `overdue` items for the given owner.
- Drafts a single follow-up email addressed to that owner, summarizing their open and overdue items (task, due date, source meeting/date), clearly separating overdue items from open ones.
- Creates the draft as a **Gmail draft** via the Gmail MCP connector. **It never sends the email** — draft only, always requires human review before sending.
- If the owner has no open/overdue items, the tool reports this and does not create a draft.
- `--all` flag: runs the followup flow for every owner who currently has open or overdue items, creating one draft per owner, and prints a summary of drafts created/skipped.
- If the Gmail MCP connector is not authorized/available, the tool reports a clear actionable error instead of failing silently.

## 4. Core behaviors & edge cases

### 4.1 Due date resolution

- Each note's **meeting date** is parsed as the anchor date for that file (e.g. from a header line or filename).
- Relative due-date phrases ("Friday", "next week", "EOD tomorrow", "end of month") are resolved **relative to the note's own meeting date**, not the date `ingest` is run.
- If a note has no discoverable meeting date, any relative due dates within it cannot be resolved; the item is stored with due date = null and flagged (see §4.5), while absolute/explicit dates in the same file can still be parsed normally.
- Resolved due dates are stored as absolute calendar dates.

### 4.2 Owner name resolution & disambiguation

- Owner names are matched, where possible, against the note's attendee list to confirm identity.
- If a first name alone (e.g. "Priya") matches more than one distinct person across the attendee list / historical data, and no last name or other identifying detail is available anywhere in the note, the item is stored with an ambiguous-owner marker (e.g. `Priya (ambiguous)`), not silently assigned to one person.
- If a last name, initial, or email address is present anywhere in the note (attendee list or inline) that disambiguates the first name, the tool uses it to resolve the owner to a full identity.
- Ambiguous owners are:
  - Listed in `list` output with the ambiguous marker so they're visible.
  - Reported in the `ingest` summary as items needing manual resolution.
  - Excluded from `followup --all` (since the tool cannot confidently address a single person) — running `followup <owner>` with the ambiguous marker explicitly is still allowed.

### 4.3 Status lifecycle

- `open` — not yet marked done, due date in the future or unknown.
- `overdue` — not yet marked done, due date in the past (computed dynamically relative to current date).
- `done` — marked complete via checkbox `[x]` at ingest time, or via `actiontrack done <id>`.

### 4.4 Duplicate items across meetings

- The same action item often recurs verbatim or near-verbatim across multiple meeting notes (e.g. carried over week to week because it's still open).
- `ingest` must detect likely duplicates (same/similar owner + similar task description, optionally same or updated due date) and merge them into a single tracked item rather than creating a new row per occurrence.
- When a duplicate is merged, the tool keeps the most recent due date/status mention and retains a reference to all source meetings it appeared in (not just the first or last).
- The `ingest` summary reports how many duplicates were merged.

### 4.5 Items with no owner or no due date

- Items with no identifiable owner are stored with owner = null and shown as `(unassigned)` in `list`.
- Items with no resolvable due date are stored with due date = null and shown as `(no due date)` in `list`.
- Neither condition causes the item to be dropped — both are tracked and visible so nothing silently disappears.
- These items are excluded from `--due-before` filtering (no date to compare) but included in unfiltered `list` and in `--status` filtering.
- Unassigned items are excluded from any `followup` run (no owner to email) and reported separately in the `ingest` summary as needing manual owner assignment.

### 4.6 Malformed notes

- A "malformed" note is one the parser cannot process safely — e.g. unreadable file, no checkbox-style lines at all combined with no discernible structure, severely broken Markdown, or encoding errors.
- `ingest` must never crash on a malformed file. It skips the file, continues processing the rest of the folder, and reports the skipped file with a reason in the run summary.
- A note that is merely messy but still parseable (inconsistent formatting, long free text, non-standard date formats) should still be parsed as best-effort, extracting whatever action items it can — "messy" is not the same as "malformed."

## 5. Non-functional requirements

- **Never sends email** — `followup` only creates Gmail drafts; sending is always a manual, human action outside the tool.
- **Idempotent ingestion** — safe to re-run `ingest` repeatedly on a growing notes folder without duplicating data.
- **Transparent failure reporting** — every skipped/ambiguous/unresolved case is surfaced to the user in command output, never silently dropped.
- **Local persistence** — parsed action items, their status, and resolution metadata (ambiguous owners, source files, merge history) are stored locally (e.g. JSON or SQLite file in a `.actiontrack/` folder) so that `list` and `done` operate without re-parsing notes each time, and `ingest` can run incrementally.
- **Human-in-the-loop** — the tool assists with tracking and drafting; marking items done and sending emails remain explicit human actions.

## 6. Out of scope (for this version)

- Automatically sending emails.
- Editing or rewriting the original meeting note files.
- Real-time/continuous watching of the notes folder (ingestion is run on-demand).
- Integrations beyond Gmail MCP for follow-ups (e.g. Slack, calendar reminders).
- A GUI or web interface — CLI only.

## 7. Open items for the implementation phase

These are flagged for discussion when we move from requirements to design/build, not blocking this requirements doc:

- Exact CLI output formatting (table library, column widths, color).
- Exact local storage schema (SQLite vs. JSON) and file location.
- Date-parsing library choice for relative phrase resolution.
- Similarity threshold/algorithm for duplicate detection (§4.4).
