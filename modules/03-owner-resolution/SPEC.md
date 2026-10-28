# Module 03 — Owner Resolution

## Use case

Action items name an owner as free text (often just a first name). Across 30+ meeting notes, the same person may be referred to inconsistently, and two different people can share a first name (e.g. two "Priya"s). The tool must resolve a raw owner name into a confident identity where possible, and explicitly flag ambiguity rather than guessing — because a follow-up email sent to the wrong "Priya" is worse than no email.

## Responsibilities

- Given a raw owner name text (e.g. "Priya", "Raj K.", "priya"), and the attendee list + any other identity hints available from the same note (and, where useful, across previously-seen notes), resolve it to:
  - A **confirmed identity** (e.g. "Priya Sharma") when enough information disambiguates it, or
  - An **ambiguous marker** (e.g. "Priya (ambiguous)") when multiple known distinct people match the same first name and nothing in the note disambiguates them, or
  - **Unassigned/null** when no owner name was present at all (passthrough from Module 01).
- Maintain/consult a running picture of "known people" built up from attendee lists and any full names seen across ingested notes, so later notes can benefit from identity hints learned earlier (e.g. if "Priya Sharma" appeared with a last name in one note, a bare "Priya" in another note from the same project can be matched to her if she's the only "Priya" known).

## Inputs

- Raw owner name text from an action item (Module 01 output).
- Attendee list (raw names) from the same note (Module 01 output).
- Any additional identifying text found inline in the note (e.g. "Priya S. to send...", or an email address).
- The existing people/identity picture accumulated from prior ingested notes (read from Module 04 storage, or an in-memory structure built during a single `ingest` run).

## Outputs

- Resolved owner value, one of:
  - Full/confirmed identity string.
  - Ambiguous marker string (clearly distinguishable from a confirmed identity, e.g. suffixed `(ambiguous)`).
  - Null (no owner named).
- A flag/reason indicating which case applied, for reporting purposes (confirmed / ambiguous / unassigned).

## Behavior rules

- **Resolution order**:
  1. If the raw owner text already includes a disambiguating detail (last name, initial, email) → use it directly as the confirmed identity (normalized).
  2. Else, check the note's attendee list: if exactly one attendee matches the first name → confirmed identity using that attendee's full name.
  3. Else, check previously accumulated known-people data: if exactly one known person across all ingested notes matches the first name → confirmed identity.
  4. Else, if more than one distinct known person matches the first name and nothing disambiguates → ambiguous marker.
  5. If no name was present at all → null (unassigned), not ambiguous.
- Name matching should be case-insensitive and tolerant of minor formatting differences (e.g. "Priya", "priya", "Priya," ).
- Once a person is confirmed with a full identity (first seen with last name), that identity should be reusable for matching bare first names in later notes, as long as they remain the unique match for that first name.
- If a previously-unique first name later becomes ambiguous (a second distinct person with the same first name is confirmed elsewhere), prior and future bare-first-name references must be treated as ambiguous going forward — the tool should not keep assuming the old single match once ambiguity is known. (Exact re-resolution of already-ingested historical items on later ingest runs is an implementation detail to confirm in Module 05/04, but the identity-matching logic itself must support recognizing the ambiguity the moment it arises.)

## Edge cases this module must handle

- Two distinct full identities share a first name (e.g. "Priya Sharma" and "Priya Patel" both attend meetings) → any bare "Priya" reference with no disambiguating detail resolves to ambiguous, even if one of them is more "frequent."
- Raw owner text has a typo or nickname not exactly matching any attendee (e.g. "Priy" or "PJ") → if no reasonable match is found, treat as a new/unknown raw name (not null, not auto-matched) — stored as the literal raw text as the "confirmed identity" since nothing contradicts it being a distinct new person, unless this creates its own ambiguity later. Must never silently crash.
- Attendee list missing or empty for the note → fall back to previously accumulated known-people data only.
- Owner raw text is empty (Module 01 found no owner) → resolved as null/unassigned, not ambiguous, not an error.
- Same person referred to with different capitalization/spacing across notes → must resolve to the same identity, not be treated as distinct people.

## Dependencies

- Consumes Module 01 output (raw owner text, attendee list) per note.
- Reads/updates identity knowledge that Module 05 (Ingest Command) persists via Module 04 (Storage) across runs.
- Consumed by Module 05 when storing items, Module 06 (`list --owner` filtering), and Module 08 (`followup <owner>` targeting and ambiguous-owner exclusion from `--all`).

## Out of scope

- Deciding how ambiguous items are displayed in `list` output (Module 06) or excluded from bulk followups (Module 08) — this module only produces the resolution result and reason.
- A manual people-directory config file (explicitly not required per the agreed approach — resolution is derived from attendee lists and inline hints only).

## Acceptance criteria

- Given a note where "Priya" is the only Priya in the attendee list and known history, resolves to her full identity.
- Given a note where two distinct "Priya"s are known and nothing disambiguates, resolves to the ambiguous marker.
- Given an action item with no owner text, resolves to null without being flagged ambiguous.
- Given the same person's name spelled differently across two notes, both resolve to the same identity.
