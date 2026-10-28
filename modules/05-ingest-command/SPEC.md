# Module 05 — Ingest Command (`actiontrack ingest <folder>`)

## Use case

A team lead points the tool at the folder of meeting notes (30+ files, some messy, some malformed) and expects every real action item across all of them to end up tracked, deduplicated, and ready to query — without having to manually check each file, and without the tool crashing on the bad ones.

## Responsibilities

This module is the **orchestrator** for the ingest pipeline. It does not itself parse Markdown, resolve dates, resolve owners, or persist data — it coordinates Modules 01, 02, 03, and 04 for every file in the folder, then reports the outcome.

For each `.md` file in `<folder>`:
1. Parse the file (Module 01). If it comes back as malformed, record it as skipped with its reason and move to the next file.
2. For each raw action item extracted:
   - Resolve the meeting date and due date (Module 02).
   - Resolve the owner (Module 03), using the note's attendee list and the running identity picture.
   - Check whether this item is a likely duplicate of an already-known item (see Deduplication below).
   - If duplicate: merge into the existing stored item (update due date/status if newer, append this file to its source list).
   - If new: create a new stored item (Module 04).
3. After all files are processed, print a run summary.

## Inputs

- `<folder>` path containing `.md` meeting note files.

## Outputs (CLI)

A summary printed to the terminal, including:
- Number of files processed successfully.
- Number of files skipped (malformed), each with filename + reason.
- Number of action items ingested (new).
- Number of duplicate occurrences merged into existing items.
- Number of items with unresolved/ambiguous owner, listed by raw name and source file.
- Number of items with unresolved due date, listed by item/source file.

## Deduplication logic

- Two action items (possibly from different files) are considered the **same tracked item** when they have a sufficiently similar owner (same resolved identity, or same raw name if unresolved) **and** a sufficiently similar task description (e.g. "Priya to send the revised quote by Friday" appearing near-verbatim across two consecutive weekly notes).
- When a duplicate is detected:
  - The item's due date is updated to the most recently mentioned one (later note wins on due date/status).
  - The item's status reflects the most recent mention (e.g. if a later note shows it checked off, status becomes `done`).
  - The item's source file list grows to include every occurrence, not just the first or last.
- Exact similarity-matching algorithm/threshold is a build-time decision (see requirements.md §7) but must be conservative enough not to merge genuinely different tasks that merely share an owner.

## Behavior rules

- Processing one file must never halt processing of the rest of the folder — errors are caught per-file.
- `ingest` is **idempotent**: running it again on the same unchanged folder produces the same stored state (no new duplicate rows), per Module 04's guarantee.
- Running `ingest` on a folder with new files added since the last run only adds/updates what's new — it doesn't require a clean slate.
- Non-`.md` files in the folder are ignored. Subfolders are not recursed into (per requirements.md — flat folder only), unless this is revisited during build.

## Edge cases this module must handle

- Entire folder is empty or contains no `.md` files → reports zero files processed, not an error.
- Folder path doesn't exist → clear error message, no crash.
- A file is malformed → skipped and reported; rest of folder still processes (Module 01 contract).
- Same task repeated across many (3+) meetings → merged into a single item with full source history, not just deduplicated pairwise.
- An item's owner becomes ambiguous only after processing a later file in the same run (e.g. file 5 introduces the second "Priya") → items from earlier files in the *same* run referencing the now-ambiguous first name should also reflect the ambiguity by the end of the run (not leave some items silently resolved to the wrong person just because of file processing order).

## Dependencies

- Orchestrates Module 01 (Note Parsing), Module 02 (Date Resolution), Module 03 (Owner Resolution), Module 04 (Storage).

## Out of scope

- Displaying/filtering stored items (Module 06).
- Marking items done (Module 07).
- Drafting emails (Module 08).

## Acceptance criteria

- Running against the provided sample `notes/` folder (30+ files, several malformed) completes without crashing, produces a summary matching manual spot-checks of a few files, and all malformed files are named with reasons.
- Re-running ingest on the same folder immediately after does not increase the stored item count.
- A task repeated across 3 sample notes results in exactly one stored item with 3 source files listed.
