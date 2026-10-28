# actiontrack — Requirements

## 1. Purpose

Meeting notes pile up as markdown files. Action items buried in them get lost, and
follow-up emails are written late or never. `actiontrack` is a CLI that:

1. Parses meeting notes for action items.
2. Tracks each item's owner, task, due date, source and status.
3. Lets the team query and update that tracked state.
4. Drafts (never sends) a Gmail follow-up per owner, summarizing their open and
   overdue items.

## 2. Input format

- Input is a folder of `.md` files, one meeting note per file.
- Each note is expected to contain:
  - A **date** for the meeting (front-matter, a `Date:` line, or a parseable date
    in the first few lines — parser should accept common variants).
  - An **attendees** list (names, ideally with last names, e.g. `Priya Sharma`,
    `Priya Verma`) used later for owner disambiguation.
  - Free-form notes containing **action items** as markdown task list lines, e.g.:
    ```
    - [ ] Priya to send the revised quote by Friday
    - [x] Rahul to update the slide deck
    ```
    - `- [ ]` = open, `- [x]` = done (as authored in the source note).
    - The sentence after the checkbox is free text: `<owner> to <task> [by <due>]`.
      Owner and due date are extracted heuristically from this text; the task
      description is the remainder.

## 3. Commands

### 3.1 `actiontrack ingest <folder>`

- Walks `<folder>` for all `*.md` files (recursively).
- For each file:
  - Parse meeting date and attendee list.
  - Extract every action-item line.
  - For each item, resolve:
    - **Owner**: see §5 (name resolution).
    - **Task**: the remaining free text after owner/due-date extraction.
    - **Due date**: resolved to an absolute calendar date — see §4.
    - **Status**: `open` or `done`, from the checkbox state in the source line.
    - **Source**: file path + meeting date, for traceability.
  - Assign each item a stable **id** used by `done <id>` and display.
- **Duplicate items** (the same task repeated verbatim or near-verbatim across
  multiple notes, e.g. a recurring reminder) are stored as a single logical item
  whose source list references every file it appeared in, not duplicated rows.
  Near-duplicate detection is a normalized match (case/whitespace-insensitive,
  same owner + same task text); exact rule to be refined during implementation,
  but it must not create N separate open items for one recurring task.
- **Malformed notes** (missing date, unparsable structure, binary/garbage
  content, etc.) are **skipped**, not fatal — ingestion continues with the rest
  of the folder, and a summary at the end reports:
  - Total files scanned.
  - Files successfully ingested, with item counts.
  - Files skipped, with a one-line reason each.
- Ingest is idempotent / re-runnable: re-ingesting the same folder updates
  existing stored items (e.g. picks up new `done` checkboxes) rather than
  duplicating them.

### 3.2 `actiontrack list`

- Prints tracked items in a readable table: id, owner, task, due date, status,
  source.
- Filters (combinable):
  - `--owner <name>` — exact or disambiguated owner match (see §5).
  - `--status open|done|overdue` — see §4 for the overdue definition.
  - `--due-before <date>` — items whose resolved due date is before the given
    date.
- No filters = list everything.

### 3.3 `actiontrack done <id>`

- Marks the item with the given id as `done` in the stored state.
- Errors clearly (non-zero exit, readable message) if the id doesn't exist.
- Does **not** rewrite the original source `.md` file — status lives in
  actiontrack's own store, updated independently of ingest.

### 3.4 `actiontrack followup <owner>`

- Resolves `<owner>` using the same name-resolution rules as `--owner` (§5);
  if ambiguous, lists the possible matches and asks the caller to
  disambiguate instead of guessing.
- Gathers that owner's **open** and **overdue** items.
- Drafts a follow-up email (subject + body summarizing the items, grouped by
  overdue vs. open, each with task and due date).
- Resolves the owner's email address via the contacts file (§6).
- Creates the draft via the **Gmail MCP connector**'s draft-creation
  capability. It **never sends** the email — draft only, left for human
  review.
- If the owner has no open/overdue items, the command reports that and does
  not create a draft.

## 4. Due dates & status

- **Date anchor**: relative due dates in note text (e.g. "by Friday", "next
  Tuesday", "EOD tomorrow") are resolved relative to **the meeting's own
  date** (from that note's metadata), not today's date. This is what the
  speaker actually meant at the time and keeps re-ingesting old notes
  accurate.
- **Overdue** is **not** a separately stored status. It's computed
  dynamically at query/report time:
  > an item is overdue if `status == open` AND `resolved_due_date < today`.
  - Items with no resolvable due date are never classified as overdue.
  - `done` items are never overdue regardless of due date.
- Stored statuses are only `open` and `done`; `overdue` is a derived view
  used by `--status overdue` filtering and by `followup`.

## 5. Owner / name resolution

- Action item text often names an owner by **first name only** (e.g.
  "Priya to send...").
- Each note's **attendee list** is the source of truth for who was in the
  room; it should include full names (first + last) where possible.
- Resolution algorithm:
  1. Match the first name in the action-item text against the note's
     attendee list.
  2. If exactly one attendee matches that first name, resolve to that full
     name.
  3. If **more than one** attendee shares that first name (e.g. two
     "Priya"s), the item is stored with an **ambiguous owner** marker
     (not silently assigned to either person) and surfaced in `list` /
     ingest summary for manual follow-up.
  4. If **no owner** can be extracted at all (no name found in the item
     text, or no attendee list), store as `owner: unassigned` and surface
     similarly — never crash or silently drop the item.
- `--owner <name>` filters accept a full name; accept a bare first name only
  when it's unambiguous across stored items, otherwise require
  disambiguation (e.g. `"Priya Sharma"`).

## 6. Contacts / email resolution (for `followup`)

- A user-maintained **contacts file** (e.g. `contacts.yaml`) maps full names
  (matching the resolved owner names from §5) to email addresses:
  ```yaml
  priya sharma: priya.sharma@example.com
  priya verma: priya.verma@example.com
  rahul: rahul@example.com
  ```
- `followup <owner>` looks up the resolved owner's email in this file.
- If the owner isn't found in the contacts file, the command fails clearly,
  naming the missing contact, and does **not** attempt to guess or create a
  draft with an empty/incorrect recipient.
- Items with `owner: ambiguous` or `owner: unassigned` cannot be targeted by
  `followup` directly — they must be resolved (manually, out of band) before
  a follow-up can be sent for them.

## 7. Storage

- Ingested items persist locally between CLI invocations (e.g. a local JSON
  or SQLite store) so `list`, `done`, and `followup` operate on previously
  ingested data without re-parsing notes each time.
- Re-running `ingest` on the same or an overlapping folder updates/merges
  into this store rather than duplicating it (see duplicate handling in
  §3.1).

## 8. Robustness / edge cases summary

| Case | Required behavior |
|---|---|
| Duplicate items across meetings | Merge into one logical item; track all source files |
| Item with no owner | Store as `unassigned`, never crash, surfaced in output |
| Item with no due date | Store with null due date; never counted as overdue |
| Two attendees, same first name | Store as `ambiguous`, never guessed |
| Malformed/unparsable note | Skip file, log reason, continue ingesting the rest |
| Re-ingesting same folder | Idempotent update, not duplicate rows |
| `followup` with no email on file | Fail with a clear, actionable error |
| `followup` for owner with no open/overdue items | No-op with a message, no draft created |

## 9. Out of scope (for this version)

- Sending emails automatically (drafts only, by design).
- Editing/reassigning an item's owner via the CLI (requires manual contacts
  file edits).
- Syncing status changes back into the original `.md` source files.
- Natural-language due dates beyond common relative-day phrasing (e.g. no
  support for fiscal quarters, "mid next month", etc. — best-effort only).
