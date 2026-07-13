"""
glossary.py - Plain-English one-line summaries for schema sections

Validators may not know what a class like ``ContextSummary`` or a field like
``topography`` means. This module resolves a short, human-friendly summary for
any selection or nested field using, in order:

1. a curated ``glossary/<schema_module>.yaml`` override (flat keys:
   ``ClassName``, ``ClassName.field``, ``EnumClass.value``, or a bare field name);
2. the schema's own ``Field(description=...)`` (first sentence, LLM cruft stripped);
3. for enum values only, a humanised version of the value.

The glossary file is optional; without it the app falls back to (2)/(3).
"""

import re
from pathlib import Path
from typing import get_args, get_origin

import yaml

GLOSSARY_DIR = Path("glossary")


def load_glossary(schema_module, glossary_dir=GLOSSARY_DIR):
    """Load the flat glossary dict for a schema module ({} if none/invalid)."""
    path = Path(glossary_dir) / f"{schema_module}.yaml"
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _clean(desc):
    """First sentence of a Field description, with trailing LLM instructions removed."""
    if not desc:
        return None
    # drop "... Use OTHER where ..." style instructions aimed at the model
    text = re.split(r"\.\s+Use\b", desc.strip())[0].strip()
    if text and not text.endswith((".", "!", "?", ")")):
        text += "."
    return text or None


def _humanize(name):
    """CamelCase / snake_case identifier -> readable sentence fragment."""
    spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", str(name)).replace("_", " ")
    spaced = " ".join(spaced.split())
    return spaced[:1].upper() + spaced[1:] if spaced else str(name)


def _iter_types(annotation):
    origin = get_origin(annotation)
    if origin is not None:
        for arg in get_args(annotation):
            if arg is type(None):
                continue
            yield from _iter_types(arg)
    else:
        yield annotation


def _parent_field_description(class_name, inspector):
    """Description of any field whose (unwrapped) type is this class."""
    for _, info in inspector.classes.items():
        if info["type"] != "BaseModel":
            continue
        for _, field_info in info["class"].model_fields.items():
            for t in _iter_types(field_info.annotation):
                if getattr(t, "__name__", None) == class_name and field_info.description:
                    return field_info.description
    return None


def _field_description(class_name, field_name, inspector):
    info = inspector.classes.get(class_name)
    if not info or info["type"] != "BaseModel":
        return None
    field_info = info["class"].model_fields.get(field_name)
    return field_info.description if field_info else None


def _field_description_by_name(field_name, inspector):
    for _, info in inspector.classes.items():
        if info["type"] != "BaseModel":
            continue
        field_info = info["class"].model_fields.get(field_name)
        if field_info and field_info.description:
            return field_info.description
    return None


def describe_class(class_name, inspector, glossary):
    if class_name in glossary:
        return glossary[class_name]
    return _clean(_parent_field_description(class_name, inspector))


def describe_field_by_name(field_name, inspector, glossary):
    """Summary for a nested sub-object heading, keyed only by field name."""
    if field_name in glossary:
        return glossary[field_name]
    return _clean(_field_description_by_name(field_name, inspector))


def describe_field(class_name, field_name, inspector, glossary):
    key = f"{class_name}.{field_name}"
    if key in glossary:
        return glossary[key]
    return _clean(_field_description(class_name, field_name, inspector))


def describe_enum_value(enum_class_name, value, glossary):
    key = f"{enum_class_name}.{value}"
    if key in glossary:
        return glossary[key]
    return _humanize(value)


def enum_field_options(class_name, field_name, inspector, glossary):
    """Allowed values (with optional glossary descriptions) for an enum-typed
    field, so the validation UI can reveal the permitted set.

    Returns ``{"enum_class": str, "values": [{"value": str, "desc": str|None}]}``
    or ``None`` when the field is not an enum. ``desc`` is the curated glossary
    entry for that value, or ``None`` when none exists (name-only display).
    """
    meta = inspector.get_class_fields(class_name).get(field_name)
    if not meta or not meta.get("is_enum"):
        return None
    enum_class = meta.get("type")
    info = inspector.classes.get(enum_class)
    if not info or info.get("type") != "Enum":
        return None
    values = [
        {"value": v, "desc": glossary.get(f"{enum_class}.{v}")}
        for v in (info.get("values") or [])
    ]
    return {"enum_class": enum_class, "values": values}


def describe_selection(selection, inspector, glossary):
    """One-line summary for a FieldSelection, or None if nothing sensible exists."""
    if selection.selection_type == "basemodel_class":
        return describe_class(selection.class_name, inspector, glossary)
    if selection.selection_type == "basemodel_field":
        return describe_field(
            selection.class_name, selection.field_name, inspector, glossary
        )
    if selection.selection_type == "enum_value":
        return describe_enum_value(
            selection.class_name, selection.enum_value, glossary
        )
    return None


def starter_glossary(inspector):
    """
    Auto-derived starter entries for every class and field in a schema, so a
    coordinator can seed glossary/<module>.yaml and then edit it rather than
    starting from a blank file.
    """
    entries = {}
    for class_name, info in sorted(inspector.classes.items()):
        if info["type"] != "BaseModel":
            continue
        entries[class_name] = describe_class(class_name, inspector, {}) or _humanize(
            class_name
        )
        for field_name in info["class"].model_fields:
            desc = _clean(_field_description(class_name, field_name, inspector))
            entries[f"{class_name}.{field_name}"] = desc or _humanize(field_name)
    return entries
