# Module 01 — Note Parsing

## Use case

A meeting note is a loosely-structured Markdown file. Before anything can be tracked, the tool needs to read one file and pull out of it: the meeting date, the attendee list, and the raw action-item lines (owner + task text + raw due-date phrase + done/open marker). This module is the single place that turns "a Markdown file's text" into "structured facts about one meeting," so every other module works with clean data instead of raw text.

This module does not resolve dates, does not disambiguate owners, and does not decide what gets stored. It only reads a single file and extracts what's literally there (or reports that it couldn't).

## Responsibilities

- Read one `.md` file's content.
- Extract the **meeting date** as written in the file (e.g. a header line, a `Date:` field, or the filename if the body has no date) — returned as a raw string/token, not yet resolved to a calendar date.
- Extract the **attendee list** as written (names as they appear, no identity resolution).
- Extract every **action item line** matching checkbox syntax `- [ ] ...` / `- [x] ...` / `- [X] ...`, and for each one return:
  - raw completion marker (checked / unchecked)
  - raw owner text (the leading name/phrase before the task)
  - raw task description text
  - raw due-date phrase, if any is detectable in the line (e.g. text following "by", "due", "before")
- Classify the file as **parseable** or **malformed** (see Edge Cases) and, if malformed, return a reason instead of partial structured data.

## Inputs

- Path to a single `.md` file.

## Outputs

A structured result per file, containing either:
- **Success**: meeting date (raw), attendee list (raw names), list of raw action-item records (as above), and the source filename/path.
- **Failure**: source filename/path + a human-readable reason the file was skipped.

This module does not write to any store — it returns data to the caller (the ingest command, Module 05).

## Behavior rules

- A file is parsed **best-effort**: inconsistent heading styles, extra whitespace, non-standard bullet characters, long free-form discussion text, and unusual (but still readable) date formats should not cause a failure — just reduced extraction (e.g. no attendee list found, but action items still extracted).
- Only lines matching checkbox task syntax are treated as action items. Free-form text elsewhere in the file is never scanned for action items.
- The raw due-date phrase extraction is a lightweight text split (e.g. text after "by"/"due"/"on"/"before" in the line) — it does **not** interpret what the phrase means. Interpretation belongs to Module 02 (Date Resolution).
- The raw owner extraction assumes the owner is named at or near the start of the task line (e.g. "Priya to send...", "Raj: review the contract"). It returns the leading name text as-is — it does **not** decide whether that name maps to a real, unique person. Identity resolution belongs to Module 03 (Owner Resolution).

## Edge cases this module must handle

- **No meeting date found anywhere** (no header, no field, no usable filename pattern) → file is still parseable; meeting date raw value is returned as empty/null, and the file is NOT marked malformed on this basis alone.
- **No attendee list found** → returned as an empty list; not a failure condition.
- **No checkbox lines at all** → returned as an empty action-item list; not a failure condition by itself (a note can legitimately have zero action items).
- **Malformed file** (file is treated as malformed, i.e. a Failure result, only when parsing cannot proceed safely at all), e.g.:
  - File cannot be read/decoded (binary content, broken encoding).
  - File is empty.
  - Checkbox-like lines exist but are so broken they cannot be split into owner/task at all (e.g. `- [ ]` with no text after it) — that specific line is skipped and reported, not necessarily the whole file (see below).
- **Partially broken lines within an otherwise fine file**: a single malformed action-item line (e.g. empty checkbox, checkbox with only whitespace) is skipped individually with a reason, while the rest of the file continues to be parsed normally. This does not fail the whole file.
- **Checkbox line with no discernible owner** (task starts directly with a verb, no name before it) → owner raw value returned as empty/null; task text still extracted. This is a valid outcome, not an error.

## Dependencies

- None on other modules (this is a foundational module). Produces data consumed by Module 05 (Ingest Command), which in turn feeds Modules 02 and 03.

## Out of scope

- Resolving relative/explicit dates to calendar dates (Module 02).
- Matching owner names to real identities / disambiguation (Module 03).
- Deduplication across files (Module 05 / Module 04).
- Any persistence (Module 04).

## Acceptance criteria

- Given a well-formed sample note, returns correct meeting date, attendee list, and all action items with correct owner/task/raw-due-date/status splits.
- Given a messy-but-readable note (inconsistent formatting, long prose, odd date format), still extracts whatever action items are present without failing.
- Given an empty or unreadable file, returns a Failure result with a clear reason, and does not throw/crash.
- Given a file with one broken checkbox line among several valid ones, returns the valid items and reports only the broken line.
