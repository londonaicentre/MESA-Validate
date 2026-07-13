"""
validation_ui.py - Dynamic validation UI generation for selections

Builds validation interface for each item depending on type of item
"""

import html as html_lib

import streamlit as st

from utils.glossary import describe_class, describe_field_by_name
from utils.validation_plan import group_rollup, resolve_target

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
    return html_lib.escape(str(value))


def _field_row_html(field_name, value):
    return (
        f"<div class='mesa-row'>"
        f"<span class='mesa-label'>{html_lib.escape(str(field_name))}</span>"
        f"<span class='mesa-value'>{_format_value(value)}</span></div>"
    )


def _render_scalar_field(field_name, value, key_prefix):
    """
    One label/value row. Excerpt-like values get a compact locate button on
    the same row (Streamlit widgets are block-level, so a per-row column
    layout is the only way to keep the button beside its field). Label and
    value share the wide left column so neither wraps awkwardly in the narrow
    validation pane; the button sits in a slim right column.
    """
    # Every row uses the same [text, button] geometry so values line up whether
    # or not the row carries a locate button; the button cell stays empty when
    # the value is not an excerpt.
    c_text, c_btn = st.columns([6, 1], vertical_alignment="center")
    with c_text:
        st.markdown(_field_row_html(field_name, value), unsafe_allow_html=True)
    if _is_excerpt_field(field_name, value):
        with c_btn:
            st.button(
                "🔎",
                key=f"{key_prefix}_locate_{field_name}",
                on_click=_set_highlight,
                args=(value,),
                help=f"Locate in document: {value[:80]}",
            )


def _nested_heading(field_name, count=None, describe_heading=None):
    suffix = f" ({count})" if count is not None else ""
    st.markdown(
        f"<div class='mesa-nested-label'>{html_lib.escape(str(field_name))}{suffix}</div>",
        unsafe_allow_html=True,
    )
    if describe_heading:
        summary = describe_heading(field_name)
        if summary:
            st.caption(summary)


def _render_field(field_name, value, key_prefix, describe_heading=None):
    """
    Render one field of an entity, recursing into nested objects and lists of
    objects so nothing is shown as raw JSON.
    """
    # nested object -> heading + its own bordered card
    if isinstance(value, dict) and value:
        _nested_heading(field_name, describe_heading=describe_heading)
        with st.container(border=True):
            for sub_name, sub_value in value.items():
                _render_field(
                    sub_name, sub_value, f"{key_prefix}_{field_name}", describe_heading
                )
        return

    # list of objects -> heading + one bordered card per item
    if isinstance(value, list) and value and all(isinstance(x, dict) for x in value):
        _nested_heading(field_name, count=len(value), describe_heading=describe_heading)
        for i, item in enumerate(value):
            with st.container(border=True):
                for sub_name, sub_value in item.items():
                    _render_field(
                        sub_name,
                        sub_value,
                        f"{key_prefix}_{field_name}_{i}",
                        describe_heading,
                    )
        return

    # list of scalars -> single joined row
    if isinstance(value, list) and value:
        _render_scalar_field(
            field_name, ", ".join(str(x) for x in value), key_prefix
        )
        return

    # scalar, None, or empty container (shown as an em dash)
    if isinstance(value, (dict, list)):
        value = None
    _render_scalar_field(field_name, value, key_prefix)


def render_entity_card(item, key_prefix, describe_heading=None):
    """
    Render a dict as a fully-expanded card (label/value rows, nulls dimmed,
    nested objects as nested cards); excerpt-like values get an inline locate
    button for jump-to-source. describe_heading(field_name) optionally supplies
    a one-line summary shown under nested sub-object headings.
    """
    if not isinstance(item, dict):
        with st.container(border=True):
            st.markdown(html_lib.escape(str(item)))
        return

    with st.container(border=True):
        for field_name, value in item.items():
            _render_field(field_name, value, key_prefix, describe_heading)


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


# --- Grouped, per-field validation UI (validation plan driven) -------------


def toggle_to_storage(choice, is_present):
    """Map a ✓/✗/None choice + presence to a storage verdict (or None)."""
    if choice == "correct":
        return "PRESENT_CORRECT" if is_present else "ABSENT_CORRECT"
    if choice == "incorrect":
        return "PRESENT_INCORRECT" if is_present else "ABSENT_INCORRECT"
    return None


def storage_to_choice(stored):
    """Inverse: storage verdict -> 'correct' | 'incorrect' | None."""
    if isinstance(stored, str) and stored.endswith("_CORRECT"):
        return "correct"
    if isinstance(stored, str) and stored.endswith("_INCORRECT"):
        return "incorrect"
    return None


def bulk_apply(choices, verdict):
    """Block-level bulk verdict rule (shared by Streamlit and the packet UI).

    ``choices`` maps a field key to its current choice ('correct' | 'incorrect'
    | None). Returns a NEW dict:
      * verdict is None -> clear: every field back to unreviewed (None).
      * verdict is 'correct'/'incorrect' -> fill only fields that are currently
        unreviewed (None); already-marked fields are left untouched.
    """
    if verdict is None:
        return {k: None for k in choices}
    return {k: (verdict if cur is None else cur) for k, cur in choices.items()}


def _is_nested_value(value):
    """A nested object or list-of-objects that must be rendered recursively
    rather than stringified into a single row."""
    if isinstance(value, dict) and value:
        return True
    if isinstance(value, list) and value and any(isinstance(x, dict) for x in value):
        return True
    return False


def render_leaf_toggle(target, resolved, key_prefix, stored):
    """
    One label/value row (+ 🔎 locate button for excerpt-like values) with a
    compact ✓/✗ toggle pair. Nested BaseModel values (a non-list object field
    selected on its own) are rendered as a full-width card instead of raw JSON,
    with the toggle on its own row below. Untouched = unreviewed; clicking the
    lit icon clears back to unreviewed. Returns the storage verdict (or None).
    """
    value = resolved["value"]
    is_present = is_value_present(value)
    choice = storage_to_choice(stored)

    nested = _is_nested_value(value)
    if nested:
        # Full-width recursive render (heading + bordered card), then a
        # toggle-only row below -- mirrors render_list_target's item layout.
        _render_field(target.field_name, value, key_prefix)
        c_text, c_ok, c_no = st.columns([6, 1, 1], vertical_alignment="center")
        with c_text:
            st.markdown("<span class='mesa-toggle-row'></span>", unsafe_allow_html=True)
    else:
        c_text, c_ok, c_no = st.columns([6, 1, 1], vertical_alignment="center")
        with c_text:
            st.markdown(
                f"<span class='mesa-toggle-row'></span>{_field_row_html(target.field_name, value)}",
                unsafe_allow_html=True,
            )
            if _is_excerpt_field(target.field_name, value):
                st.button(
                    "🔎",
                    key=f"{key_prefix}_locate",
                    on_click=_set_highlight,
                    args=(value,),
                    help=f"Locate: {str(value)[:80]}",
                )

    def _toggle(new_choice):
        # clicking the lit icon clears back to unreviewed
        st.session_state[f"{key_prefix}_choice"] = (
            None
            if st.session_state.get(f"{key_prefix}_choice") == new_choice
            else new_choice
        )

    if f"{key_prefix}_choice" not in st.session_state:
        st.session_state[f"{key_prefix}_choice"] = choice

    with c_ok:
        st.button(
            "✓",
            key=f"{key_prefix}_ok",
            type="primary" if st.session_state[f"{key_prefix}_choice"] == "correct" else "secondary",
            on_click=_toggle,
            args=("correct",),
        )
    with c_no:
        st.button(
            "✗",
            key=f"{key_prefix}_no",
            type="primary" if st.session_state[f"{key_prefix}_choice"] == "incorrect" else "secondary",
            on_click=_toggle,
            args=("incorrect",),
        )

    return toggle_to_storage(st.session_state[f"{key_prefix}_choice"], is_present)


def render_list_target(target, resolved, key_prefix, stored):
    """
    Per-item ✓/✗ toggle + a "missed" number input, for list/enum targets.
    Mirrors the (now retired) radio-based logic in ``show_item_validation``
    but stores True/False/None per item via the same lit-icon-clears toggle
    used by ``render_leaf_toggle``. Storage shape is unchanged:
    ``{"items": [true|false|null, ...], "missed": int}``.
    """
    items = resolved.get("items", []) if isinstance(resolved, dict) else []
    stored = stored if isinstance(stored, dict) else {}
    current_items = stored.get("items", [])
    current_missed = stored.get("missed", 0)

    item_results = []

    for i, item in enumerate(items):
        item_key = f"{key_prefix}_item_{i}"
        saved = current_items[i] if i < len(current_items) else None
        saved_choice = "correct" if saved is True else "incorrect" if saved is False else None

        if isinstance(item, dict):
            render_entity_card(item, key_prefix=f"{item_key}_card")
        else:
            st.markdown(_field_row_html(f"Item {i + 1}", item), unsafe_allow_html=True)

        label_col, c_ok, c_no = st.columns([6, 1, 1], vertical_alignment="center")
        with label_col:
            st.markdown("<span class='mesa-toggle-row'></span>", unsafe_allow_html=True)

        def _toggle(new_choice, ik=item_key):
            st.session_state[f"{ik}_choice"] = (
                None if st.session_state.get(f"{ik}_choice") == new_choice else new_choice
            )

        if f"{item_key}_choice" not in st.session_state:
            st.session_state[f"{item_key}_choice"] = saved_choice

        with c_ok:
            st.button(
                "✓",
                key=f"{item_key}_ok",
                type="primary" if st.session_state[f"{item_key}_choice"] == "correct" else "secondary",
                on_click=_toggle,
                args=("correct",),
            )
        with c_no:
            st.button(
                "✗",
                key=f"{item_key}_no",
                type="primary" if st.session_state[f"{item_key}_choice"] == "incorrect" else "secondary",
                on_click=_toggle,
                args=("incorrect",),
            )

        final_choice = st.session_state[f"{item_key}_choice"]
        if final_choice == "correct":
            item_results.append(True)
        elif final_choice == "incorrect":
            item_results.append(False)
        else:
            item_results.append(None)

    missed = st.number_input(
        "Number of items missed",
        min_value=0,
        value=current_missed or 0,
        key=f"{key_prefix}_missed",
    )

    return {"items": item_results, "missed": missed}


def _render_bulk_controls(group, key_prefix):
    """✓ all / ✗ all / Clear for a group's OWN scalar (leaf) fields.

    ✓/✗ fill only unreviewed fields; Clear resets all of them. Callbacks mutate
    the per-field ``*_choice`` session keys that render_leaf_toggle reads, so the
    ensuing rerun repaints the toggles and roll-up from the new state. List
    items and subgroups are untouched (each subgroup renders its own controls).
    """
    leaf_choice_keys = [
        f"{key_prefix}_{t.key}_choice" for t in group.targets if t.kind == "leaf"
    ]
    if not leaf_choice_keys:
        return

    def _bulk(verdict):
        current = {k: st.session_state.get(k) for k in leaf_choice_keys}
        for k, v in bulk_apply(current, verdict).items():
            st.session_state[k] = v

    bk = f"{key_prefix}_{group.path}_bulk"
    st.caption("Set all fields in this block")
    c_ok, c_no, c_clr, _ = st.columns([1, 1, 1, 1], vertical_alignment="center")
    with c_ok:
        st.button("✓ all", key=f"{bk}_ok", on_click=_bulk, args=("correct",),
                  help="Mark all unreviewed fields correct")
    with c_no:
        st.button("✗ all", key=f"{bk}_no", on_click=_bulk, args=("incorrect",),
                  help="Mark all unreviewed fields incorrect")
    with c_clr:
        st.button("Clear", key=f"{bk}_clear", on_click=_bulk, args=(None,),
                  help="Reset all fields in this block to unreviewed")


def render_group(group, extraction_data, inspector, key_prefix, doc_results, glossary, depth=0):
    """
    Render one Group (and its subgroups, indented) as ✓/✗ rows. Returns
    ``{target.key: verdict}`` for every target rendered in this group and its
    subgroups. The group itself stores no verdict of its own -- the roll-up
    line is derived on the fly from its targets' stored results.
    """
    results = {}
    summary = describe_class(group.class_name, inspector, glossary or {})

    def describe_heading(fname):
        return describe_field_by_name(fname, inspector, glossary or {})

    # depth 0 groups already sit inside a titled expander (see 2_Validate.py);
    # only subgroups need their own heading here.
    if depth > 0:
        indent = "&nbsp;" * 4 * depth
        st.markdown(f"{indent}**{group.class_name}**", unsafe_allow_html=True)
    if summary:
        st.caption(summary)
    _render_bulk_controls(group, key_prefix)
    # The roll-up must reflect the verdicts chosen in THIS run (including a
    # click that triggered the current rerun), so reserve its slot now and
    # fill it after the rows/subgroups have been collected into ``results``.
    roll_placeholder = st.empty()

    for target in group.targets:
        resolved = resolve_target(target, extraction_data, inspector)
        tk = f"{key_prefix}_{target.key}"
        if target.kind == "leaf":
            results[target.key] = render_leaf_toggle(
                target, resolved, tk, doc_results.get(target.key)
            )
        else:
            _nested_heading(
                target.field_name or target.title,
                count=len(resolved.get("items", [])),
                describe_heading=describe_heading,
            )
            results[target.key] = render_list_target(
                target, resolved, tk, doc_results.get(target.key)
            )

    for sub in group.subgroups:
        results.update(
            render_group(
                sub, extraction_data, inspector, key_prefix, doc_results, glossary, depth + 1
            )
        )

    roll = group_rollup(group, results)
    roll_placeholder.caption(
        f"▸ {roll['correct']} correct · {roll['incorrect']} incorrect · "
        f"{roll['unvalidated']} unvalidated"
    )
    return results
