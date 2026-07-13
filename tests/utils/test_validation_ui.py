from utils.validation_ui import storage_to_choice, toggle_to_storage


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
