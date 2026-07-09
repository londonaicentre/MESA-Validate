import pytest

from mesa_validate.selection_resolver import (
    _filter_by_enum_value,
    is_value_present,
    map_storage_to_ui,
)


class TestIsValuePresent:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, False),
            ("", False),
            ("   ", False),
            ("foo", True),
            ([], False),
            ({}, False),
            (["foo"], True),
            ({"foo": "bar"}, True),
            (0, True),
            (False, True),
        ],
    )
    def test_is_value_present_various_values_returns_expected(
        self, value: object, expected: bool
    ) -> None:
        assert is_value_present(value) is expected


class TestMapStorageToUi:
    @pytest.mark.parametrize(
        ("storage_value", "expected"),
        [
            ("PRESENT_CORRECT", "CORRECT"),
            ("ABSENT_CORRECT", "CORRECT"),
            ("PRESENT_INCORRECT", "INCORRECT"),
            ("ABSENT_INCORRECT", "INCORRECT"),
            ("NONE", "NONE"),
            ("NOT_APPLICABLE", "NOT_APPLICABLE"),
            ("foo", "NONE"),
            (None, "NONE"),
        ],
    )
    def test_map_storage_to_ui_various_values_returns_expected(
        self, storage_value: str | None, expected: str
    ) -> None:
        assert map_storage_to_ui(storage_value) == expected


class TestFilterByEnumValue:
    def test_filter_by_enum_value_not_a_list_returns_empty_list(self) -> None:
        assert _filter_by_enum_value("foo", "bar", "baz") == []

    def test_filter_by_enum_value_mixed_items_returns_matching_dicts_only(self) -> None:
        assert _filter_by_enum_value(
            [{"bar": "baz"}, {"bar": "qux"}, "not_a_dict"], "bar", "baz"
        ) == [{"bar": "baz"}]
