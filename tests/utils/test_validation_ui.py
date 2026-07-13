from utils.validation_ui import bulk_apply, storage_to_choice, toggle_to_storage


def test_toggle_round_trip_present():
    assert toggle_to_storage("correct", True) == "PRESENT_CORRECT"
    assert toggle_to_storage("incorrect", False) == "ABSENT_INCORRECT"
    assert toggle_to_storage(None, True) is None
    assert storage_to_choice("PRESENT_INCORRECT") == "incorrect"
    assert storage_to_choice(None) is None


def test_toggle_round_trip_absent():
    assert toggle_to_storage("correct", False) == "ABSENT_CORRECT"
    assert toggle_to_storage("incorrect", True) == "PRESENT_INCORRECT"


def test_storage_to_choice_all_verdicts():
    assert storage_to_choice("PRESENT_CORRECT") == "correct"
    assert storage_to_choice("ABSENT_CORRECT") == "correct"
    assert storage_to_choice("PRESENT_INCORRECT") == "incorrect"
    assert storage_to_choice("ABSENT_INCORRECT") == "incorrect"
    assert storage_to_choice("NOT_APPLICABLE") is None
    assert storage_to_choice(123) is None


# --- bulk_apply: block-level ✓ all / ✗ all / clear -------------------------


def test_bulk_apply_fills_only_unreviewed():
    # ✓ all fills unreviewed (None) entries, leaves existing marks untouched
    choices = {"a": None, "b": "incorrect", "c": None}
    assert bulk_apply(choices, "correct") == {
        "a": "correct",
        "b": "incorrect",
        "c": "correct",
    }


def test_bulk_apply_incorrect_only_unreviewed():
    choices = {"a": "correct", "b": None}
    assert bulk_apply(choices, "incorrect") == {"a": "correct", "b": "incorrect"}


def test_bulk_apply_clear_resets_everything():
    # verdict=None means clear: every entry goes back to unreviewed
    choices = {"a": "correct", "b": "incorrect", "c": None}
    assert bulk_apply(choices, None) == {"a": None, "b": None, "c": None}


def test_bulk_apply_does_not_mutate_input():
    choices = {"a": None}
    result = bulk_apply(choices, "correct")
    assert choices == {"a": None}  # original untouched
    assert result == {"a": "correct"}


def test_bulk_apply_empty():
    assert bulk_apply({}, "correct") == {}
    assert bulk_apply({}, None) == {}
