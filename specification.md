# actiontrack — Root Specification

This is the top-level specification for `actiontrack`. It summarizes the product, lays out the chosen tech stack, and maps the module breakdown to how the code will actually be organized. Detailed behavior for each feature lives in its own `modules/<module>/SPEC.md` (linked below) — this document does not repeat that detail, it ties the pieces together.

See also: [requirements.md](requirements.md) for the full original requirements.

## 1. What we're building

A CLI tool, `actiontrack`, that:
- Parses a folder of Markdown meeting notes.
- Extracts, resolves, deduplicates, and tracks action items (owner, task, due date, status).
- Lets the team list/filter items and mark them done.
- Drafts (never sends) per-owner follow-up emails as Gmail drafts via the Gmail MCP connector.

Four commands: `ingest`, `list`, `done`, `followup`.

## 2. Tech stack

| Concern | Choice | Why |
|---|---|---|
| Language / runtime | **Python 3.11+** | Strong fit for text parsing, date math, and CLI tooling; easy for a small team to read and maintain. |
| CLI framework | **Typer** (built on Click) | Clean command/flag definitions via type hints, auto-generated `--help`, matches our 4-command/flag structure directly. |
| Markdown parsing | **mistune** (or Python's `re`/line-based parsing for checkbox lines) | Lightweight; we don't need full HTML rendering, just structured access to headings, lists, and checkbox task lines. |
| Date parsing/resolution | **`python-dateutil`** for explicit dates + **`parsedatetime`** (or a small custom resolver) for relative phrases ("Friday", "next week") anchored to a given reference date | Both are mature, well-tested libraries; anchoring to an arbitrary reference date (not just "today") is supported by passing a custom base date. |
| Local storage | **SQLite** via Python's built-in `sqlite3` | Zero external dependencies, transactional (safe against partial writes), trivial to query with filters (owner/status/due date), lives as a single file in `.actiontrack/`. |
| Fuzzy text matching (for dedup & name matching) | **`rapidfuzz`** | Fast, well-maintained string-similarity library for comparing task descriptions (dedup) and name variants (owner resolution). |
| Gmail integration | **Gmail MCP connector** (already available in this environment) | Draft-only email creation goes through the existing Gmail MCP tool rather than a custom Gmail API client/OAuth flow — this is the connector the user authorizes once, and the tool is explicitly required never to send. |
| Testing | **pytest** | Standard, works well with the sample `notes/` fixture folder for parsing/resolution tests. |
| Packaging | **`pyproject.toml`** with a console-script entry point (`actiontrack = actiontrack.cli:app`) | Lets the tool be installed and run as a real `actiontrack` command (e.g. via `pip install -e .`), matching the CLI usage shown in requirements.md. |

No database server, no web framework, no external queue — everything runs locally, synchronously, per CLI invocation.

## 3. Project structure

Code structure mirrors the module breakdown directly, so each `modules/<n>/SPEC.md` maps to one Python package/module:

```
actiontrack/
  cli.py                  # Typer app, wires the 4 commands to their handlers
  note_parsing.py         # Module 01
  date_resolution.py      # Module 02
  owner_resolution.py     # Module 03
  storage.py              # Module 04 (SQLite access layer)
  commands/
    ingest.py             # Module 05
    list_cmd.py           # Module 06
    done.py               # Module 07
    followup.py           # Module 08
tests/
  fixtures/notes/         # sample meeting notes used in tests
  test_note_parsing.py
  test_date_resolution.py
  test_owner_resolution.py
  test_storage.py
  test_ingest.py
  test_list.py
  test_done.py
  test_followup.py
pyproject.toml
requirements.md
specification.md          # this file
modules/
  01-note-parsing/SPEC.md
  02-date-resolution/SPEC.md
  03-owner-resolution/SPEC.md
  04-storage/SPEC.md
  05-ingest-command/SPEC.md
  06-list-command/SPEC.md
  07-done-command/SPEC.md
  08-followup-command/SPEC.md
notes/                     # sample meeting notes (provided)
```

## 4. Module map

| # | Module | Type | Spec |
|---|---|---|---|
| 01 | Note Parsing | Shared engine | [modules/01-note-parsing/SPEC.md](modules/01-note-parsing/SPEC.md) |
| 02 | Date Resolution | Shared engine | [modules/02-date-resolution/SPEC.md](modules/02-date-resolution/SPEC.md) |
| 03 | Owner Resolution | Shared engine | [modules/03-owner-resolution/SPEC.md](modules/03-owner-resolution/SPEC.md) |
| 04 | Storage | Shared engine | [modules/04-storage/SPEC.md](modules/04-storage/SPEC.md) |
| 05 | Ingest Command | CLI command | [modules/05-ingest-command/SPEC.md](modules/05-ingest-command/SPEC.md) |
| 06 | List Command | CLI command | [modules/06-list-command/SPEC.md](modules/06-list-command/SPEC.md) |
| 07 | Done Command | CLI command | [modules/07-done-command/SPEC.md](modules/07-done-command/SPEC.md) |
| 08 | Followup Command | CLI command | [modules/08-followup-command/SPEC.md](modules/08-followup-command/SPEC.md) |

Dependency flow: commands (05–08) orchestrate the shared engines (01–04); the shared engines don't depend on the commands or on each other except where noted in their specs (e.g. Module 05 calls 01→02→03→04 in sequence).

## 5. Cross-cutting conventions

- **No network calls** except the Gmail MCP connector in Module 08 — everything else is local file/DB I/O.
- **Never send email** — enforced at the Module 08 boundary; only draft-creation MCP calls are permitted.
- **Never edit the source meeting notes** — all state changes (status, dedup merges) live only in the `.actiontrack/` SQLite store.
- **Fail soft, report loudly**: malformed files, unresolved dates, and ambiguous owners are always skipped/flagged with a clear reason in command output — never a silent drop or an uncaught crash.
- **Determinism**: given the same notes folder and the same "current date," `ingest` and `list` must produce the same results every time (no hidden randomness in dedup/matching).

## 6. Out of scope (reiterated from requirements.md)

- Sending email, editing source notes, a GUI, non-Gmail integrations, real-time folder watching. See [requirements.md §6](requirements.md) for the full list.

## 7. Next step

Review this spec plus the eight module specs under `modules/`. Once approved, implementation proceeds module-by-module in dependency order: 01 → 02/03 → 04 → 05 → 06/07/08.
