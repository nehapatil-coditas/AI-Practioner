# actiontrack

A CLI tool that reads Markdown meeting notes, tracks the action items buried in them, and drafts follow-up emails for review — so nothing gets lost and follow-ups don't get written late (or not at all).

```
actiontrack ingest <folder>      # parse meeting notes, track action items
actiontrack list [filters]       # view/filter tracked items
actiontrack done <id>            # mark an item complete
actiontrack followup <owner>     # draft (never send) a follow-up email
```

## Status

Fully implemented and tested — 133/133 tests passing, validated end-to-end against the sample `notes/notes/` folder. The one open item is real Gmail OAuth wiring for `followup` (see [Known limitations](#known-limitations)). See [STATE.md](STATE.md) for the full build log and design decisions.

## Requirements

- Python 3.11+
- Windows (PowerShell) or any shell with the `py` launcher / `python3` available

## Setup

```bash
py -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

This installs the `actiontrack` package in editable mode along with its dependencies (Typer, Rich, python-dateutil, rapidfuzz) and dev dependencies (pytest).

## Usage

All commands operate on a local `.actiontrack/` folder created in your current working directory — this is where tracked items and tool state live. Run commands either via the installed console script or as a module:

```bash
actiontrack <command> ...
# or, without installing a console script on PATH:
./.venv/Scripts/python.exe -m actiontrack.cli <command> ...
```

### `ingest <folder>`

Parses every `.md` file in `<folder>`, extracts action items (`- [ ] Owner to do the thing by <date>` style checkbox lines), resolves owners and due dates, deduplicates items repeated across multiple meetings, and stores everything locally. Prints a summary including skipped malformed files, ambiguous owners, unassigned owners, and unresolved due dates. Safe to re-run — re-ingesting an unchanged folder won't create duplicates.

```bash
actiontrack ingest notes/notes
```

### `list`

Shows tracked items as a table, with optional filters:

```bash
actiontrack list
actiontrack list --owner "Priya Sharma"
actiontrack list --status overdue        # open | done | overdue
actiontrack list --due-before 2026-11-01
```

"Overdue" is computed live against today's date, never stored — so it's always accurate regardless of when you last ran `ingest`.

### `done <id>`

Marks an item complete by its ID (shown in `list` output):

```bash
actiontrack done 42
```

### `followup <owner>` / `--all`

Drafts a follow-up email summarizing an owner's open and overdue items. **Never sends** — draft only, always requires human review. Use `--all` to draft one for every owner with open/overdue items (ambiguous and unassigned owners are automatically excluded from `--all`).

```bash
actiontrack followup "Priya Sharma"
actiontrack followup --all
```

Requires an email address on file for the owner — add one to `.actiontrack/emails.json`:

```json
{ "Priya Sharma": "priya@example.com" }
```

## Running the tests

```bash
./.venv/Scripts/python.exe -m pytest -q
```

## Project structure

```
actiontrack/
  cli.py                  # Typer CLI entrypoint, wires the 4 commands
  note_parsing.py         # parses a single .md note into raw facts
  date_resolution.py      # resolves raw date phrases to calendar dates
  owner_resolution.py     # resolves raw owner text to identities
  storage.py              # local SQLite persistence (.actiontrack/)
  commands/
    ingest.py             # orchestrates parsing/resolution/storage + dedup
    list_cmd.py            # filtering and dynamic overdue computation
    done.py                # mark an item done
    followup.py            # compose + draft follow-up emails
tests/                     # pytest suite, one file per module
notes/                      # sample meeting notes for testing ingest
requirements.md             # original product requirements
specification.md            # tech stack and architecture
modules/                     # per-module design specs
STATE.md                     # build log / session continuity notes
```

## Known limitations

- **`followup` can't actually send a Gmail draft yet.** The command's logic (filtering, composing, excluding ambiguous/unassigned owners, continuing past per-owner failures) is fully built and tested against a pluggable `DraftClient` interface, but no real Gmail OAuth client is wired in — it will report "Gmail connector not authorized" until one is added.
- A few intentionally-scoped parsing limitations (by design, documented in [STATE.md](STATE.md)): multi-owner lines like "Anita & Rahul to..." resolve to no owner rather than splitting; only `- [ ]`-style checkboxes count as action items (Markdown tables or "ACTION:"-prefixed lines are ignored).
