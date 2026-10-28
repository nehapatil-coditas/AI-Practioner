from actiontrack.owner_resolution import OwnerDirectory


def test_no_owner_is_unassigned_not_ambiguous() -> None:
    directory = OwnerDirectory()
    result = directory.resolve(None, attendees=["Priya Sharma"])
    assert result.identity is None
    assert result.status == "unassigned"

    result_empty = directory.resolve("   ", attendees=[])
    assert result_empty.identity is None
    assert result_empty.status == "unassigned"


def test_inline_full_name_is_confirmed_directly() -> None:
    directory = OwnerDirectory()
    result = directory.resolve("Raj Kumar", attendees=[])
    assert result.identity == "Raj Kumar"
    assert result.status == "confirmed"


def test_inline_email_is_confirmed_directly() -> None:
    directory = OwnerDirectory()
    result = directory.resolve("priya.sharma@example.com", attendees=[])
    assert result.status == "confirmed"
    assert result.identity == "priya.sharma@example.com"


def test_unique_attendee_match_resolves_bare_first_name() -> None:
    directory = OwnerDirectory()
    result = directory.resolve("Priya", attendees=["Priya Sharma", "Raj Kumar"])
    assert result.status == "confirmed"
    assert result.identity == "Priya Sharma"


def test_two_attendees_sharing_first_name_are_ambiguous() -> None:
    directory = OwnerDirectory()
    result = directory.resolve(
        "Priya", attendees=["Priya Sharma", "Priya Patel", "Raj Kumar"]
    )
    assert result.status == "ambiguous"
    assert result.identity == "Priya (ambiguous)"


def test_resolution_uses_accumulated_history_across_notes() -> None:
    directory = OwnerDirectory()
    # Note 1: Priya Sharma is introduced via the attendee list.
    first = directory.resolve("Priya", attendees=["Priya Sharma", "Raj Kumar"])
    assert first.identity == "Priya Sharma"

    # Note 2: no attendee list at all, just a bare first name — should still
    # resolve via the accumulated directory.
    second = directory.resolve("Priya", attendees=[])
    assert second.status == "confirmed"
    assert second.identity == "Priya Sharma"


def test_ambiguity_learned_from_one_note_persists_for_bare_lookups_in_another() -> None:
    directory = OwnerDirectory()
    directory.resolve("Priya", attendees=["Priya Sharma", "Raj Kumar"])
    directory.resolve("Priya", attendees=["Priya Patel", "Kavya Rao"])

    # Now a third note mentions "Priya" with no attendee list to disambiguate.
    result = directory.resolve("Priya", attendees=[])
    assert result.status == "ambiguous"
    assert result.identity == "Priya (ambiguous)"


def test_attendee_list_can_still_resolve_despite_global_ambiguity() -> None:
    # Per spec: the note's own attendee list is a strong local signal and
    # takes priority over global ambiguity when it uniquely disambiguates.
    directory = OwnerDirectory()
    directory.resolve("Priya", attendees=["Priya Sharma", "Raj Kumar"])
    directory.resolve("Priya", attendees=["Priya Patel", "Kavya Rao"])

    # This note's attendee list only has one Priya.
    result = directory.resolve("Priya", attendees=["Priya Sharma", "Kavya Rao"])
    assert result.status == "confirmed"
    assert result.identity == "Priya Sharma"


def test_unknown_name_with_no_hints_becomes_its_own_identity() -> None:
    directory = OwnerDirectory()
    result = directory.resolve("Priy", attendees=["Priya Sharma"])
    assert result.status == "confirmed"
    assert result.identity == "Priy"


def test_same_person_different_capitalization_resolves_to_one_identity() -> None:
    directory = OwnerDirectory()
    first = directory.resolve("Priya Sharma", attendees=[])
    second = directory.resolve("priya   sharma", attendees=[])
    assert first.identity == "Priya Sharma"
    assert second.identity == "Priya Sharma"


def test_missing_attendee_list_falls_back_to_directory() -> None:
    directory = OwnerDirectory()
    directory.register("Priya Sharma")
    result = directory.resolve("Priya", attendees=[])
    assert result.status == "confirmed"
    assert result.identity == "Priya Sharma"


def test_bare_first_name_with_nothing_known_anywhere_is_new_identity() -> None:
    directory = OwnerDirectory()
    result = directory.resolve("Kavya", attendees=[])
    assert result.status == "confirmed"
    assert result.identity == "Kavya"


def test_initial_merges_with_matching_attendee() -> None:
    directory = OwnerDirectory()
    result = directory.resolve("Priya N.", attendees=["Priya Nair", "Priya Shah", "Karan Joshi"])
    assert result.status == "confirmed"
    assert result.identity == "Priya Nair"


def test_initial_merges_with_other_priya() -> None:
    directory = OwnerDirectory()
    result = directory.resolve("Priya S.", attendees=["Priya Nair", "Priya Shah", "Karan Joshi"])
    assert result.status == "confirmed"
    assert result.identity == "Priya Shah"


def test_initial_with_no_matching_attendee_becomes_literal_identity() -> None:
    directory = OwnerDirectory()
    result = directory.resolve("Priya N.", attendees=["Raj Kumar"])
    assert result.status == "confirmed"
    assert result.identity == "Priya N."


def test_initial_matches_against_accumulated_directory_without_attendee_list() -> None:
    directory = OwnerDirectory()
    directory.register("Priya Nair")
    directory.register("Priya Shah")
    result = directory.resolve("Priya N.", attendees=[])
    assert result.status == "confirmed"
    assert result.identity == "Priya Nair"


def test_two_priyas_in_attendee_list_ambiguous_but_initial_disambiguates() -> None:
    directory = OwnerDirectory()
    attendees = ["Priya Nair", "Priya Shah", "Karan Joshi"]
    bare = directory.resolve("Priya", attendees=attendees)
    assert bare.status == "ambiguous"

    with_initial = directory.resolve("Priya N.", attendees=attendees)
    assert with_initial.status == "confirmed"
    assert with_initial.identity == "Priya Nair"


def test_two_rahuls_sharing_first_name_are_ambiguous() -> None:
    directory = OwnerDirectory()
    result = directory.resolve("Rahul", attendees=["Rahul Mehta", "Rahul Verma", "Anita Desai"])
    assert result.status == "ambiguous"
    assert result.identity == "Rahul (ambiguous)"


def test_to_dict_and_from_dict_round_trip() -> None:
    directory = OwnerDirectory()
    directory.resolve("Priya", attendees=["Priya Sharma", "Raj Kumar"])
    directory.resolve("Priya", attendees=["Priya Patel", "Kavya Rao"])
    directory.register("Raj Kumar")

    snapshot = directory.to_dict()
    restored = OwnerDirectory.from_dict(snapshot)

    result = restored.resolve("Priya", attendees=[])
    assert result.status == "ambiguous"

    result2 = restored.resolve("Raj", attendees=[])
    assert result2.status == "confirmed"
    assert result2.identity == "Raj Kumar"
