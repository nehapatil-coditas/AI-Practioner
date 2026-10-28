from pathlib import Path

from actiontrack.note_parsing import MalformedNote, ParsedNote, parse_note


def write_note(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_well_formed_note(tmp_path: Path) -> None:
    path = write_note(
        tmp_path,
        "2026-03-05-standup.md",
        """\
# Meeting Notes
Date: 2026-03-05
Attendees: Priya, Raj, Kavya

## Discussion
Talked about the quote.

## Action Items
- [ ] Priya to send the revised quote by Friday
- [x] Raj reviewed the contract
""",
    )

    result = parse_note(path)

    assert isinstance(result, ParsedNote)
    assert result.raw_meeting_date == "2026-03-05"
    assert result.attendees == ["Priya", "Raj", "Kavya"]
    assert len(result.action_items) == 2

    item1 = result.action_items[0]
    assert item1.raw_owner == "Priya"
    assert item1.raw_task == "send the revised quote by Friday"
    assert item1.raw_due_phrase == "Friday"
    assert item1.done is False

    item2 = result.action_items[1]
    assert item2.raw_owner == "Raj"
    assert item2.done is True
    assert not result.skipped_lines


def test_attendees_as_bulleted_list(tmp_path: Path) -> None:
    path = write_note(
        tmp_path,
        "note.md",
        """\
Date: 2026-03-06
Attendees:
- Priya Sharma
- Raj Kumar

- [ ] Raj to update the doc by next week
""",
    )

    result = parse_note(path)
    assert isinstance(result, ParsedNote)
    assert result.attendees == ["Priya Sharma", "Raj Kumar"]


def test_messy_note_still_extracts_items(tmp_path: Path) -> None:
    path = write_note(
        tmp_path,
        "messy.md",
        """\
some free text with no clear header
lots of rambling discussion that goes on for a while
and more rambling

- [ ] Kavya to follow up with legal before end of month
random trailing note
""",
    )

    result = parse_note(path)
    assert isinstance(result, ParsedNote)
    assert result.raw_meeting_date is None
    assert result.attendees == []
    assert len(result.action_items) == 1
    assert result.action_items[0].raw_owner == "Kavya"


def test_no_checkbox_lines_is_not_an_error(tmp_path: Path) -> None:
    path = write_note(tmp_path, "no-items.md", "Date: 2026-03-07\n\nJust a discussion, no actions.\n")
    result = parse_note(path)
    assert isinstance(result, ParsedNote)
    assert result.action_items == []


def test_action_item_with_no_owner(tmp_path: Path) -> None:
    path = write_note(tmp_path, "note.md", "- [ ] send the follow-up email by Monday\n")
    result = parse_note(path)
    assert isinstance(result, ParsedNote)
    assert result.action_items[0].raw_owner is None
    assert result.action_items[0].raw_task == "send the follow-up email by Monday"


def test_empty_checkbox_line_is_skipped_not_fatal(tmp_path: Path) -> None:
    path = write_note(
        tmp_path,
        "note.md",
        "- [ ]\n- [ ] Priya to send the report\n",
    )
    result = parse_note(path)
    assert isinstance(result, ParsedNote)
    assert len(result.action_items) == 1
    assert result.action_items[0].raw_owner == "Priya"
    assert len(result.skipped_lines) == 1
    assert result.skipped_lines[0][0] == 1


def test_empty_file_is_malformed(tmp_path: Path) -> None:
    path = write_note(tmp_path, "empty.md", "")
    result = parse_note(path)
    assert isinstance(result, MalformedNote)
    assert "empty" in result.reason


def test_whitespace_only_file_is_malformed(tmp_path: Path) -> None:
    path = write_note(tmp_path, "blank.md", "   \n\n   \n")
    result = parse_note(path)
    assert isinstance(result, MalformedNote)


def test_binary_garbage_file_is_malformed(tmp_path: Path) -> None:
    path = tmp_path / "binary.md"
    path.write_bytes(b"\xff\xfe\x00\x01broken\x80\x81")
    result = parse_note(path)
    assert isinstance(result, MalformedNote)


def test_unreadable_missing_file_is_malformed(tmp_path: Path) -> None:
    path = tmp_path / "does-not-exist.md"
    result = parse_note(path)
    assert isinstance(result, MalformedNote)


def test_meeting_date_from_filename_fallback(tmp_path: Path) -> None:
    path = write_note(
        tmp_path,
        "2026-04-10-planning.md",
        "Attendees: Raj\n\n- [ ] Raj to plan the sprint\n",
    )
    result = parse_note(path)
    assert isinstance(result, ParsedNote)
    assert result.raw_meeting_date == "2026-04-10"


def test_plus_bullet_checkbox_supported(tmp_path: Path) -> None:
    path = write_note(tmp_path, "note.md", "+ [ ] Meera to share the forecast by Wednesday\n")
    result = parse_note(path)
    assert isinstance(result, ParsedNote)
    assert len(result.action_items) == 1
    assert result.action_items[0].raw_owner == "Meera"


def test_uppercase_x_checkbox_marks_done(tmp_path: Path) -> None:
    path = write_note(tmp_path, "note.md", "- [X] Karan to approve the Q4 cloud spend\n")
    result = parse_note(path)
    assert isinstance(result, ParsedNote)
    assert result.action_items[0].done is True


def test_checkbox_inside_fenced_code_block_is_ignored(tmp_path: Path) -> None:
    path = write_note(
        tmp_path,
        "note.md",
        """\
Some text.

```
- [ ] Owner to remediate finding by <date>
```

- [ ] Sam to enable MFA on all admin accounts by 2026-10-16
""",
    )
    result = parse_note(path)
    assert isinstance(result, ParsedNote)
    assert len(result.action_items) == 1
    assert result.action_items[0].raw_owner == "Sam"


def test_checkbox_inside_html_comment_is_ignored(tmp_path: Path) -> None:
    path = write_note(
        tmp_path,
        "note.md",
        "<!-- - [ ] Sam to buy hardware tokens for everyone by Friday -->\n"
        "- [ ] Rahul to patch the dependency by Monday\n",
    )
    result = parse_note(path)
    assert isinstance(result, ParsedNote)
    assert len(result.action_items) == 1
    assert result.action_items[0].raw_owner == "Rahul"


def test_checkbox_inside_blockquote_is_ignored(tmp_path: Path) -> None:
    path = write_note(
        tmp_path,
        "note.md",
        "> - [ ] Karan to refund affected customers by Friday\n"
        "- [ ] Karan to refund affected customers\n",
    )
    result = parse_note(path)
    assert isinstance(result, ParsedNote)
    assert len(result.action_items) == 1
    assert result.action_items[0].raw_due_phrase is None


def test_mention_style_owner(tmp_path: Path) -> None:
    path = write_note(tmp_path, "note.md", "- [ ] @anita: audit colour contrast on the dashboard by Mon\n")
    result = parse_note(path)
    assert isinstance(result, ParsedNote)
    assert result.action_items[0].raw_owner == "Anita"
    assert result.action_items[0].raw_task == "audit colour contrast on the dashboard by Mon"


def test_placeholder_owner_words_are_treated_as_no_owner(tmp_path: Path) -> None:
    path = write_note(
        tmp_path,
        "note.md",
        "- [ ] Someone to update the CRM notes\n"
        "- [ ] Team to decide on the launch date\n"
        "- [ ] TBD to write the design-system changelog\n"
        "- [ ] Everyone to review the prototype before the next review\n",
    )
    result = parse_note(path)
    assert isinstance(result, ParsedNote)
    assert all(item.raw_owner is None for item in result.action_items)
    assert len(result.action_items) == 4


def test_due_phrase_uses_last_keyword_not_first(tmp_path: Path) -> None:
    # "on" appears earlier as a plain preposition, not a date introducer;
    # the real due date clause is the later "by Mon".
    path = write_note(tmp_path, "note.md", "- [ ] Anita to audit colour contrast on the dashboard by Mon\n")
    result = parse_note(path)
    assert isinstance(result, ParsedNote)
    assert result.action_items[0].raw_due_phrase == "Mon"


def test_due_phrase_last_keyword_with_multiple_by(tmp_path: Path) -> None:
    path = write_note(tmp_path, "note.md", "- [ ] Sam to cut cloud costs by 10% - proposal by 2026-10-09\n")
    result = parse_note(path)
    assert isinstance(result, ParsedNote)
    assert result.action_items[0].raw_due_phrase == "2026-10-09"


def test_yaml_frontmatter_attendees_list(tmp_path: Path) -> None:
    path = write_note(
        tmp_path,
        "note.md",
        """\
---
title: Team standup
date: 2026-09-16
attendees: [Anita Desai, Lena Fischer, Meera Iyer]
---

- [ ] Lena to draft the case study outline by 2026-09-21
""",
    )
    result = parse_note(path)
    assert isinstance(result, ParsedNote)
    assert result.raw_meeting_date == "2026-09-16"
    assert result.attendees == ["Anita Desai", "Lena Fischer", "Meera Iyer"]


def test_duplicate_task_text_across_lines_both_extracted(tmp_path: Path) -> None:
    # Dedup across files is Module 05's job; this module just extracts facts.
    path = write_note(
        tmp_path,
        "note.md",
        "- [ ] Priya to send the revised quote by Friday\n"
        "- [ ] Priya to send the revised quote by Friday\n",
    )
    result = parse_note(path)
    assert isinstance(result, ParsedNote)
    assert len(result.action_items) == 2
