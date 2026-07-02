from datetime import datetime

import pytest
from mesa_runner.adapters.io_schemas import DocumentInput

from utils.types import (
    FilesystemInferenceRecord,
    LegacyPredictionRecord,
    PredictionDocument,
)


class TestFilesystemInferenceRecord:
    def test_filesystem_inference_record_omitted_fields_use_defaults(self) -> None:
        record = FilesystemInferenceRecord(document_id="foo")
        assert record.document_source == {}
        assert record.document_inference == {}
        assert record.metadata == {}
        assert record.is_valid is True

    @pytest.mark.parametrize(
        "field", ["document_source", "document_inference", "metadata"]
    )
    def test_filesystem_inference_record_json_string_field_is_parsed(
        self, field: str
    ) -> None:
        record = FilesystemInferenceRecord.model_validate(
            {"document_id": "foo", field: '{"foo": "bar"}'}
        )
        assert getattr(record, field) == {"foo": "bar"}

    @pytest.mark.parametrize(
        "field", ["document_source", "document_inference", "metadata"]
    )
    def test_filesystem_inference_record_dict_field_is_passed_through(
        self, field: str
    ) -> None:
        record = FilesystemInferenceRecord.model_validate(
            {"document_id": "foo", field: {"foo": "bar"}}
        )
        assert getattr(record, field) == {"foo": "bar"}


class TestFromDocumentInput:
    def test_from_document_input_with_source_keeps_fields(self) -> None:
        document = DocumentInput(
            document_id="foo",
            document_content="bar",
            document_update_dt=None,
            document_source={"foo": "bar"},
        )
        prediction = PredictionDocument.from_document_input(document)
        assert prediction.document_id == "foo"
        assert prediction.document_content == "bar"
        assert prediction.document_update_dt is None
        assert prediction.document_source == {"foo": "bar"}
        assert prediction.document_inference == {}
        assert prediction.metadata == {}
        assert prediction.is_valid is True

    def test_from_document_input_without_source_defaults_to_empty_dict(self) -> None:
        document = DocumentInput(
            document_id="foo",
            document_content="bar",
            document_update_dt=None,
            document_source=None,
        )
        prediction = PredictionDocument.from_document_input(document)
        assert prediction.document_source == {}


class TestFromInference:
    def test_from_inference_maps_all_fields(self) -> None:
        inference = FilesystemInferenceRecord(
            document_id="foo",
            document_source={"foo": "bar"},
            document_inference={"baz": "qux"},
            metadata={"model": "xyzzy"},
            is_valid=False,
        )
        prediction = PredictionDocument.from_inference(inference)
        assert prediction.document_id == "foo"
        assert prediction.document_content == ""
        assert prediction.document_update_dt is None
        assert prediction.document_source == {"foo": "bar"}
        assert prediction.document_inference == {"baz": "qux"}
        assert prediction.metadata == {"model": "xyzzy"}
        assert prediction.is_valid is False


class TestFromLegacy:
    def test_from_legacy_maps_content_and_inference(self) -> None:
        record = LegacyPredictionRecord(content="bar", output={"foo": "bar"})

        prediction = PredictionDocument.from_legacy("foo", record)

        assert prediction.document_id == "foo"
        assert prediction.document_content == "bar"
        assert prediction.document_update_dt is None
        assert prediction.document_inference == {"foo": "bar"}
        assert prediction.document_source == {}
        assert prediction.metadata == {}
        assert prediction.is_valid is True


class TestUpdateFrom:
    @staticmethod
    def _base() -> PredictionDocument:
        return PredictionDocument(
            document_id="foo",
            document_content="foobar",
            document_update_dt=None,
            document_source={"base": "source"},
            document_inference={"base": "inference"},
            metadata={"base": "metadata"},
            is_valid=True,
        )

    def test_update_from_document_content_truthy_overwrites(self) -> None:
        prediction = self._base()
        record = PredictionDocument(
            document_id="foo", document_content="foobar", document_update_dt=None
        )
        prediction.update_from(record)
        assert prediction.document_content == "foobar"

    def test_update_from_document_content_falsy_is_kept(self) -> None:
        prediction = self._base()
        record = PredictionDocument(
            document_id="foo", document_content="", document_update_dt=None
        )
        prediction.update_from(record)
        assert prediction.document_content == "foobar"

    def test_update_from_document_update_dt_present_overwrites(self) -> None:
        prediction = self._base()
        new_update_dt = datetime(2026, 1, 1)
        record = PredictionDocument(
            document_id="foo", document_content="", document_update_dt=new_update_dt
        )
        prediction.update_from(record)
        assert prediction.document_update_dt == new_update_dt

    def test_update_from_document_update_dt_none_is_kept(self) -> None:
        prediction = self._base()
        prediction.document_update_dt = datetime(2025, 1, 1)
        record = PredictionDocument(
            document_id="foo", document_content="", document_update_dt=None
        )
        prediction.update_from(record)
        assert prediction.document_update_dt == datetime(2025, 1, 1)

    @pytest.mark.parametrize(
        "field", ["document_source", "document_inference", "metadata"]
    )
    def test_update_from_dict_field_nonempty_overwrites(self, field: str) -> None:
        prediction = self._base()
        record = PredictionDocument.model_validate(
            {
                "document_id": "foo",
                "document_content": "",
                "document_update_dt": None,
                field: {"foo": "bar"},
            }
        )
        prediction.update_from(record)
        assert getattr(prediction, field) == {"foo": "bar"}

    @pytest.mark.parametrize(
        "field", ["document_source", "document_inference", "metadata"]
    )
    def test_update_from_dict_field_empty_is_kept(self, field: str) -> None:
        prediction = self._base()
        record = PredictionDocument.model_validate(
            {
                "document_id": "foo",
                "document_content": "",
                "document_update_dt": None,
                field: {},
            }
        )
        prediction.update_from(record)
        assert getattr(prediction, field) == {"base": field.split("_")[-1]}

    @pytest.mark.parametrize(
        "field", ["document_source", "document_inference", "metadata"]
    )
    def test_update_from_dict_field_left_unset_is_kept(self, field: str) -> None:
        prediction = self._base()
        expected = getattr(prediction, field)
        record = PredictionDocument(
            document_id="foo", document_content="", document_update_dt=None
        )
        prediction.update_from(record)
        assert getattr(prediction, field) == expected

    def test_update_from_is_valid_explicitly_set_false_overwrites_true(self) -> None:
        prediction = self._base()
        record = PredictionDocument(
            document_id="foo",
            document_content="",
            document_update_dt=None,
            is_valid=False,
        )
        prediction.update_from(record)
        assert prediction.is_valid is False

    def test_update_from_is_valid_left_unset_is_kept(self) -> None:
        prediction = self._base()
        prediction.is_valid = False
        record = PredictionDocument(
            document_id="foo", document_content="", document_update_dt=None
        )
        prediction.update_from(record)
        assert prediction.is_valid is False
