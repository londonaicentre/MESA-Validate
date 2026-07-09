from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from mesa_validate.models import FieldSelection
from mesa_validate.validation_ui import (
    display_field_value,
    generate_validation_block,
    show_item_validation,
)


@dataclass
class DisplayFieldValueMocks:
    st: MagicMock


@dataclass
class ShowItemValidationMocks:
    st: MagicMock


@dataclass
class GenerateValidationBlockMocks:
    st: MagicMock
    resolve_selection: MagicMock
    display_field_value: MagicMock
    show_item_validation: MagicMock


@pytest.fixture
def display_field_value_mocks(mocker: MockerFixture) -> DisplayFieldValueMocks:
    return DisplayFieldValueMocks(mocker.patch("mesa_validate.validation_ui.st"))


@pytest.fixture
def show_item_validation_mocks(mocker: MockerFixture) -> ShowItemValidationMocks:
    return ShowItemValidationMocks(mocker.patch("mesa_validate.validation_ui.st"))


@pytest.fixture
def generate_validation_block_mocks(
    mocker: MockerFixture,
) -> GenerateValidationBlockMocks:
    return GenerateValidationBlockMocks(
        mocker.patch("mesa_validate.validation_ui.st"),
        mocker.patch("mesa_validate.validation_ui.resolve_selection"),
        mocker.patch("mesa_validate.validation_ui.display_field_value"),
        mocker.patch("mesa_validate.validation_ui.show_item_validation"),
    )


class TestDisplayFieldValue:
    def test_display_field_value_none_shows_not_present(
        self, display_field_value_mocks: DisplayFieldValueMocks
    ) -> None:
        display_field_value(None, "foo")
        assert "Not present" in display_field_value_mocks.st.markdown.call_args.args[0]

    def test_display_field_value_empty_list_shows_empty_list(
        self, display_field_value_mocks: DisplayFieldValueMocks
    ) -> None:
        display_field_value([], "foo")
        assert "Empty list" in display_field_value_mocks.st.markdown.call_args.args[0]

    def test_display_field_value_list_of_dicts_shows_json_per_item(
        self, display_field_value_mocks: DisplayFieldValueMocks
    ) -> None:
        display_field_value([{"bar": "baz"}, {"qux": "quux"}], "foo")
        assert display_field_value_mocks.st.json.call_count == 2
        display_field_value_mocks.st.json.assert_any_call(
            {"bar": "baz"}, expanded=False
        )
        display_field_value_mocks.st.json.assert_any_call(
            {"qux": "quux"}, expanded=False
        )

    def test_display_field_value_list_of_scalars_shows_markdown_per_item(
        self, display_field_value_mocks: DisplayFieldValueMocks
    ) -> None:
        display_field_value(["bar", "baz"], "foo")
        markdown_calls = [
            args[0] for args, _ in display_field_value_mocks.st.markdown.call_args_list
        ]
        assert any("1. bar" in call for call in markdown_calls)
        assert any("2. baz" in call for call in markdown_calls)

    def test_display_field_value_dict_shows_json(
        self, display_field_value_mocks: DisplayFieldValueMocks
    ) -> None:
        display_field_value({"bar": "baz"}, "foo")
        display_field_value_mocks.st.json.assert_called_once_with(
            {"bar": "baz"}, expanded=False
        )

    def test_display_field_value_long_string_shows_text_area(
        self, display_field_value_mocks: DisplayFieldValueMocks
    ) -> None:
        long_value = "x" * 101
        display_field_value(long_value, "foo")
        args = display_field_value_mocks.st.text_area.call_args.args
        assert args[0] == "foo"
        assert args[1] == long_value
        assert (
            display_field_value_mocks.st.text_area.call_args.kwargs["disabled"] is True
        )

    def test_display_field_value_short_scalar_shows_inline_markdown(
        self, display_field_value_mocks: DisplayFieldValueMocks
    ) -> None:
        display_field_value("bar", "foo")
        (html,), _ = display_field_value_mocks.st.markdown.call_args
        assert "foo" in html and "bar" in html


class TestShowItemValidation:
    @pytest.mark.parametrize(
        ("user_choice", "item", "expected"),
        [
            ("None", "foo", None),
            ("Correct", "foo", "PRESENT_CORRECT"),
            ("Correct", None, "ABSENT_CORRECT"),
            ("Incorrect", "foo", "PRESENT_INCORRECT"),
            ("Incorrect", None, "ABSENT_INCORRECT"),
        ],
    )
    def test_show_item_validation_binary_choice_returns_expected_storage(
        self,
        show_item_validation_mocks: ShowItemValidationMocks,
        user_choice: str,
        item: str | None,
        expected: str | None,
    ) -> None:
        show_item_validation_mocks.st.radio.return_value = user_choice
        assert show_item_validation([item], "foo") == expected

    @pytest.mark.parametrize(
        ("current_value", "expected_index"),
        [
            (None, 0),
            ("PRESENT_CORRECT", 1),
            ("ABSENT_INCORRECT", 2),
        ],
    )
    def test_show_item_validation_binary_current_value_sets_default_index(
        self,
        show_item_validation_mocks: ShowItemValidationMocks,
        current_value: str | None,
        expected_index: int,
    ) -> None:
        show_item_validation_mocks.st.radio.return_value = "None"
        show_item_validation(["foo"], "bar", current_value=current_value)
        assert (
            show_item_validation_mocks.st.radio.call_args.kwargs["index"]
            == expected_index
        )

    def test_show_item_validation_list_no_items_only_shows_missed_count(
        self, show_item_validation_mocks: ShowItemValidationMocks
    ) -> None:
        show_item_validation_mocks.st.number_input.return_value = 3
        assert show_item_validation([], "foo", show_missed_count=True) == {
            "items": [],
            "missed": 3,
        }
        show_item_validation_mocks.st.radio.assert_not_called()

    def test_show_item_validation_list_none_placeholder_only_shows_missed_count(
        self, show_item_validation_mocks: ShowItemValidationMocks
    ) -> None:
        show_item_validation_mocks.st.number_input.return_value = 0
        assert show_item_validation([None], "foo", show_missed_count=True) == {
            "items": [],
            "missed": 0,
        }
        show_item_validation_mocks.st.radio.assert_not_called()

    def test_show_item_validation_list_dict_items_maps_choices_to_storage(
        self, show_item_validation_mocks: ShowItemValidationMocks
    ) -> None:
        show_item_validation_mocks.st.radio.side_effect = [
            "Correct",
            "Incorrect",
            "None",
        ]
        show_item_validation_mocks.st.number_input.return_value = 1
        assert show_item_validation(
            [{"foo": "a"}, {"foo": "b"}, {"foo": "c"}], "bar", show_missed_count=True
        ) == {"items": [True, False, None], "missed": 1}
        assert show_item_validation_mocks.st.json.call_count == 3

    def test_show_item_validation_list_scalar_items_shows_markdown_not_json(
        self, show_item_validation_mocks: ShowItemValidationMocks
    ) -> None:
        show_item_validation_mocks.st.radio.return_value = "Correct"
        show_item_validation_mocks.st.number_input.return_value = 0
        show_item_validation(["foo", "bar"], "baz", show_missed_count=True)
        show_item_validation_mocks.st.json.assert_not_called()
        assert show_item_validation_mocks.st.markdown.call_count == 2

    def test_show_item_validation_list_current_value_prefills_defaults(
        self, show_item_validation_mocks: ShowItemValidationMocks
    ) -> None:
        show_item_validation_mocks.st.radio.return_value = "None"
        show_item_validation_mocks.st.number_input.return_value = 2
        show_item_validation(
            [{"foo": "a"}, {"foo": "b"}],
            "bar",
            current_value={"items": [True, False], "missed": 2},
            show_missed_count=True,
        )
        assert (
            show_item_validation_mocks.st.radio.call_args_list[0].kwargs["index"] == 1
        )
        assert (
            show_item_validation_mocks.st.radio.call_args_list[1].kwargs["index"] == 2
        )
        assert show_item_validation_mocks.st.number_input.call_args.kwargs["value"] == 2

    def test_show_item_validation_list_current_value_not_dict_uses_defaults(
        self, show_item_validation_mocks: ShowItemValidationMocks
    ) -> None:
        show_item_validation_mocks.st.radio.return_value = "None"
        show_item_validation_mocks.st.number_input.return_value = 0
        show_item_validation(
            [{"foo": "a"}], "bar", current_value="not_a_dict", show_missed_count=True
        )
        assert show_item_validation_mocks.st.radio.call_args.kwargs["index"] == 0
        assert show_item_validation_mocks.st.number_input.call_args.kwargs["value"] == 0


class TestGenerateValidationBlock:
    def test_generate_validation_block_no_extraction_data_returns_none(
        self,
        generate_validation_block_mocks: GenerateValidationBlockMocks,
        mocker: MockerFixture,
    ) -> None:
        assert (
            generate_validation_block(
                FieldSelection(
                    selection_type="basemodel_field", class_name="foo", field_name="bar"
                ),
                {},
                mocker.Mock(),
                "baz",
            )
            is None
        )
        generate_validation_block_mocks.st.warning.assert_called_once()
        generate_validation_block_mocks.resolve_selection.assert_not_called()

    def test_generate_validation_block_selection_not_in_schema_returns_none(
        self,
        generate_validation_block_mocks: GenerateValidationBlockMocks,
        mocker: MockerFixture,
    ) -> None:
        generate_validation_block_mocks.resolve_selection.side_effect = ValueError(
            "Class Foo not found in schema"
        )
        assert (
            generate_validation_block(
                FieldSelection(selection_type="basemodel_class", class_name="Foo"),
                {"bar": "baz"},
                mocker.Mock(),
                "qux",
            )
            is None
        )
        generate_validation_block_mocks.st.error.assert_called_once_with(
            "Class Foo not found in schema"
        )

    def test_generate_validation_block_basemodel_class_list_item_no_items_found(
        self,
        generate_validation_block_mocks: GenerateValidationBlockMocks,
        mocker: MockerFixture,
    ) -> None:
        generate_validation_block_mocks.resolve_selection.return_value = {
            "items": [],
            "is_list": True,
            "path_found": True,
        }
        generate_validation_block_mocks.show_item_validation.return_value = "result"
        assert (
            generate_validation_block(
                FieldSelection(selection_type="basemodel_class", class_name="Foo"),
                {"bar": "baz"},
                mocker.Mock(),
                "qux",
            )
            == "result"
        )
        generate_validation_block_mocks.st.info.assert_called_once()
        assert (
            generate_validation_block_mocks.show_item_validation.call_args.args[0] == []
        )
        assert (
            generate_validation_block_mocks.show_item_validation.call_args.kwargs[
                "show_missed_count"
            ]
            is True
        )

    def test_generate_validation_block_basemodel_class_list_item_items_found(
        self,
        generate_validation_block_mocks: GenerateValidationBlockMocks,
        mocker: MockerFixture,
    ) -> None:
        generate_validation_block_mocks.resolve_selection.return_value = {
            "items": [{"foo": "a"}],
            "is_list": True,
            "path_found": True,
        }
        generate_validation_block_mocks.show_item_validation.return_value = "result"
        assert (
            generate_validation_block(
                FieldSelection(selection_type="basemodel_class", class_name="Foo"),
                {"bar": [{"foo": "a"}]},
                mocker.Mock(),
                "qux",
            )
            == "result"
        )
        generate_validation_block_mocks.st.info.assert_not_called()
        assert generate_validation_block_mocks.show_item_validation.call_args.args[
            0
        ] == [{"foo": "a"}]
        assert (
            generate_validation_block_mocks.show_item_validation.call_args.kwargs[
                "show_missed_count"
            ]
            is True
        )

    def test_generate_validation_block_basemodel_class_binary_dict_data_displays_each_field(
        self,
        generate_validation_block_mocks: GenerateValidationBlockMocks,
        mocker: MockerFixture,
    ) -> None:
        generate_validation_block_mocks.resolve_selection.return_value = {
            "items": [{"bar": "baz", "qux": "quux"}],
            "is_list": False,
            "path_found": True,
        }
        generate_validation_block_mocks.show_item_validation.return_value = "result"
        assert (
            generate_validation_block(
                FieldSelection(selection_type="basemodel_class", class_name="Foo"),
                {"foo": {"bar": "baz"}},
                mocker.Mock(),
                "corge",
            )
            == "result"
        )
        assert generate_validation_block_mocks.display_field_value.call_count == 2
        generate_validation_block_mocks.display_field_value.assert_any_call(
            "baz", "bar"
        )
        generate_validation_block_mocks.display_field_value.assert_any_call(
            "quux", "qux"
        )
        assert generate_validation_block_mocks.show_item_validation.call_args.args[
            0
        ] == [{"bar": "baz", "qux": "quux"}]
        assert (
            generate_validation_block_mocks.show_item_validation.call_args.kwargs[
                "show_missed_count"
            ]
            is False
        )

    def test_generate_validation_block_basemodel_class_binary_scalar_data_displays_once(
        self,
        generate_validation_block_mocks: GenerateValidationBlockMocks,
        mocker: MockerFixture,
    ) -> None:
        generate_validation_block_mocks.resolve_selection.return_value = {
            "items": ["bar"],
            "is_list": False,
            "path_found": True,
        }
        generate_validation_block(
            FieldSelection(selection_type="basemodel_class", class_name="Foo"),
            {"foo": "bar"},
            mocker.Mock(),
            "baz",
        )
        generate_validation_block_mocks.display_field_value.assert_called_once_with(
            "bar", "Foo"
        )

    def test_generate_validation_block_basemodel_class_binary_no_data_found(
        self,
        generate_validation_block_mocks: GenerateValidationBlockMocks,
        mocker: MockerFixture,
    ) -> None:
        generate_validation_block_mocks.resolve_selection.return_value = {
            "items": [None],
            "is_list": False,
            "path_found": True,
        }
        generate_validation_block(
            FieldSelection(selection_type="basemodel_class", class_name="Foo"),
            {"foo": None},
            mocker.Mock(),
            "baz",
        )
        generate_validation_block_mocks.st.info.assert_called_once()
        generate_validation_block_mocks.display_field_value.assert_not_called()

    def test_generate_validation_block_basemodel_class_binary_path_not_found(
        self,
        generate_validation_block_mocks: GenerateValidationBlockMocks,
        mocker: MockerFixture,
    ) -> None:
        generate_validation_block_mocks.resolve_selection.return_value = {
            "items": [None],
            "is_list": False,
            "path_found": False,
        }
        generate_validation_block(
            FieldSelection(selection_type="basemodel_class", class_name="Foo"),
            {"bar": "baz"},
            mocker.Mock(),
            "qux",
        )
        generate_validation_block_mocks.st.warning.assert_called_once()
        assert generate_validation_block_mocks.show_item_validation.call_args.args[
            0
        ] == [None]

    def test_generate_validation_block_basemodel_field_found_displays_value(
        self,
        generate_validation_block_mocks: GenerateValidationBlockMocks,
        mocker: MockerFixture,
    ) -> None:
        generate_validation_block_mocks.resolve_selection.return_value = {
            "items": ["baz"],
            "is_list": False,
            "path_found": True,
        }
        generate_validation_block(
            FieldSelection(
                selection_type="basemodel_field", class_name="Foo", field_name="bar"
            ),
            {"foo": {"bar": "baz"}},
            mocker.Mock(),
            "qux",
        )
        generate_validation_block_mocks.display_field_value.assert_called_once_with(
            "baz", "bar"
        )
        assert generate_validation_block_mocks.show_item_validation.call_args.args[
            0
        ] == ["baz"]
        assert (
            generate_validation_block_mocks.show_item_validation.call_args.kwargs[
                "show_missed_count"
            ]
            is False
        )

    def test_generate_validation_block_basemodel_field_path_not_found(
        self,
        generate_validation_block_mocks: GenerateValidationBlockMocks,
        mocker: MockerFixture,
    ) -> None:
        generate_validation_block_mocks.resolve_selection.return_value = {
            "items": [None],
            "is_list": False,
            "path_found": False,
        }
        generate_validation_block(
            FieldSelection(
                selection_type="basemodel_field", class_name="Foo", field_name="bar"
            ),
            {"foo": "bar"},
            mocker.Mock(),
            "baz",
        )
        generate_validation_block_mocks.st.warning.assert_called_once()
        generate_validation_block_mocks.st.info.assert_called_once()

    def test_generate_validation_block_enum_value_no_items_found(
        self,
        generate_validation_block_mocks: GenerateValidationBlockMocks,
        mocker: MockerFixture,
    ) -> None:
        generate_validation_block_mocks.resolve_selection.return_value = {
            "items": [],
            "is_list": True,
            "path_found": True,
        }
        generate_validation_block(
            FieldSelection(
                selection_type="enum_value", class_name="Foo", enum_value="bar"
            ),
            {"baz": "qux"},
            mocker.Mock(),
            "corge",
        )
        generate_validation_block_mocks.st.info.assert_called_once()
        assert (
            generate_validation_block_mocks.show_item_validation.call_args.args[0] == []
        )
        assert (
            generate_validation_block_mocks.show_item_validation.call_args.kwargs[
                "show_missed_count"
            ]
            is True
        )

    def test_generate_validation_block_enum_value_items_found(
        self,
        generate_validation_block_mocks: GenerateValidationBlockMocks,
        mocker: MockerFixture,
    ) -> None:
        generate_validation_block_mocks.resolve_selection.return_value = {
            "items": [{"qux": "bar"}],
            "is_list": True,
            "path_found": True,
        }
        generate_validation_block(
            FieldSelection(
                selection_type="enum_value", class_name="Foo", enum_value="bar"
            ),
            {"baz": [{"qux": "bar"}]},
            mocker.Mock(),
            "corge",
        )
        generate_validation_block_mocks.st.info.assert_not_called()
        assert generate_validation_block_mocks.show_item_validation.call_args.args[
            0
        ] == [{"qux": "bar"}]

    def test_generate_validation_block_unexpected_exception_returns_none(
        self,
        generate_validation_block_mocks: GenerateValidationBlockMocks,
        mocker: MockerFixture,
    ) -> None:
        generate_validation_block_mocks.resolve_selection.side_effect = Exception(
            "thud"
        )
        assert (
            generate_validation_block(
                FieldSelection(
                    selection_type="basemodel_field", class_name="Foo", field_name="bar"
                ),
                {"foo": "bar"},
                mocker.Mock(),
                "baz",
            )
            is None
        )
        generate_validation_block_mocks.st.error.assert_called_once()
        generate_validation_block_mocks.st.exception.assert_called_once()
