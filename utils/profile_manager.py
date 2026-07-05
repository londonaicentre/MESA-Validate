"""
profile_manager.py - Save/load reusable field-selection profiles

A profile is a named, schema-scoped list of FieldSelections stored as JSON
in profiles/. Loading validates each selection against the live schema.
"""

import json
import re
from pathlib import Path

from utils.models import FieldSelection
from utils.selection_resolver import selection_title

PROFILES_DIR = Path("profiles")


def _slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not slug:
        raise ValueError(f"Profile name '{name}' has no usable characters")
    return slug


def list_profiles(schema_module=None, profiles_dir=PROFILES_DIR):
    profiles = []
    if not Path(profiles_dir).exists():
        return profiles
    for path in sorted(Path(profiles_dir).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profiles.append(
                {
                    "name": data["name"],
                    "schema_module": data["schema_module"],
                    "path": path,
                    "num_selections": len(data.get("selections", [])),
                }
            )
        except (json.JSONDecodeError, KeyError):
            continue
    if schema_module is not None:
        profiles = [p for p in profiles if p["schema_module"] == schema_module]
    return profiles


def save_profile(name, schema_module, selections, profiles_dir=PROFILES_DIR):
    profiles_dir = Path(profiles_dir)
    profiles_dir.mkdir(parents=True, exist_ok=True)
    path = profiles_dir / f"{_slugify(name)}.json"
    if path.exists():
        raise FileExistsError(f"A profile named '{name}' already exists")
    payload = {
        "name": name,
        "schema_module": schema_module,
        "selections": [s.model_dump() for s in selections],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _selection_is_valid(selection, inspector):
    class_info = inspector.classes.get(selection.class_name)
    if not class_info:
        return False
    if selection.selection_type == "basemodel_class":
        return class_info["type"] == "BaseModel"
    if selection.selection_type == "basemodel_field":
        return (
            class_info["type"] == "BaseModel"
            and selection.field_name in class_info["fields"]
        )
    if selection.selection_type == "enum_value":
        return (
            class_info["type"] == "Enum"
            and selection.enum_value in class_info["values"]
        )
    return False


def load_profile(path, inspector):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    valid, skipped = [], []
    for raw in data.get("selections", []):
        selection = FieldSelection(**raw)
        if _selection_is_valid(selection, inspector):
            valid.append(selection)
        else:
            skipped.append(selection_title(selection))
    return valid, skipped
