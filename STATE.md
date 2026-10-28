# actiontrack — Project State

> Purpose: if this session runs out of context, read this file first to pick up exactly where things left off. Update this file whenever a decision is made, a file is created, or a phase completes.

Last updated: 2026-10-28

## Current phase

**All 8 modules implemented and working end-to-end.** The CLI runs for real against the sample `notes/notes/` folder (33 files ingested, 94 items tracked, 23 duplicate occurrences merged, 2 malformed files correctly skipped). 133/133 tests passing. Remaining known gap: `followup` needs a real Gmail OAuth client wired in (see below) — everything else is functional.

## Decisions made so far

- **Scope**: CLI tool `actiontrack` with 4 commands — `ingest <folder>`, `list`, `done <id>`, `followup <owner>` (+ `--all`). Full detail in [requirements.md](requirements.md).
- **Due date resolution**: relative phrases ("by Friday") resolve against each note's own meeting date as anchor — never the `ingest` run date.
- **Owner disambiguation**: resolved via attendee list + inline full-name/email hints; no separate people-directory config file. Same-first-name collisions with no disambiguating info are stored as an explicit "(ambiguous)" marker, never auto-guessed.
- **Followup scope**: single owner required by default; `--all` flag added to loop over every owner with open/overdue items.
- **Storage**: local file-based persistence in a `.actiontrack/` folder (chosen engine: SQLite — see tech stack below). No external DB server.
- **Tech stack** (user-confirmed): **Python 3.11+**, Typer (CLI), mistune/line-based parsing (Markdown), python-dateutil + parsedatetime (dates), SQLite via stdlib `sqlite3` (storage), rapidfuzz (fuzzy matching for dedup/owner names), Gmail MCP connector (draft-only, never send), pytest (tests), pyproject.toml console-script packaging.
- **Module breakdown**: 8 modules — 4 shared engines (parsing, date resolution, owner resolution, storage) + 4 command modules (ingest, list, done, followup). Dependency flow: commands orchestrate engines; engines are foundational.

## Files created so far

| File | Status | Purpose |
|---|---|---|
| [requirements.md](requirements.md) | ✅ Done, confirmed correct by user | Full original requirements |
| [specification.md](specification.md) | ✅ Done | Root spec: tech stack, project structure, module map, cross-cutting conventions |
| [modules/01-note-parsing/SPEC.md](modules/01-note-parsing/SPEC.md) | ✅ Done | Raw Markdown → raw meeting date/attendees/action-item lines |
| [modules/02-date-resolution/SPEC.md](modules/02-date-resolution/SPEC.md) | ✅ Done | Raw date phrases → resolved calendar dates, anchored on meeting date |
| [modules/03-owner-resolution/SPEC.md](modules/03-owner-resolution/SPEC.md) | ✅ Done | Raw owner text → confirmed identity / ambiguous marker / null |
| [modules/04-storage/SPEC.md](modules/04-storage/SPEC.md) | ✅ Done | Local persistence layer (SQLite), CRUD + query contract |
| [modules/05-ingest-command/SPEC.md](modules/05-ingest-command/SPEC.md) | ✅ Done | Orchestrates 01→02→03→04 per file, dedup/merge, run summary |
| [modules/06-list-command/SPEC.md](modules/06-list-command/SPEC.md) | ✅ Done | Filtering/display, dynamic overdue computation |
| [modules/07-done-command/SPEC.md](modules/07-done-command/SPEC.md) | ✅ Done | Mark item done by ID |
| [modules/08-followup-command/SPEC.md](modules/08-followup-command/SPEC.md) | ✅ Done | Draft per-owner emails via Gmail MCP, `--all` support |
| STATE.md (this file) | ✅ Done | Session continuity / handoff state |

## Implementation progress

| Module | Code | Tests | Status |
|---|---|---|---|
| 01 Note Parsing | `actiontrack/note_parsing.py` | `tests/test_note_parsing.py` (12 passing) | ✅ Done |
| 02 Date Resolution | `actiontrack/date_resolution.py` | `tests/test_date_resolution.py` (24 passing) | ✅ Done |
| 03 Owner Resolution | `actiontrack/owner_resolution.py` | `tests/test_owner_resolution.py` (13 passing) | ✅ Done |
| 04 Storage | `actiontrack/storage.py` | `tests/test_storage.py` (20 passing) | ✅ Done |
| 05 Ingest Command | `actiontrack/commands/ingest.py` | `tests/test_ingest.py` (14 passing) | ✅ Done |
| 06 List Command | `actiontrack/commands/list_cmd.py` | `tests/test_list.py` (14 passing) | ✅ Done |
| 07 Done Command | `actiontrack/commands/done.py` | `tests/test_done.py` (4 passing) | ✅ Done |
| 08 Followup Command | `actiontrack/commands/followup.py` | `tests/test_followup.py` (13 passing) | ✅ Done |
| CLI entrypoint | `actiontrack/cli.py` (Typer app, console script `actiontrack`) | smoke-tested manually (see below) | ✅ Done |

### Project environment

- Virtual env at `.venv/` (created with `py -m venv .venv`; `py` launcher → Python 3.14.3). Run tools via `./.venv/Scripts/python.exe`.
- Installed editable (`pip install -e ".[dev]"`): typer, rich, python-dateutil, rapidfuzz, pytest.
- Note: specification.md originally suggested `mistune`/`parsedatetime` — decided during build to hand-roll line-based Markdown parsing (regex) and a custom date resolver instead, for tighter control over the spec's strict "don't guess, report unresolved" requirements. `pyproject.toml` reflects the actual deps in use (no mistune/parsedatetime).

### Module 02 implementation notes (for continuity)

- `actiontrack/date_resolution.py`: `resolve_meeting_date(raw) -> DateResolution`, `resolve_due_date(raw_phrase, anchor_date) -> DateResolution`. `DateResolution` has `.date` (None on failure) and `.reason` (set only on failure).
- Explicit date formats supported: ISO (`2026-03-05`), `Month D, YYYY`, `D Month YYYY`, and slash dates.
- Slash-date convention (documented, deterministic, not a silent guess): assume `MM/DD/YYYY`; if the first number can't be a valid month (>12), reinterpret as `DD/MM/YYYY`; if neither number is a valid month, unresolved.
- Relative-phrase conventions chosen (all anchored on the note's meeting date, never today's date):
  - Bare weekday ("Friday") = next occurrence **on or after** the anchor, so a meeting held on a Friday with "by Friday" resolves to that same day.
  - "next `<weekday>`" = always skips the current week entirely (e.g. said on a Monday, "next Friday" = the Friday of the *following* week, not this week's).
  - "next week" (no weekday) = anchor + 7 days.
  - "end of month" = last calendar day of the anchor's month.
  - "end of week" = Friday of the anchor's week (business-week convention).
  - "tomorrow" / "EOD tomorrow" = anchor + 1 day; "today"/"EOD" = anchor.
  - "in N days" = anchor + N days.
  - Unrecognized phrases ("ASAP", "soon", "after the holidays") → always unresolved with a reason, never guessed.
- If `anchor_date` is None and the phrase is relative, resolution is always unresolved with reason "meeting date unknown..." — it never silently falls back to today's date (this was a hard requirement from the spec, explicitly tested).

### Module 03 implementation notes (for continuity)

- `actiontrack/owner_resolution.py`: `OwnerDirectory` class holds the accumulated "known people" picture; `.resolve(raw_owner, attendees) -> OwnerResolution(identity, status)` where status is `"confirmed"` / `"ambiguous"` / `"unassigned"`. One `OwnerDirectory` instance is meant to live for an entire `ingest` run (Module 05 will create it, feeding in Module 04's persisted snapshot via `to_dict()`/`from_dict()`, and save it back after the run).
- Identity matching is case/whitespace-insensitive internally (`_canonical` dict keyed by lowercase-normalized name) but always returns the **first-seen casing** as the display identity, so "Priya Sharma" and "priya sharma" across different notes resolve to the same string.
- Resolution order implemented exactly per spec, in this priority: (1) inline disambiguating detail (2+ words or an `@`) → confirmed immediately; (2) note's own attendee list, only counting full names (2+ tokens) there, unique match → confirmed, 2+ matches → ambiguous; (3) accumulated directory unique match → confirmed; (4) directory already flags that first name as ambiguous → ambiguous; (5) nothing known anywhere → the raw text itself becomes a new tentative identity (not rejected, not null).
- **Important nuance implemented**: a note's own attendee list can resolve a name even when that first name is *globally* ambiguous elsewhere, as long as this note's attendee list itself has only one match — attendee-list evidence is locally authoritative and checked before the global-ambiguity fallback. Covered by `test_attendee_list_can_still_resolve_despite_global_ambiguity`.
- Ambiguity "stickiness": once 2+ distinct full identities are registered under the same first name (e.g. via two different notes' attendee lists), any later bare-first-name lookup with no disambiguating attendee list returns the ambiguous marker — tested in `test_ambiguity_learned_from_one_note_persists_for_bare_lookups_in_another`.
- Only `resolve()` calls actually register people into the directory — attendees who are merely *listed* in a note but never referenced as an owner are not auto-registered (unless Module 05's ingest orchestration later decides to pre-register full attendee lists up front; this was intentionally left to Module 05, not baked into Module 03, so check that design question when building the ingest orchestrator).

### Module 04 implementation notes (for continuity)

- `actiontrack/storage.py`: `Storage(project_dir)` opens/creates `<project_dir>/.actiontrack/store.db` (SQLite, stdlib `sqlite3`). Two tables: `items` and `owner_directory` (single-row JSON blob holding `OwnerDirectory.to_dict()`).
- `ActionItem` dataclass is the in-memory record shape: `id, owner, owner_status, task, due_date, due_date_reason, meeting_date, status, source_occurrences` (list of `SourceOccurrence(source_file, meeting_date)` — this is how merge/dedup history across multiple notes is retained, per Module 05's dedup requirement).
- `status` column is constrained to `'open'/'done'` only, by design — **overdue is never stored**, it's computed dynamically by Module 06 on top of `list_items()` results, exactly per spec (so it's always accurate regardless of when `ingest` last ran).
- Key methods: `insert_item`, `update_item` (raises `ItemNotFoundError` if id missing), `mark_done` (idempotent — calling it twice is harmless), `get_item`, `all_items`, `list_items(owner=, status=, due_before=)` (owner match is case-insensitive exact string match; `due_before` excludes items with no due date rather than erroring), `load_owner_directory`/`save_owner_directory`.
- **Storage does not dedupe.** `insert_item` is a plain insert — the duplicate-detection/merge decision (fuzzy-matching owner+task across notes) is explicitly left to Module 05, which will use `list_items(owner=...)` or `all_items()` to find merge candidates before deciding whether to `insert_item` or `update_item`. Confirmed via `test_idempotent_reinsert_does_not_happen_automatically`.
- Corrupted/unreadable DB file raises `StorageError` with a clear message from the `Storage(...)` constructor itself (caught `sqlite3.DatabaseError` on init) — never a raw sqlite3 stack trace.
- `Storage` is a context manager (`with Storage(path) as store:`) and also exposes `.close()` directly for CLI command code that doesn't want a `with` block.

### Module 01 implementation notes (for continuity)

- `actiontrack/note_parsing.py`: `parse_note(path) -> ParsedNote | MalformedNote`.
- Regex gotcha hit during build: `\s*` after a `field:` label (date/attendees) matches newlines too, so it can jump into the next line's content. Fixed by using `[ \t]*` instead of `\s*` around field separators — watch for this pattern if adding more `field:` extractors later.
- Owner extraction has two passes: (1) separator-based ("Priya to...", "Raj: ...", "Kavya - ..."), (2) bare "Name verb..." with no separator ("Raj reviewed the contract"), gated by an `_IMPERATIVE_STARTERS` blocklist (send/update/review/etc.) so sentences like "Send the invoice by Friday" are correctly read as having no owner rather than misreading "Send" as a name.
- Meeting date extraction order: explicit `Date:`/`Meeting Date:` field → date-like token in first 5 lines → date-like token in filename.
- **Enhancements added once the real sample `notes/notes/` folder was available** (these weren't anticipated by the original spec text but were needed for the real data to parse sensibly):
  - Bullet chars: `-`, `*`, and `+` all accepted (sample notes used `+` bullets).
  - Decoy checkboxes are now excluded via `_excluded_line_mask`: lines inside fenced ` ```code blocks``` `, inside `<!-- HTML comments -->` (single- or multi-line), and blockquoted lines (`> ...`) are never scanned for action items. The sample notes deliberately embed a fake "auditor template" checkbox in a code fence, a commented-out line, and a quoted customer remark — all three must never become tracked items.
  - `@mention:` owner syntax supported (e.g. `@anita: audit colour contrast...` → owner "Anita").
  - `_NON_OWNER_WORDS` blocklist ("someone", "anyone", "team", "tbd", "everyone", etc.) — these match the owner-slot grammar but aren't real names, so they resolve to **no owner** rather than being tracked as a fake person. Sample notes include "Someone to update the CRM notes" and "Team to decide on the launch date" specifically to test this.
  - `_extract_due_phrase` now matches the **last** occurrence of by/due/before/on in a line, not the first — "on" is a common plain preposition (e.g. "audit colour contrast **on** the dashboard **by** Mon") and taking the first match was grabbing the wrong, much-too-long phrase.
  - Attendee inline-list parsing now strips surrounding `[...]` brackets, to support YAML-frontmatter-style notes (`attendees: [Anita Desai, Lena Fischer, Meera Iyer]`), which some sample notes use instead of a plain `Attendees:` line.
  - **Known accepted limitations** (graceful degradation, not crashes): multi-owner syntax ("Anita & Rahul to...", "Lena (with Priya) to...") resolves to no owner rather than parsing both names; Markdown table rows and "ACTION:"-prefixed lines are never treated as action items (only `- [ ]`-style checkboxes count, per spec).

## Module 02 real-data follow-up fixes

- Added tolerance for a leading weekday name before an explicit date ("Monday, 14 September 2026", "Wed 16 Sep") — stripped before parsing.
- Added **month+day without a year** resolution ("10 Sep", "Oct 3rd", "15 October") for due-date phrases only (never for meeting dates, which have no anchor to borrow a year from): assumes the anchor's year, rolling forward one year if that date would already be in the past relative to the anchor — same "next occurrence" convention used for bare weekdays.

## Module 05 implementation notes (for continuity)

- `actiontrack/commands/ingest.py`: `run_ingest(folder, project_dir) -> IngestSummary`. Raises `IngestError` if the folder doesn't exist.
- **Resolved the open design question from Module 03's notes**: attendee lists ARE pre-registered into the `OwnerDirectory` up front, for every file in the folder, *before* any single owner reference is resolved. This makes ambiguity detection independent of file-processing order — a name that only becomes ambiguous because of a file processed later still correctly applies to items from earlier files in the same run (tested in `test_ambiguous_owner_detected_mid_run_applies_to_earlier_file_too`). Files are processed in sorted-filename order (which is chronological given the `YYYY-MM-DD-*.md` naming convention), so "most recent mention wins" for merges lines up with real meeting order.
- Dedup/merge: `_find_duplicate` matches items with the exact same resolved owner string (case-insensitive) and a rapidfuzz `token_sort_ratio` ≥ `DEDUP_SIMILARITY_THRESHOLD = 82` on a **due-phrase-stripped** core task string (comparing "share updated wireframes" against "share updated wireframes by Thursday" without stripping scored too low and wrongly created a duplicate — fixed by stripping trailing by/due/before/on clauses before comparing, display text is untouched).
- Merge rule actually implemented: status always takes the latest occurrence's value; due date only overwrites if the new occurrence actually resolves one (so a later mention with no due-date phrase doesn't erase a previously known due date). A given `(item, source_file)` pair is only appended once to `source_occurrences`, which is what makes re-running `ingest` on an unchanged folder idempotent (confirmed in `test_ingest_is_idempotent`).
- Validated end-to-end against the real `notes/notes/` sample folder (33 processed, 2 skipped malformed, 94 items, 23 merges, 7 ambiguous-owner flags, 7 unassigned-owner flags, 46 unresolved-due-date flags — all manually spot-checked and correct).

## Module 06/07/08 implementation notes (for continuity)

- `actiontrack/commands/list_cmd.py`: `list_items(project_dir, owner=, status=, due_before=, today=)`. `status="overdue"` and `status="open"` are both computed dynamically via `effective_status()` on top of `Storage.list_items` results — plain stored-`"open"` items that are actually overdue are excluded from a `--status open` filter (overdue is its own bucket, per spec). `today` is an injectable parameter (defaults to `date.today()`) specifically so tests are deterministic.
- `actiontrack/commands/done.py`: thin wrapper around `Storage.mark_done`; re-exports `ItemNotFoundError`.
- `actiontrack/commands/followup.py`: business logic (filtering open/overdue, excluding ambiguous/unassigned from `--all`, composing the email, continuing past per-owner failures) is fully decoupled from actual email sending via a `DraftClient` Protocol. **No real Gmail integration exists yet** — the CLI wires in `UnavailableDraftClient`, which always raises "Gmail connector not authorized — connect it and retry." This is intentional and matches the spec's requirement to fail clearly when the connector isn't available, but it means `followup` cannot actually create a Gmail draft until someone wires up real OAuth (e.g. `google-api-python-client` + `google-auth-oauthlib`, likely as a new `GmailDraftClient` implementing the same `DraftClient.create_draft()` protocol).
- Email addresses: since requirements explicitly ruled out a people-directory file for *name* resolution, but a real email address is still needed to actually draft anything, a separate, optional `.actiontrack/emails.json` (simple `{"Full Name": "email@example.com"}` map) was introduced purely for this purpose. Not present by default; `followup` reports "no email address on file for X" per owner when missing, rather than failing the whole run.
- An item's owner_status is checked for the explicit single-owner path (ambiguous markers are allowed when the user explicitly names them) vs the `--all` path (ambiguous excluded automatically, unassigned/null owners never included at all since they have no identity string).

## Not yet done / known gaps

- **Real Gmail OAuth wiring** for `followup` — needs a `GmailDraftClient` (or similar) implementing `DraftClient`, plus the user's own Google Cloud OAuth credentials. Out of scope for this coding session; the business logic around it is fully built and tested.
- `.actiontrack/emails.json` has no CLI command to manage it yet (manual JSON editing only) — could add a small `actiontrack contacts` command later if useful, but wasn't requested.
- No packaging/distribution step beyond local editable install (`pip install -e .`) — fine for this project's scope.
- Known accepted parsing limitations documented above (multi-owner lines, table-row/`ACTION:`-prefixed "action items" are never parsed) — intentional, not bugs.

## Next step

Core functionality is complete and verified against the real sample notes. Natural next steps, if desired: (1) wire up a real `GmailDraftClient` for `followup`, (2) widen/adjust the `rich` table output in `cli.py` (currently truncates long filenames at default terminal width — cosmetic only), (3) add a `.gitignore` for `.venv/`, `.actiontrack/`, `*.egg-info/` if this becomes a git repo.

## How to resume this session

If context is lost, a new session should:
1. Read this STATE.md file first — it reflects a fully working, tested CLI tool.
2. Read `requirements.md` and `specification.md` for full background context.
3. Skim `modules/*/SPEC.md` only as needed for the module being touched.
4. Run `./.venv/Scripts/python.exe -m pytest -q` to confirm the baseline (should be 133 passing) before making changes.
5. To try the CLI for real: `./.venv/Scripts/python.exe -m actiontrack.cli ingest notes/notes` from the project root (creates `.actiontrack/store.db`), then `... list`, `... done <id>`, `... followup <owner>`.
