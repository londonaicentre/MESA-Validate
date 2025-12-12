"""
predictions_loader.py - Prediction file loading and validation
"""

import json
from pathlib import Path

from pydantic import ValidationError


def list_prediction_folders(base_dir="predictions"):
    """
    List all subdirectories in the predictions folder.

    Returns list of dicts with 'name', 'path', and 'num_files'.
    """
    base_path = Path(base_dir)

    if not base_path.exists():
        return []

    folders = []

    json_files_in_root = list(base_path.glob("*.json"))
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
            json_files = list(folder.glob("*.json"))
            if json_files:
                folders.append(
                    {
                        "name": folder.name,
                        "path": str(folder),
                        "num_files": len(json_files),
                    }
                )

    return sorted(folders, key=lambda f: f["name"])


def load_prediction_file(file_path, schema_class=None):
    """
    Load a prediction JSON file and optionally validate against a schema.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Prediction file not found: {file_path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {file_path}: {e}")
    except UnicodeDecodeError as e:
        raise ValueError(f"Encoding error in {file_path}: {e}")

    if schema_class is not None:
        try:
            if "output" in data:
                schema_class(**data["output"])
            else:
                schema_class(**data)
        except ValidationError as e:
            raise ValueError(f"Schema validation failed for {file_path}: {e}")

    return data


def validate_output_schema(output_data, inspector):
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


def get_prediction_files(folder_path, limit=None):
    """
    Get list of prediction file paths in a folder
    """
    path = Path(folder_path)

    if not path.exists() or not path.is_dir():
        return []

    files = [str(f) for f in path.glob("*.json")]
    files.sort()

    if limit is not None:
        files = files[:limit]

    return files


def extract_field_value(data, field_path):
    """
    Extract a field value from nested dictionary using dot notation
    """
    parts = field_path.split(".")
    current = data

    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None

    return current


def validate_and_filter_files(files, session):
    """
    Validate files against schema and filter out invalid ones
    """
    from utils.schema_inspector import SchemaInspector

    inspector = SchemaInspector(session.schema_module, session.root_class)
    valid_files = []
    excluded = {}

    for file_path in files:
        try:
            data = load_prediction_file(file_path)
            if "output" not in data:
                excluded[file_path] = "Missing 'output' field"
                continue

            is_valid, error_msg = validate_output_schema(data["output"], inspector)
            if not is_valid:
                excluded[file_path] = error_msg
            else:
                valid_files.append(file_path)
        except Exception as e:
            excluded[file_path] = f"Error loading file: {e}"

    return valid_files, excluded
