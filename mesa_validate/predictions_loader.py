"""
predictions_loader.py - Prediction file loading and validation
"""

import json
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mesa_runner.adapters.io_schemas import DocumentInput
from pydantic import BaseModel, ValidationError

from mesa_validate.types import (
    Err,
    FilesystemInferenceRecord,
    LegacyPredictionRecord,
    Ok,
    PredictionDocument,
)

if TYPE_CHECKING:
    from mesa_validate.models import Session
    from mesa_validate.schema_inspector import SchemaInspector


def _load_json_records(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines()]
    data = json.loads(text)
    return data if isinstance(data, list) else [data]


def _normalise_record(
    record: dict[str, Any], document_id: str
) -> tuple[Ok, PredictionDocument] | tuple[Err[str], None]:
    document_id = str(record.get("document_id") or document_id)
    try:
        if "content" in record or "output" in record:
            return (
                Ok(),
                PredictionDocument.from_legacy(
                    document_id, LegacyPredictionRecord.model_validate(record)
                ),
            )
        elif "document_content" in record:
            return (
                Ok(),
                PredictionDocument.from_document_input(
                    DocumentInput.model_validate(
                        record
                        | {
                            "document_id": document_id,
                            "document_update_dt": record.get("document_update_dt"),
                        }
                    )
                ),
            )
        elif "document_inference" in record:
            return Ok(), PredictionDocument.from_inference(
                FilesystemInferenceRecord.model_validate(
                    {
                        "document_id": document_id,
                        "document_source": record.get("document_source", {}),
                        "document_inference": record["document_inference"],
                        "metadata": record.get("metadata", {}),
                        "is_valid": record.get("is_valid", True),
                    }
                )
            )
    except ValidationError:
        pass
    return Err("unsupported prediction shape"), None


@cache
def _load_prediction_folder(folder_path: str) -> dict[str, PredictionDocument]:
    path = Path(folder_path)
    if not path.exists() or not path.is_dir():
        return {}

    predictions = {}
    for file_path in sorted([*path.glob("*.json"), *path.glob("*.jsonl")]):
        records = _load_json_records(file_path)
        for record in records:
            # pass file path as id for legacy documents
            result, prediction = _normalise_record(record, str(file_path))
            if isinstance(result, Err) or prediction is None:
                raise ValueError(
                    f"{file_path}: {result.error if isinstance(result, Err) else 'unknown error'}"
                )
            # if id matches one stored but incoming record differs, merge
            stored = predictions.setdefault(prediction.document_id, prediction)
            if stored is not prediction:
                stored.update_from(prediction)
    return predictions


def list_prediction_folders(
    base_dir: str = "predictions",
) -> list[dict[str, str | int]]:
    """
    List all subdirectories in the predictions folder.

    Returns list of dicts with 'name', 'path', and 'num_files'.
    """
    base_path = Path(base_dir)

    if not base_path.exists():
        return []

    folders = []
    json_files_in_root = [*base_path.glob("*.json"), *base_path.glob("*.jsonl")]
    if json_files_in_root:
        folders.append(
            {
                "name": base_dir,
                "path": str(base_path),
                "num_files": len(json_files_in_root),
            }
        )

    for folder in base_path.iterdir():
        if folder.is_dir():
            json_files = [*folder.glob("*.json"), *folder.glob("*.jsonl")]
            if json_files:
                folders.append(
                    {
                        "name": folder.name,
                        "path": str(folder),
                        "num_files": len(json_files),
                    }
                )

    return sorted(folders, key=lambda f: f["name"])


def load_prediction_file(
    document_id: str,
    folder_path: str,
    schema_class: type[BaseModel] | None = None,
) -> dict[str, Any]:
    """
    Load a prediction JSON file and optionally validate against a schema.
    """
    data = _load_prediction_folder(folder_path).get(document_id)
    if data is None:
        raise FileNotFoundError(f"Prediction file not found for {document_id}")

    if schema_class is not None:
        try:
            schema_class(**data.document_inference)
        except ValidationError as e:
            raise ValueError(f"Schema validation failed for {document_id}: {e}")

    return data.model_dump()


def _validate_output_schema(
    output_data: dict[str, Any], inspector: "SchemaInspector"
) -> tuple[bool, str | None]:
    """
    Validate output data against the root schema class
    """
    try:
        root_class = inspector.root_class

        if root_class is None:
            return False, "No root schema class found"

        root_class(**output_data)
        return True, None

    except ValidationError as e:
        error_count = len(e.errors())
        first_error = e.errors()[0] if e.errors() else {}
        field = ".".join(str(x) for x in first_error.get("loc", []))
        msg = first_error.get("msg", "Unknown error")
        return False, f"{error_count} validation errors (first: {field} - {msg})"
    except Exception as e:
        return False, f"Validation error: {e}"


def get_prediction_files(folder_path: str, limit: int | None = None) -> list[str]:
    """
    Get list of prediction files in a folder
    """
    files = list(_load_prediction_folder(folder_path))

    if limit is not None:
        files = files[:limit]

    return files


def extract_field_value(data: dict[str, Any], field_path: str) -> Any:
    """
    Extract a field value from nested dictionary using dot notation
    """
    if not field_path:
        return data

    current = data
    for part in field_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def validate_and_filter_files(
    files: list[str], session: "Session"
) -> tuple[list[str], dict[str, str]]:
    """
    Validate files against schema and filter out invalid ones
    """
    from mesa_validate.schema_inspector import SchemaInspector

    inspector = SchemaInspector(session.schema_module, session.root_class)
    valid_files = []
    excluded = {}

    for file_path in files:
        try:
            data = load_prediction_file(file_path, session.predictions_folder)
            if data.get("document_inference") == {}:
                excluded[file_path] = "Missing 'document_inference' field"
                continue

            is_valid, error_msg = _validate_output_schema(
                data["document_inference"], inspector
            )
            if not is_valid:
                excluded[file_path] = error_msg or ""
            else:
                valid_files.append(file_path)
        except Exception as e:
            excluded[file_path] = f"Error loading file: {e}"

    return valid_files, excluded
