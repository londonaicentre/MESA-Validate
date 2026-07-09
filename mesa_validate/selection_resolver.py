"""
selection_resolver.py - Streamlit-free resolution of validation selections

Determines which extracted item(s) a human must judge for a given
FieldSelection, and encodes/decodes the resulting judgement to and from the
storage format consumed by metrics.py. Kept free of any UI framework so it
can be shared by both the Streamlit validation_ui and other frontends (e.g.
a notebook-based reviewer).
"""

from typing import get_args, get_origin

from mesa_validate.predictions_loader import extract_field_value
from mesa_validate.schema_inspector import SchemaInspector


def is_value_present(value):
    """
    Detect if a field value is present (not null/empty)
    Returns True if value is present
    """
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    if isinstance(value, (list, dict)) and len(value) == 0:
        return False
    return True


def map_storage_to_ui(storage_value):
    """
    Convert storage format to UI display value
    UI only shows NONE/CORRECT/INCORRECT
    """
    mapping = {
        "PRESENT_CORRECT": "CORRECT",
        "ABSENT_CORRECT": "CORRECT",
        "PRESENT_INCORRECT": "INCORRECT",
        "ABSENT_INCORRECT": "INCORRECT",
        "NONE": "NONE",
        "NOT_APPLICABLE": "NOT_APPLICABLE",
    }
    return mapping.get(storage_value, "NONE")


def encode_binary_result(user_choice, is_present):
    """
    Encode a "None" | "Correct" | "Incorrect" choice to storage format

    Args:
        user_choice: UI choice string
        is_present: Whether the underlying field value is present

    Returns:
        Storage string, or None if user_choice is "None"
    """
    if user_choice == "None":
        return None
    elif user_choice == "Correct":
        return "PRESENT_CORRECT" if is_present else "ABSENT_CORRECT"
    elif user_choice == "Incorrect":
        return "PRESENT_INCORRECT" if is_present else "ABSENT_INCORRECT"


def encode_list_item_result(user_choice):
    """
    Encode a "None" | "Correct" | "Incorrect" choice for a single list item

    Returns:
        True (correct), False (incorrect), or None (not evaluated)
    """
    # convert to storage: none -> null, correct -> true, incorrect -> false
    if user_choice == "None":
        return None
    elif user_choice == "Correct":
        return True
    else:
        return False


def resolve_selection(selection, extraction_data, inspector: SchemaInspector):
    """
    Determine the extracted item(s) a human must judge for a selection

    Args:
        selection: FieldSelection to resolve
        extraction_data: Extracted data from a prediction document
        inspector: SchemaInspector for the session's schema

    Returns:
        Dict with the items to judge and how to judge them:
        {
            "items": [...],
            "is_list": bool,
            "path_found": bool  # False if the selection's class/field isn't reachable from the root
        }

    Raises:
        ValueError: If the selection references a class/enum not in the schema
    """
    if selection.selection_type == "basemodel_class":
        return _resolve_basemodel_class(selection, extraction_data, inspector)
    elif selection.selection_type == "basemodel_field":
        return _resolve_basemodel_field(selection, extraction_data, inspector)
    elif selection.selection_type == "enum_value":
        return _resolve_enum_value(selection, extraction_data, inspector)
    raise ValueError(f"Unknown selection type: {selection.selection_type}")


def _resolve_basemodel_class(selection, extraction_data, inspector):
    is_list_item = inspector.is_class_used_as_list_item(selection.class_name)

    class_info = inspector.classes.get(selection.class_name)
    if not class_info:
        raise ValueError(f"Class {selection.class_name} not found in schema")

    if is_list_item:
        found_items = _find_list_items_for_class(
            selection.class_name, extraction_data, inspector
        )
        return {"items": found_items, "is_list": True, "path_found": True}
    else:
        path = inspector.find_class_path(selection.class_name)
        if path is not None:
            class_data = extract_field_value(extraction_data, ".".join(path))
            path_found = True
        else:
            class_data = None
            path_found = False

        return {"items": [class_data], "is_list": False, "path_found": path_found}


def _resolve_basemodel_field(selection, extraction_data, inspector):
    path = inspector.find_class_path(selection.class_name)
    if path is not None:
        field_path = ".".join(path + [selection.field_name])
        field_value = extract_field_value(extraction_data, field_path)
        path_found = True
    else:
        field_value = None
        path_found = False

    return {"items": [field_value], "is_list": False, "path_found": path_found}


def _resolve_enum_value(selection, extraction_data, inspector):
    enum_class = inspector.classes.get(selection.class_name, {}).get("class")
    if not enum_class:
        raise ValueError(f"Enum {selection.class_name} not found")

    containers = inspector.find_enum_containers(selection.class_name)
    found_items = []

    for container_class_name, enum_field_name in containers:
        container_path = inspector.find_class_path(container_class_name)
        if container_path:
            items = extract_field_value(extraction_data, ".".join(container_path))
            if isinstance(items, list):
                filtered = _filter_by_enum_value(
                    items, enum_field_name, selection.enum_value
                )
                found_items.extend(filtered)

    return {"items": found_items, "is_list": True, "path_found": True}


def _find_list_items_for_class(class_name, extraction_data, inspector):
    classes = inspector.classes
    found_items = []

    for parent_class_name, parent_class_info in classes.items():
        if parent_class_info["type"] != "BaseModel":
            continue

        parent_class = parent_class_info["class"]
        for field_name, field_info in parent_class.model_fields.items():
            annotation = field_info.annotation

            origin = get_origin(annotation)
            if str(origin) == "typing.Union":
                args = get_args(annotation)
                for arg in args:
                    if arg is not type(None):
                        annotation = arg
                        break

            origin = get_origin(annotation)
            if origin is list:
                args = get_args(annotation)
                if (
                    args
                    and hasattr(args[0], "__name__")
                    and args[0].__name__ == class_name
                ):
                    parent_path = inspector.find_class_path(parent_class_name)
                    if parent_path is not None:
                        list_path = ".".join(parent_path + [field_name])
                        items = extract_field_value(extraction_data, list_path)
                        if isinstance(items, list):
                            found_items.extend(items)

    return found_items


def _filter_by_enum_value(items, enum_field_name, enum_value):
    if not isinstance(items, list):
        return []

    filtered = []
    for item in items:
        if isinstance(item, dict) and item.get(enum_field_name) == enum_value:
            filtered.append(item)

    return filtered
