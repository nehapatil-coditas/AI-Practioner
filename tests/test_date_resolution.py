from datetime import date

from actiontrack.date_resolution import resolve_due_date, resolve_meeting_date


# ---- meeting date resolution ----


def test_resolve_meeting_date_iso() -> None:
    result = resolve_meeting_date("2026-03-05")
    assert result.date == date(2026, 3, 5)
    assert result.resolved


def test_resolve_meeting_date_month_day_year() -> None:
    result = resolve_meeting_date("March 5, 2026")
    assert result.date == date(2026, 3, 5)


def test_resolve_meeting_date_day_month_year() -> None:
    result = resolve_meeting_date("5th March 2026")
    assert result.date == date(2026, 3, 5)


def test_resolve_meeting_date_none() -> None:
    result = resolve_meeting_date(None)
    assert result.date is None
    assert "no meeting date" in result.reason


def test_resolve_meeting_date_unrecognized() -> None:
    result = resolve_meeting_date("sometime last week")
    assert result.date is None
    assert "not understood" in result.reason


# ---- explicit due dates (anchor irrelevant) ----


def test_due_date_explicit_iso_no_anchor_needed() -> None:
    result = resolve_due_date("2026-11-05", anchor_date=None)
    assert result.date == date(2026, 11, 5)


def test_due_date_explicit_month_name() -> None:
    result = resolve_due_date("Nov 5, 2026", anchor_date=None)
    assert result.date == date(2026, 11, 5)


def test_due_date_slash_mm_dd_convention() -> None:
    # 11 can be a month -> MM/DD/YYYY convention applies: Nov 5, 2026.
    result = resolve_due_date("11/5/2026", anchor_date=None)
    assert result.date == date(2026, 11, 5)


def test_due_date_slash_forced_dd_mm_when_first_number_invalid_month() -> None:
    # 25 cannot be a month, so it must be DD/MM/YYYY: Dec 25, 2026.
    result = resolve_due_date("25/12/2026", anchor_date=None)
    assert result.date == date(2026, 12, 25)


def test_due_date_slash_unresolvable_when_both_invalid() -> None:
    result = resolve_due_date("32/40/2026", anchor_date=None)
    assert result.date is None
    assert result.reason is not None


# ---- relative due dates anchored on meeting date ----


def test_due_date_bare_weekday_same_day_as_anchor() -> None:
    # Meeting is on a Friday; "by Friday" should resolve to that same day.
    friday = date(2026, 3, 6)
    assert friday.weekday() == 4
    result = resolve_due_date("Friday", anchor_date=friday)
    assert result.date == friday


def test_due_date_bare_weekday_upcoming_this_week() -> None:
    # Meeting is Monday 2026-03-02; "by Friday" -> Friday of the same week.
    monday = date(2026, 3, 2)
    result = resolve_due_date("Friday", anchor_date=monday)
    assert result.date == date(2026, 3, 6)


def test_due_date_tomorrow() -> None:
    anchor = date(2026, 3, 2)
    result = resolve_due_date("tomorrow", anchor_date=anchor)
    assert result.date == date(2026, 3, 3)


def test_due_date_eod_tomorrow() -> None:
    anchor = date(2026, 3, 2)
    result = resolve_due_date("EOD tomorrow", anchor_date=anchor)
    assert result.date == date(2026, 3, 3)


def test_due_date_next_week() -> None:
    anchor = date(2026, 3, 2)
    result = resolve_due_date("next week", anchor_date=anchor)
    assert result.date == date(2026, 3, 9)


def test_due_date_next_weekday_skips_current_week() -> None:
    # Meeting is Monday 2026-03-02; "next Friday" should be the Friday of
    # the FOLLOWING week (2026-03-13), not this week's Friday (2026-03-06).
    monday = date(2026, 3, 2)
    result = resolve_due_date("next Friday", anchor_date=monday)
    assert result.date == date(2026, 3, 13)


def test_due_date_end_of_month() -> None:
    anchor = date(2026, 2, 10)
    result = resolve_due_date("end of month", anchor_date=anchor)
    assert result.date == date(2026, 2, 28)


def test_due_date_end_of_week() -> None:
    monday = date(2026, 3, 2)
    result = resolve_due_date("end of week", anchor_date=monday)
    assert result.date == date(2026, 3, 6)  # Friday


def test_due_date_in_n_days() -> None:
    anchor = date(2026, 3, 2)
    result = resolve_due_date("in 3 days", anchor_date=anchor)
    assert result.date == date(2026, 3, 5)


# ---- edge cases per spec ----


def test_due_date_no_phrase() -> None:
    result = resolve_due_date(None, anchor_date=date(2026, 3, 2))
    assert result.date is None
    assert "no due date mentioned" in result.reason


def test_due_date_relative_phrase_with_unknown_anchor_never_falls_back_to_today() -> None:
    result = resolve_due_date("Friday", anchor_date=None)
    assert result.date is None
    assert "meeting date unknown" in result.reason


def test_due_date_unrecognized_phrase_not_guessed() -> None:
    result = resolve_due_date("ASAP", anchor_date=date(2026, 3, 2))
    assert result.date is None
    assert "not understood" in result.reason


def test_due_date_soon_not_guessed() -> None:
    result = resolve_due_date("soon", anchor_date=date(2026, 3, 2))
    assert result.date is None


def test_due_date_day_month_no_year_uses_anchor_year() -> None:
    anchor = date(2026, 9, 3)
    result = resolve_due_date("10 Sep", anchor_date=anchor)
    assert result.date == date(2026, 9, 10)


def test_due_date_month_day_no_year_with_ordinal() -> None:
    anchor = date(2026, 9, 30)
    result = resolve_due_date("Oct 3rd", anchor_date=anchor)
    assert result.date == date(2026, 10, 3)


def test_due_date_day_month_no_year_rolls_to_next_year_if_already_past() -> None:
    anchor = date(2026, 11, 20)
    result = resolve_due_date("10 Sep", anchor_date=anchor)
    assert result.date == date(2027, 9, 10)


def test_due_date_day_month_no_year_with_leading_weekday() -> None:
    anchor = date(2026, 9, 14)
    result = resolve_due_date("Wed 16 Sep", anchor_date=anchor)
    assert result.date == date(2026, 9, 16)


def test_due_date_day_month_no_year_requires_anchor() -> None:
    result = resolve_due_date("10 Sep", anchor_date=None)
    assert result.date is None
    assert "meeting date unknown" in result.reason


def test_meeting_date_with_leading_weekday_name() -> None:
    result = resolve_meeting_date("Monday, 14 September 2026")
    assert result.date == date(2026, 9, 14)


def test_due_date_resolution_is_deterministic() -> None:
    anchor = date(2026, 3, 2)
    first = resolve_due_date("next Friday", anchor_date=anchor)
    second = resolve_due_date("next Friday", anchor_date=anchor)
    assert first.date == second.date
