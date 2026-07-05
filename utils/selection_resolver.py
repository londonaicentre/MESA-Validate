"""
selection_resolver.py - UI-free resolution of FieldSelections against extraction data

Single source of truth for what data a selection points at; used by the
Streamlit validation UI and by the packet builder.
"""

from typing import get_args, get_origin

from utils.predictions_loader import extract_field_value


def selection_title(selection):
    if selection.selection_type == "basemodel_class":
        return selection.class_name
    if selection.selection_type == "basemodel_field":
        return f"{selection.class_name}.{selection.field_name}"
    return f"{selection.class_name}.{selection.enum_value}"


def selection_kind(selection, inspector):
    """'list' selections validate item-by-item with a missed count; 'single' are binary."""
    if selection.selection_type == "enum_value":
        return "list"
    if selection.selection_type == "basemodel_class" and inspector.is_class_used_as_list_item(
        selection.class_name
    ):
        return "list"
    return "single"


def _collect_list_items(class_name, extraction_data, inspector):
    """Find every List[class_name] field in the schema and pull its items."""
    found_items = []
    for parent_class_name, parent_class_info in inspector.classes.items():
        if parent_class_info["type"] != "BaseModel":
            continue
        parent_class = parent_class_info["class"]
        for field_name, field_info in parent_class.model_fields.items():
            annotation = field_info.annotation
            origin = get_origin(annotation)
            if str(origin) == "typing.Union":
                for arg in get_args(annotation):
                    if arg is not type(None):
                        annotation = arg
                        break
            if get_origin(annotation) is list:
                args = get_args(annotation)
                if args and getattr(args[0], "__name__", None) == class_name:
                    parent_path = inspector.find_class_path(parent_class_name)
                    if parent_path:
                        items = extract_field_value(
                            extraction_data, ".".join(parent_path + [field_name])
                        )
                        if isinstance(items, list):
                            found_items.extend(items)
    return found_items


def _filter_by_enum_value(items, enum_field_name, enum_value):
    if not isinstance(items, list):
        return []
    return [
        item
        for item in items
        if isinstance(item, dict) and item.get(enum_field_name) == enum_value
    ]


def resolve_selection(selection, extraction_data, inspector):
    """
    Resolve a FieldSelection to display-ready data.

    Returns:
        {"kind": "list", "items": [...]} or {"kind": "single", "value": Any}
    """
    if selection.selection_type == "basemodel_class":
        if inspector.is_class_used_as_list_item(selection.class_name):
            return {
                "kind": "list",
                "items": _collect_list_items(
                    selection.class_name, extraction_data or {}, inspector
                ),
            }
        path = inspector.find_class_path(selection.class_name)
        value = (
            extract_field_value(extraction_data or {}, ".".join(path)) if path else None
        )
        return {"kind": "single", "value": value}

    if selection.selection_type == "basemodel_field":
        path = inspector.find_class_path(selection.class_name)
        value = (
            extract_field_value(
                extraction_data or {}, ".".join(path + [selection.field_name])
            )
            if path
            else None
        )
        return {"kind": "single", "value": value}

    if selection.selection_type == "enum_value":
        found_items = []
        for container_class_name, enum_field_name in inspector.find_enum_containers(
            selection.class_name
        ):
            container_path = inspector.find_class_path(container_class_name)
            if container_path:
                items = extract_field_value(
                    extraction_data or {}, ".".join(container_path)
                )
                found_items.extend(
                    _filter_by_enum_value(items, enum_field_name, selection.enum_value)
                )
        return {"kind": "list", "items": found_items}

    raise ValueError(f"Unknown selection_type: {selection.selection_type}")
