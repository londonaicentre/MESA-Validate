"""
validation_ui.py - Dynamic validation UI generation for selections

Builds validation interface for each item depending on type of item
"""

import html as html_lib
import json

import streamlit as st

from utils.schema_inspector import SchemaInspector
from utils.selection_resolver import resolve_selection, selection_kind

EXCERPT_SUFFIXES = ("_desc", "_name_desc", "_summary")


def _is_excerpt_field(field_name, value):
    """Heuristic: does this value plausibly quote the source document?"""
    if not isinstance(value, str) or not value.strip():
        return False
    if field_name.endswith(EXCERPT_SUFFIXES):
        return True
    return len(value.strip()) >= 12


def _set_highlight(value):
    st.session_state["highlight_query"] = value


def _format_value(value):
    if value is None:
        return "<span class='mesa-null'>—</span>"
    if isinstance(value, (dict, list)):
        return html_lib.escape(json.dumps(value))
    return html_lib.escape(str(value))


def _field_row_html(field_name, value):
    return (
        f"<div class='mesa-row'>"
        f"<span class='mesa-label'>{html_lib.escape(str(field_name))}</span>"
        f"<span class='mesa-value'>{_format_value(value)}</span></div>"
    )


def _render_field_row(field_name, value, key_prefix):
    """
    One label/value row. Excerpt-like values get a compact locate button on
    the same row (Streamlit widgets are block-level, so a per-row column
    layout is the only way to keep the button beside its field). Label and
    value share the wide left column so neither wraps awkwardly in the narrow
    validation pane; the button sits in a slim right column.
    """
    if not _is_excerpt_field(field_name, value):
        st.markdown(_field_row_html(field_name, value), unsafe_allow_html=True)
        return

    c_text, c_btn = st.columns([5, 1], vertical_alignment="center")
    with c_text:
        st.markdown(_field_row_html(field_name, value), unsafe_allow_html=True)
    with c_btn:
        st.button(
            "🔎",
            key=f"{key_prefix}_locate_{field_name}",
            on_click=_set_highlight,
            args=(value,),
            help=f"Locate in document: {value[:80]}",
        )


def render_entity_card(item, key_prefix):
    """
    Render a dict as a fully-expanded card (label/value rows, nulls dimmed);
    excerpt-like values get an inline locate button for jump-to-source.
    """
    if not isinstance(item, dict):
        with st.container(border=True):
            st.markdown(html_lib.escape(str(item)))
        return

    with st.container(border=True):
        for field_name, value in item.items():
            _render_field_row(field_name, value, key_prefix)


def display_field_value(value, field_name="", key_prefix=""):
    """
    Display a field value with compact formatting
    """
    if value is None:
        st.markdown(
            f"<div style='color:#666; font-style:italic;'>{field_name}: Not present</div>",
            unsafe_allow_html=True,
        )
    elif isinstance(value, list):
        if not value:
            st.markdown(
                f"<div style='color:#666; font-style:italic;'>{field_name}: Empty list</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div style='font-weight:600;'>{field_name}:</div>",
                unsafe_allow_html=True,
            )
            for i, item in enumerate(value, 1):
                if isinstance(item, dict):
                    render_entity_card(
                        item, key_prefix=f"{key_prefix}_{field_name}_{i}"
                    )
                else:
                    st.markdown(
                        f"<div style='margin-left:10px;'>{i}. {item}</div>",
                        unsafe_allow_html=True,
                    )
    elif isinstance(value, dict):
        st.markdown(
            f"<div style='font-weight:600;'>{field_name}:</div>", unsafe_allow_html=True
        )
        render_entity_card(value, key_prefix=f"{key_prefix}_{field_name}")
    else:
        with st.container(border=True):
            _render_field_row(field_name, value, key_prefix)


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


def show_item_validation(
    items, key_prefix, current_value=None, show_missed_count=False
):
    """
    Show radio buttons for each item + optional missed count for list/enum items
    """
    ui_options = ["None", "Correct", "Incorrect"]

    # determine if this is single-item (binary) or multi-item (list)
    is_binary = len(items) == 1 and not show_missed_count

    if is_binary:
        item = items[0]
        is_present = is_value_present(item)

        default_index = 0
        if current_value:
            ui_value = map_storage_to_ui(current_value)
            if ui_value == "CORRECT":
                default_index = 1
            elif ui_value == "INCORRECT":
                default_index = 2

        user_choice = st.radio(
            "Validation choice",
            options=ui_options,
            index=default_index,
            key=f"{key_prefix}_item_0",
            horizontal=True,
            label_visibility="collapsed",
        )

        if user_choice == "None":
            return None
        elif user_choice == "Correct":
            return "PRESENT_CORRECT" if is_present else "ABSENT_CORRECT"
        elif user_choice == "Incorrect":
            return "PRESENT_INCORRECT" if is_present else "ABSENT_INCORRECT"

    else:
        if isinstance(current_value, dict):
            current_items = current_value.get("items", [])
            current_missed = current_value.get("missed", 0)
        else:
            current_items = []
            current_missed = 0

        item_results = []

        # only show items if there are actual items (not none placeholders)
        if items and items[0] is not None:
            for i, item in enumerate(items):
                if isinstance(item, dict):
                    render_entity_card(item, key_prefix=f"{key_prefix}_card_{i}")
                else:
                    st.markdown(f"**Item {i + 1}:** {item}")

                default_index = 0
                if i < len(current_items):
                    saved = current_items[i]
                    if saved is True:
                        default_index = 1
                    elif saved is False:
                        default_index = 2

                user_choice = st.radio(
                    "Validation choice",
                    options=ui_options,
                    index=default_index,
                    key=f"{key_prefix}_item_{i}",
                    horizontal=True,
                    label_visibility="collapsed",
                )

                # convert to storage: none -> null, correct -> true, incorrect -> false
                if user_choice == "None":
                    item_results.append(None)
                elif user_choice == "Correct":
                    item_results.append(True)
                else:
                    item_results.append(False)

        # show missed count for lists (always show, even if no items)
        missed = st.number_input(
            "Number of items missed",
            min_value=0,
            value=current_missed,
            key=f"{key_prefix}_missed",
        )

        return {"items": item_results, "missed": missed}


def generate_validation_block(
    selection, extraction_data, inspector: SchemaInspector, key_prefix, current_value=None
):
    """
    Generate validation UI for any given selection

    Args:
        selection: FieldSelection object
        extraction_data: Extracted data from prediction
        inspector: SchemaInspector instance
        key_prefix: Prefix for UI keys
        current_value: Current saved value (optional)

    Returns:
        Validation result
    """
    if not extraction_data:
        st.warning("No extraction data available")
        return None

    result = None

    try:
        if selection.selection_type in ("basemodel_class", "enum_value"):
            class_info = inspector.classes.get(selection.class_name)
            if not class_info:
                st.error(f"Class {selection.class_name} not found in schema")
                return None

        block = resolve_selection(selection, extraction_data, inspector)
        kind = selection_kind(selection, inspector)

        if selection.selection_type == "basemodel_field":
            item_key_prefix = (
                f"{key_prefix}_{selection.class_name}_{selection.field_name}"
            )
        elif selection.selection_type == "enum_value":
            item_key_prefix = (
                f"{key_prefix}_{selection.class_name}_{selection.enum_value}"
            )
        else:
            item_key_prefix = f"{key_prefix}_{selection.class_name}"

        if kind == "list":
            found_items = block["items"]
            if not found_items:
                if selection.selection_type == "enum_value":
                    st.info(
                        f"No items found with {selection.class_name} = {selection.enum_value}"
                    )
                else:
                    st.info(f"No {selection.class_name} items found in prediction")

            result = show_item_validation(
                found_items,
                key_prefix=item_key_prefix,
                current_value=current_value,
                show_missed_count=True,
            )

        else:
            value = block["value"]

            if selection.selection_type == "basemodel_class":
                if value:
                    if isinstance(value, dict):
                        render_entity_card(value, key_prefix=item_key_prefix)
                    else:
                        display_field_value(
                            value, selection.class_name, key_prefix=item_key_prefix
                        )
                else:
                    st.info(f"No {selection.class_name} data found in prediction")
            else:
                if value is not None:
                    display_field_value(
                        value, selection.field_name, key_prefix=item_key_prefix
                    )
                else:
                    st.info(f"No data found for {selection.field_name}")

            result = show_item_validation(
                [value],
                key_prefix=item_key_prefix,
                current_value=current_value,
                show_missed_count=False,
            )

    except Exception as e:
        st.error(f"Error generating validation UI: {e}")
        st.exception(e)
        return None

    return result
