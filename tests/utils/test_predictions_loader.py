from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel
from pytest_mock import MockerFixture

from utils.models import Session
from utils.predictions_loader import (
    _load_json_records,
    _load_prediction_folder,
    _normalise_record,
    _validate_output_schema,
    extract_field_value,
    get_prediction_files,
    list_prediction_folders,
    load_prediction_file,
    validate_and_filter_files,
)
from utils.types import Err, Ok, PredictionDocument


class SampleSchema(BaseModel):
    foo: str


@dataclass
class LoadJsonRecordsMocks:
    read_text: MagicMock


@dataclass
class NormaliseRecordMocks:
    from_legacy: MagicMock
    from_document_input: MagicMock
    from_inference: MagicMock


@dataclass
class LoadPredictionFolderMocks:
    exists: MagicMock
    is_dir: MagicMock
    glob: MagicMock
    load_json_records: MagicMock
    normalise_record: MagicMock


@dataclass
class ListPredictionFoldersMocks:
    exists: MagicMock
    glob: MagicMock
    iterdir: MagicMock


@dataclass
class LoadPredictionFileMocks:
    load_prediction_folder: MagicMock


@dataclass
class GetPredictionFilesMocks:
    load_prediction_folder: MagicMock


@dataclass
class ValidateAndFilterFilesMocks:
    schema_inspector: MagicMock
    load_prediction_file: MagicMock
    validate_output_schema: MagicMock


@pytest.fixture
def validate_and_filter_files_mocks(
    mocker: MockerFixture,
) -> ValidateAndFilterFilesMocks:
    return ValidateAndFilterFilesMocks(
        mocker.patch("utils.schema_inspector.SchemaInspector"),
        mocker.patch("utils.predictions_loader.load_prediction_file"),
        mocker.patch("utils.predictions_loader._validate_output_schema"),
    )


@pytest.fixture
def load_json_records_mocks(mocker: MockerFixture) -> LoadJsonRecordsMocks:
    return LoadJsonRecordsMocks(mocker.patch.object(Path, "read_text"))


@pytest.fixture
def normalise_record_mocks(mocker: MockerFixture) -> NormaliseRecordMocks:
    return NormaliseRecordMocks(
        mocker.patch.object(PredictionDocument, "from_legacy"),
        mocker.patch.object(PredictionDocument, "from_document_input"),
        mocker.patch.object(PredictionDocument, "from_inference"),
    )


@pytest.fixture
def load_prediction_folder_mocks(mocker: MockerFixture) -> LoadPredictionFolderMocks:
    return LoadPredictionFolderMocks(
        mocker.patch.object(Path, "exists"),
        mocker.patch.object(Path, "is_dir"),
        mocker.patch.object(Path, "glob"),
        mocker.patch("utils.predictions_loader._load_json_records"),
        mocker.patch("utils.predictions_loader._normalise_record"),
    )


@pytest.fixture
def list_prediction_folders_mocks(mocker: MockerFixture) -> ListPredictionFoldersMocks:
    return ListPredictionFoldersMocks(
        mocker.patch.object(Path, "exists"),
        mocker.patch.object(Path, "glob"),
        mocker.patch.object(Path, "iterdir"),
    )


@pytest.fixture
def load_prediction_file_mocks(mocker: MockerFixture) -> LoadPredictionFileMocks:
    return LoadPredictionFileMocks(
        mocker.patch("utils.predictions_loader._load_prediction_folder"),
    )


@pytest.fixture
def get_prediction_files_mocks(mocker: MockerFixture) -> GetPredictionFilesMocks:
    return GetPredictionFilesMocks(
        mocker.patch("utils.predictions_loader._load_prediction_folder"),
    )


@pytest.fixture
def sample_session() -> Session:
    return Session(
        id="foo",
        name="bar",
        schema_module="baz.qux",
        root_class="Quux",
        predictions_folder="predictions/corge",
        sample_size=1,
        selections=[],
    )


class TestLoadJsonRecords:
    @pytest.mark.parametrize(
        ("path", "text", "expected"),
        [
            (
                "foo.jsonl",
                '{"document_id": "bar1"}\n{"document_id": "bar2"}',
                [{"document_id": "bar1"}, {"document_id": "bar2"}],
            ),
            (
                "foo.json",
                '[{"document_id": "bar1"}, {"document_id": "bar2"}]',
                [{"document_id": "bar1"}, {"document_id": "bar2"}],
            ),
            (
                "foo.json",
                '{"document_id": "bar1"}',
                [{"document_id": "bar1"}],
            ),
        ],
    )
    def test_load_json_records_various_shapes_returns_list_of_records(
        self,
        load_json_records_mocks: LoadJsonRecordsMocks,
        path: str,
        text: str,
        expected: list[dict],
    ) -> None:
        load_json_records_mocks.read_text.return_value = text
        assert _load_json_records(path) == expected


class TestNormaliseRecord:
    def test_normalise_record_legacy_shape_without_own_id_uses_fallback(
        self, normalise_record_mocks: NormaliseRecordMocks
    ) -> None:
        record = {"content": "foo", "output": {"bar": "baz"}}
        result, _ = _normalise_record(record, "fallback_id")
        assert isinstance(result, Ok)
        args, _ = normalise_record_mocks.from_legacy.call_args
        assert args[0] == "fallback_id"

    def test_normalise_record_document_content_shape_uses_from_document_input(
        self, normalise_record_mocks: NormaliseRecordMocks
    ) -> None:
        record = {"document_content": "foo"}
        result, prediction = _normalise_record(record, "baz")
        assert isinstance(result, Ok)
        assert prediction is normalise_record_mocks.from_document_input.return_value
        (document,), _ = normalise_record_mocks.from_document_input.call_args
        assert document.document_id == "baz"
        assert document.document_content == "foo"

    def test_normalise_record_document_inference_shape_uses_from_inference(
        self, normalise_record_mocks: NormaliseRecordMocks
    ) -> None:
        record = {"document_inference": {"foo": "bar"}}
        result, prediction = _normalise_record(record, "baz")
        assert isinstance(result, Ok)
        assert prediction is normalise_record_mocks.from_inference.return_value
        (inference,), _ = normalise_record_mocks.from_inference.call_args
        assert inference.document_id == "baz"
        assert inference.document_inference == {"foo": "bar"}

    def test_normalise_record_unsupported_shape_returns_error(
        self, normalise_record_mocks: NormaliseRecordMocks
    ) -> None:
        result, prediction = _normalise_record({"unknown_key": "foo"}, "baz")
        assert isinstance(result, Err)
        assert result.error == "unsupported prediction shape"
        assert prediction is None
        normalise_record_mocks.from_legacy.assert_not_called()
        normalise_record_mocks.from_document_input.assert_not_called()
        normalise_record_mocks.from_inference.assert_not_called()

    def test_normalise_record_matching_shape_fails_validation_returns_error(
        self, normalise_record_mocks: NormaliseRecordMocks
    ) -> None:
        result, prediction = _normalise_record({"content": "foo"}, "baz")
        assert isinstance(result, Err)
        assert result.error == "unsupported prediction shape"
        assert prediction is None
        normalise_record_mocks.from_legacy.assert_not_called()


class TestLoadPredictionFolder:
    @pytest.fixture(autouse=True)
    def clear_cache(self) -> None:
        _load_prediction_folder.cache_clear()

    def test_load_prediction_folder_path_missing_returns_empty_dict(
        self, load_prediction_folder_mocks: LoadPredictionFolderMocks
    ) -> None:
        load_prediction_folder_mocks.exists.return_value = False
        assert _load_prediction_folder("foo") == {}
        load_prediction_folder_mocks.is_dir.assert_not_called()

    def test_load_prediction_folder_path_not_a_directory_returns_empty_dict(
        self, load_prediction_folder_mocks: LoadPredictionFolderMocks
    ) -> None:
        load_prediction_folder_mocks.exists.return_value = True
        load_prediction_folder_mocks.is_dir.return_value = False
        assert _load_prediction_folder("foo") == {}

    def test_load_prediction_folder_single_record_returns_prediction(
        self,
        load_prediction_folder_mocks: LoadPredictionFolderMocks,
        mocker: MockerFixture,
    ) -> None:
        load_prediction_folder_mocks.exists.return_value = True
        load_prediction_folder_mocks.is_dir.return_value = True
        load_prediction_folder_mocks.glob.side_effect = lambda pattern: (
            [Path("foo/bar.json")] if pattern == "*.json" else []
        )
        load_prediction_folder_mocks.load_json_records.return_value = [
            {"document_id": "baz"}
        ]
        prediction = mocker.Mock(document_id="baz")
        load_prediction_folder_mocks.normalise_record.return_value = (Ok(), prediction)
        assert _load_prediction_folder("foo") == {"baz": prediction}
        prediction.update_from.assert_not_called()

    def test_load_prediction_folder_duplicate_document_id_merges_records(
        self,
        load_prediction_folder_mocks: LoadPredictionFolderMocks,
        mocker: MockerFixture,
    ) -> None:
        load_prediction_folder_mocks.exists.return_value = True
        load_prediction_folder_mocks.is_dir.return_value = True
        load_prediction_folder_mocks.glob.side_effect = lambda pattern: (
            [Path("foo/bar.json")] if pattern == "*.json" else []
        )
        load_prediction_folder_mocks.load_json_records.return_value = [
            {"document_id": "baz"},
            {"document_id": "baz"},
        ]
        first_prediction = mocker.Mock(document_id="baz")
        second_prediction = mocker.Mock(document_id="baz")
        load_prediction_folder_mocks.normalise_record.side_effect = [
            (Ok(), first_prediction),
            (Ok(), second_prediction),
        ]
        assert _load_prediction_folder("foo") == {"baz": first_prediction}
        first_prediction.update_from.assert_called_once_with(second_prediction)

    def test_load_prediction_folder_normalise_error_raises_value_error(
        self, load_prediction_folder_mocks: LoadPredictionFolderMocks
    ) -> None:
        load_prediction_folder_mocks.exists.return_value = True
        load_prediction_folder_mocks.is_dir.return_value = True
        load_prediction_folder_mocks.glob.side_effect = lambda pattern: (
            [Path("foo/bar.json")] if pattern == "*.json" else []
        )
        load_prediction_folder_mocks.load_json_records.return_value = [
            {"document_id": "baz"}
        ]
        load_prediction_folder_mocks.normalise_record.return_value = (
            Err("bad shape"),
            None,
        )
        with pytest.raises(ValueError, match="bad shape"):
            _load_prediction_folder("foo")


class TestListPredictionFolders:
    def test_list_prediction_folders_base_dir_missing_returns_empty_list(
        self, list_prediction_folders_mocks: ListPredictionFoldersMocks
    ) -> None:
        list_prediction_folders_mocks.exists.return_value = False
        assert list_prediction_folders("predictions") == []

    def test_list_prediction_folders_root_files_returns_root_entry(
        self, list_prediction_folders_mocks: ListPredictionFoldersMocks
    ) -> None:
        list_prediction_folders_mocks.exists.return_value = True
        list_prediction_folders_mocks.glob.side_effect = lambda pattern: (
            [Path("predictions/foo.json"), Path("predictions/bar.json")]
            if pattern == "*.json"
            else []
        )
        list_prediction_folders_mocks.iterdir.return_value = []
        assert list_prediction_folders("predictions") == [
            {"name": "predictions", "path": "predictions", "num_files": 2}
        ]

    def test_list_prediction_folders_subfolders_sorted_and_filtered(
        self,
        list_prediction_folders_mocks: ListPredictionFoldersMocks,
        mocker: MockerFixture,
    ) -> None:
        list_prediction_folders_mocks.exists.return_value = True
        list_prediction_folders_mocks.glob.return_value = []
        with_files = mocker.Mock()
        with_files.name = "xyzzy_folder"
        with_files.is_dir.return_value = True
        with_files.glob.side_effect = lambda pattern: (
            [Path("predictions/xyzzy_folder/foo.json")] if pattern == "*.json" else []
        )
        without_files = mocker.Mock()
        without_files.name = "quux_folder"
        without_files.is_dir.return_value = True
        without_files.glob.return_value = []
        not_a_directory = mocker.Mock()
        not_a_directory.name = "bar_baz"
        not_a_directory.is_dir.return_value = False
        list_prediction_folders_mocks.iterdir.return_value = [
            not_a_directory,
            with_files,
            without_files,
        ]
        assert list_prediction_folders("predictions") == [
            {"name": "xyzzy_folder", "path": str(with_files), "num_files": 1}
        ]


class TestLoadPredictionFile:
    def test_load_prediction_file_found_via_folder_returns_dump(
        self, load_prediction_file_mocks: LoadPredictionFileMocks, mocker: MockerFixture
    ) -> None:
        prediction = mocker.Mock(document_id="baz")
        prediction.model_dump.return_value = {"document_id": "baz"}
        load_prediction_file_mocks.load_prediction_folder.return_value = {
            "baz": prediction
        }
        assert load_prediction_file("baz", "foo") == {"document_id": "baz"}

    def test_load_prediction_file_not_found_via_folder_raises_file_not_found(
        self, load_prediction_file_mocks: LoadPredictionFileMocks
    ) -> None:
        load_prediction_file_mocks.load_prediction_folder.return_value = {}
        with pytest.raises(FileNotFoundError):
            load_prediction_file("baz", "foo")

    def test_load_prediction_file_schema_class_valid_returns_dump(
        self, load_prediction_file_mocks: LoadPredictionFileMocks, mocker: MockerFixture
    ) -> None:
        prediction = mocker.Mock(document_id="baz", document_inference={"foo": "bar"})
        prediction.model_dump.return_value = {"document_id": "baz"}
        load_prediction_file_mocks.load_prediction_folder.return_value = {
            "baz": prediction
        }
        assert load_prediction_file("baz", "foo", SampleSchema) == {
            "document_id": "baz"
        }

    def test_load_prediction_file_schema_class_invalid_raises_value_error(
        self, load_prediction_file_mocks: LoadPredictionFileMocks, mocker: MockerFixture
    ) -> None:
        prediction = mocker.Mock(document_id="baz", document_inference={})
        load_prediction_file_mocks.load_prediction_folder.return_value = {
            "baz": prediction
        }
        with pytest.raises(ValueError, match="Schema validation failed"):
            load_prediction_file("baz", "foo", SampleSchema)


class TestValidateOutputSchema:
    def test_validate_output_schema_no_root_class_returns_false(
        self, mocker: MockerFixture
    ) -> None:
        inspector = mocker.Mock(root_class=None)
        assert _validate_output_schema({}, inspector) == (
            False,
            "No root schema class found",
        )

    def test_validate_output_schema_valid_data_returns_true(
        self, mocker: MockerFixture
    ) -> None:
        inspector = mocker.Mock(root_class=SampleSchema)
        assert _validate_output_schema({"foo": "value"}, inspector) == (True, None)

    def test_validate_output_schema_invalid_data_returns_false_with_details(
        self, mocker: MockerFixture
    ) -> None:
        inspector = mocker.Mock(root_class=SampleSchema)
        is_valid, message = _validate_output_schema({}, inspector)
        assert is_valid is False
        assert message and message.startswith("1 validation errors (first: foo - ")

    def test_validate_output_schema_unexpected_exception_returns_false_with_message(
        self, mocker: MockerFixture
    ) -> None:
        inspector = mocker.Mock(root_class=mocker.Mock(side_effect=Exception("thud")))
        assert _validate_output_schema({}, inspector) == (
            False,
            "Validation error: thud",
        )


class TestGetPredictionFiles:
    def test_get_prediction_files_no_limit_returns_all_document_ids(
        self, get_prediction_files_mocks: GetPredictionFilesMocks
    ) -> None:
        get_prediction_files_mocks.load_prediction_folder.return_value = {
            "baz": None,
            "quux": None,
        }
        assert get_prediction_files("foo") == ["baz", "quux"]

    def test_get_prediction_files_with_limit_returns_sliced_document_ids(
        self, get_prediction_files_mocks: GetPredictionFilesMocks
    ) -> None:
        get_prediction_files_mocks.load_prediction_folder.return_value = {
            "baz": None,
            "quux": None,
        }
        assert get_prediction_files("foo", 1) == ["baz"]


class TestExtractFieldValue:
    def test_extract_field_value_single_level_key_returns_value(self) -> None:
        assert extract_field_value({"foo": "bar"}, "foo") == "bar"

    def test_extract_field_value_nested_key_returns_value(self) -> None:
        assert extract_field_value({"foo": {"bar": "baz"}}, "foo.bar") == "baz"

    def test_extract_field_value_missing_key_returns_none(self) -> None:
        assert extract_field_value({"foo": {}}, "foo.bar") is None

    def test_extract_field_value_non_dict_mid_path_returns_none(self) -> None:
        assert extract_field_value({"foo": "bar"}, "foo.baz") is None


class TestValidateAndFilterFiles:
    def test_validate_and_filter_files_valid_file_is_kept(
        self,
        validate_and_filter_files_mocks: ValidateAndFilterFilesMocks,
        sample_session: Session,
    ) -> None:
        validate_and_filter_files_mocks.load_prediction_file.return_value = {
            "document_inference": {"foo": "bar"}
        }
        validate_and_filter_files_mocks.validate_output_schema.return_value = (
            True,
            None,
        )
        valid_files, excluded = validate_and_filter_files(["foobar"], sample_session)
        assert valid_files == ["foobar"]
        assert excluded == {}

    def test_validate_and_filter_files_missing_document_inference_is_excluded(
        self,
        validate_and_filter_files_mocks: ValidateAndFilterFilesMocks,
        sample_session: Session,
    ) -> None:
        validate_and_filter_files_mocks.load_prediction_file.return_value = {
            "document_inference": {}
        }
        valid_files, excluded = validate_and_filter_files(["foobar"], sample_session)
        assert valid_files == []
        assert excluded == {"foobar": "Missing 'document_inference' field"}
        validate_and_filter_files_mocks.validate_output_schema.assert_not_called()

    def test_validate_and_filter_files_schema_invalid_is_excluded(
        self,
        validate_and_filter_files_mocks: ValidateAndFilterFilesMocks,
        sample_session: Session,
    ) -> None:
        validate_and_filter_files_mocks.load_prediction_file.return_value = {
            "document_inference": {"foo": "bar"}
        }
        validate_and_filter_files_mocks.validate_output_schema.return_value = (
            False,
            "schema error",
        )
        valid_files, excluded = validate_and_filter_files(["foobar"], sample_session)
        assert valid_files == []
        assert excluded == {"foobar": "schema error"}

    def test_validate_and_filter_files_load_error_is_excluded(
        self,
        validate_and_filter_files_mocks: ValidateAndFilterFilesMocks,
        sample_session: Session,
    ) -> None:
        validate_and_filter_files_mocks.load_prediction_file.side_effect = Exception(
            "thud"
        )
        valid_files, excluded = validate_and_filter_files(["foobar"], sample_session)
        assert valid_files == []
        assert excluded == {"foobar": "Error loading file: thud"}
