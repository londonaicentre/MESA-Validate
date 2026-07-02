from dataclasses import dataclass
import json
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, field_validator

from mesa_runner.adapters.io_schemas import DocumentInput

E = TypeVar("E")


class Result(Generic[E]):
    pass


@dataclass
class Ok(Result[E]):
    pass


@dataclass
class Err(Result[E]):
    error: E


class FilesystemInferenceRecord(BaseModel):
    document_id: str
    document_source: dict[str, Any] = Field(default_factory=dict)
    document_inference: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_valid: bool = True

    @field_validator("document_source", "document_inference", "metadata", mode="before")
    @classmethod
    def parse_json_string(cls, value):
        return json.loads(value) if isinstance(value, str) else value


class LegacyPredictionRecord(BaseModel):
    content: str
    output: dict[str, Any]


class PredictionDocument(DocumentInput, FilesystemInferenceRecord):
    @classmethod
    def from_document_input(cls, document):
        return cls(
            document_id=document.document_id,
            document_content=document.document_content,
            document_update_dt=document.document_update_dt,
            document_source=document.document_source or {},
        )

    @classmethod
    def from_inference(cls, inference):
        return cls(
            document_id=inference.document_id,
            document_content="",
            document_update_dt=None,
            document_source=inference.document_source,
            document_inference=inference.document_inference,
            metadata=inference.metadata,
            is_valid=inference.is_valid,
        )

    @classmethod
    def from_legacy(cls, document_id, record):
        return cls(
            document_id=document_id,
            document_content=record.content,
            document_update_dt=None,
            document_inference=record.output,
        )

    def update_from(self, record):
        # only accept real incoming data (not empty sentinels)
        for field in (
            "document_content",
            "document_update_dt",
            "document_source",
            "document_inference",
            "metadata",
        ):
            if value := getattr(record, field):
                setattr(self, field, value)
        if "is_valid" in record.model_fields_set:
            self.is_valid = record.is_valid
