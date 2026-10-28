# Module 02 — Date Resolution

## Use case

Action items reference due dates in many forms — explicit ("by Nov 5"), relative ("by Friday", "next week", "EOD tomorrow"), or absent entirely. The team needs due dates as real calendar dates so `list --due-before` and overdue status actually work. This module takes a raw due-date phrase plus the anchor date it should be interpreted against, and returns a resolved calendar date (or a clear "unresolvable" result).

## Responsibilities

- Resolve a **raw due-date phrase** (from Module 01) into an absolute calendar date, using the **meeting's own date** as the anchor — never the date the tool happens to run on.
- Resolve the **meeting's own raw date string** (from Module 01) into an absolute calendar date, to serve as that anchor.
- Report when a phrase cannot be resolved (and why), rather than guessing.

## Inputs

- Raw due-date phrase (string, possibly empty/null) from an action item.
- Raw meeting date string (string, possibly empty/null) from the note.
- (For meeting date resolution) the source filename, as a fallback hint if the body has no usable date.

## Outputs

- Resolved **meeting date** (absolute calendar date) or null if it cannot be determined from the file at all.
- Resolved **due date** (absolute calendar date) or null, plus a reason when null (e.g. "no due-date phrase found", "meeting date unknown so relative phrase can't be anchored", "phrase not understood").

## Behavior rules

- **Anchor rule**: every relative phrase ("Friday", "next week", "tomorrow", "end of month", "in 3 days") is resolved relative to that note's own meeting date — not `ingest`'s run date, not today's date.
- If the note's meeting date cannot be determined at all, any relative phrase in that note is left unresolved (null) — it must not silently fall back to using the ingest run date as an anchor.
- Explicit/absolute dates in the due-date phrase (e.g. "Nov 5", "2026-11-05", "11/5") are resolved directly and do not require a meeting-date anchor, though the meeting date should still be resolved independently if possible for record-keeping.
- "Friday" (or any weekday name) means the **next occurrence** of that weekday on or after the anchor date (i.e. if the meeting was on a Friday and the item says "by Friday", treat it as that same day unless the phrasing implies otherwise — exact tie-break rules are a build-time detail, but must be documented in code comments/tests once implemented).
- Ambiguous or unrecognized phrases (e.g. "soon", "ASAP", "after the holidays") resolve to null with reason "phrase not understood" rather than being guessed at.
- Resolution must be deterministic — the same phrase + anchor date always produces the same result (no reliance on current wall-clock time except where explicitly resolving "today" for overdue status elsewhere).

## Edge cases this module must handle

- Raw due-date phrase is empty/null → resolved due date is null, reason "no due date mentioned."
- Meeting date is unresolvable and due-date phrase is relative → resolved due date is null, reason "meeting date unknown."
- Meeting date is unresolvable but due-date phrase is an explicit date → due date resolves normally; meeting date remains null.
- Phrase spans an ambiguous weekday reference with no clear direction (e.g. "by Friday" said on a Friday) → documented, consistent tie-break behavior (not a crash, not a silently wrong date).
- Malformed/garbage phrase text (leftover punctuation, trailing words) → best-effort extraction of a date-like token; if none found, resolves to null with reason "phrase not understood."
- Date formats mixing styles across notes (DD/MM vs MM/DD, "5th Nov", "Nov 5th", ISO dates) → parsed where feasible; unresolvable formats return null with a reason rather than misparsing silently (e.g. never silently swap day/month).

## Dependencies

- Consumes raw strings produced by Module 01 (Note Parsing).
- Consumed by Module 05 (Ingest Command), which stores the resolved dates via Module 04 (Storage).
- Consumed by Module 06 (List Command) for computing "overdue" status dynamically against today's date (today's date here is the real current date, not a note's anchor — see Module 06 spec).

## Out of scope

- Deciding status (open/done/overdue) — that's Module 06/04.
- Parsing anything other than dates (owner, task text) — that's Module 01/03.

## Acceptance criteria

- Given an explicit date phrase, resolves correctly regardless of whether the meeting date is known.
- Given a relative phrase and a known meeting date, resolves to the correct calendar date anchored on the meeting date (verified against the sample notes' known meeting dates).
- Given a relative phrase and an unknown meeting date, returns null with a clear reason — never falls back to today's date.
- Given an unrecognized phrase, returns null with reason, never throws and never guesses a plausible-looking but wrong date.
