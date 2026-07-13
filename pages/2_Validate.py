"""
2_Validate.py - Two-pane HITL validation interface
"""

import streamlit as st

from utils.document_pane import render_document_pane
from utils.glossary import load_glossary
from utils.predictions_loader import load_prediction_file
from utils.schema_inspector import SchemaInspector
from utils.session_manager import SessionManager
from utils.styles import VALIDATE_PAGE_STYLES
from utils.validation_plan import build_validation_plan, flatten_targets, resolve_target
from utils.validation_ui import is_value_present, render_group

st.set_page_config(page_title="Validate", layout="wide")
st.logo("aic_logo.png")

st.markdown(VALIDATE_PAGE_STYLES, unsafe_allow_html=True)


def _result_is_incorrect(result):
    """A target is 'incorrect' if its verdict is Incorrect, or (for lists) any
    item is Incorrect or the model missed items."""
    if isinstance(result, str):
        return result.endswith("_INCORRECT")
    if isinstance(result, dict):
        return any(x is False for x in result.get("items", [])) or (
            result.get("missed", 0) > 0
        )
    return False


def _group_is_incorrect(group_results):
    """A group is 'incorrect' if any target rendered under it is incorrect."""
    return any(_result_is_incorrect(v) for v in group_results.values())


def _group_has_extracted(group, extraction_data, inspector):
    """A group is 'extracted' if any target in it (or its subgroups) has
    content: a single value that is present, or a list with at least one item."""
    for target in flatten_targets([group]):
        resolved = resolve_target(target, extraction_data, inspector)
        if resolved["kind"] == "list":
            if resolved["items"]:
                return True
        elif is_value_present(resolved["value"]):
            return True
    return False


def _render_comment_box(
    session, document_id, selection_key, is_incorrect, progress, block_prefix
):
    """
    Hidden-by-default freetext comment for one block. Opens when the validator
    clicks 'Add comment' or when the block is marked Incorrect. Streamlit forbids
    nested expanders (blocks already sit inside one), so this uses a button
    toggle + text_area rather than an expander/popover.
    """
    saved_comment = (
        progress.get("comments", {}).get(document_id, {}).get(selection_key, "")
    )

    open_key = f"{block_prefix}_comment_open"
    dismissed_key = f"{block_prefix}_comment_dismissed"
    text_key = f"{block_prefix}_comment_text"

    # re-arm auto-open if the verdict later flips back to incorrect
    if not is_incorrect:
        st.session_state[dismissed_key] = False

    show_comment = (
        st.session_state.get(open_key, False)
        or bool(saved_comment)
        or (is_incorrect and not st.session_state.get(dismissed_key, False))
    )

    if not show_comment:
        if st.button("Add comment", key=f"{block_prefix}_comment_add"):
            st.session_state[open_key] = True
            st.rerun()
        return

    def _save_comment(dk=document_id, sk=selection_key, tk=text_key):
        st.session_state.progress = SessionManager(session.id).save_comment(
            dk, sk, st.session_state.get(tk, "")
        )

    st.text_area(
        "Comment",
        value=saved_comment,
        key=text_key,
        on_change=_save_comment,
        label_visibility="collapsed",
        placeholder="Optional comment for the coordinator…",
    )
    if st.button("Hide comment", key=f"{block_prefix}_comment_hide"):
        st.session_state[open_key] = False
        st.session_state[dismissed_key] = True
        st.rerun()

if "active_session" not in st.session_state:
    st.session_state.active_session = None

if "progress" not in st.session_state:
    st.session_state.progress = None

if "current_results" not in st.session_state:
    st.session_state.current_results = {}

if "excluded_files" not in st.session_state:
    st.session_state.excluded_files = {}

if not st.session_state.active_session:
    st.warning("No active session. Please select a session from Sessions page.")
    if st.button("Go to Sessions"):
        st.switch_page("pages/1_Sessions.py")
    st.stop()

session = st.session_state.active_session

if st.session_state.progress is None:
    with st.spinner("Loading and validating documents..."):
        progress, excluded = SessionManager(session.id).initialize_files(session)
        st.session_state.progress = progress
        st.session_state.excluded_files = excluded

progress = st.session_state.progress

st.title("Validation Interface")

## UI: SIDEBAR STATS
st.sidebar.markdown(f"### {session.name}")
st.sidebar.markdown(f"**Schema:** {session.schema_module}")
st.sidebar.markdown(f"**Valid documents:** {len(progress['files'])}")
st.sidebar.markdown(f"**Excluded documents:** {len(st.session_state.excluded_files)}")
st.sidebar.markdown(
    f"**Completed:** {len(progress.get('completed_files', []))}/{len(progress['files'])}"
)

if st.session_state.excluded_files:
    with st.sidebar.expander("View excluded documents"):
        for document_id, error in st.session_state.excluded_files.items():
            st.caption(f"**{document_id}**")
            st.caption(f"_{error}_")
            st.markdown("---")

## UI: VALIDATION INTERFACE
if not progress["files"]:
    st.error(
        "No valid documents to validate. All documents were excluded due to schema validation errors."
    )
    st.info("Check the excluded documents in the sidebar for details.")
else:
    current_index = progress["current_file_index"]
    document_id = progress["files"][current_index]

    st.progress((current_index + 1) / len(progress["files"]))
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"**Document {current_index + 1} of {len(progress['files'])}**")
    with col2:
        st.caption(document_id)

    st.markdown("---")

    try:
        prediction_data = load_prediction_file(
            document_id, session.predictions_folder
        )
        extraction_data = prediction_data["document_inference"]

        inspector = SchemaInspector(session.schema_module, session.root_class)

        doc_col, val_col = st.columns([1, 1])

        with doc_col:
            st.markdown("### Document")
            highlight = st.session_state.get("highlight_query")
            if highlight:
                hcol1, hcol2 = st.columns([5, 1])
                with hcol1:
                    st.caption(f"Highlighting: “{highlight[:80]}”")
                with hcol2:
                    if st.button("Clear", key="clear_highlight"):
                        st.session_state["highlight_query"] = None
                        st.rerun()
            render_document_pane(
                prediction_data.get("document_content", "No content available"),
                highlight_query=highlight,
                height=800,
            )

        with val_col:
            st.markdown("### Validation")

            plan = build_validation_plan(session.selections, inspector)

            extracted_flags = [
                _group_has_extracted(group, extraction_data, inspector) for group in plan
            ]
            n_extracted = sum(extracted_flags)
            n_empty = len(extracted_flags) - n_extracted

            block_filter = st.segmented_control(
                "Show blocks",
                options=["All", "Extracted", "Empty"],
                default="All",
                key="block_filter",
                label_visibility="collapsed",
            )
            block_filter = block_filter or "All"

            count_note = f"{n_extracted} extracted · {n_empty} empty"
            if block_filter == "Extracted" and n_empty:
                count_note += f" · {n_empty} empty hidden"
            elif block_filter == "Empty" and n_extracted:
                count_note += f" · {n_extracted} extracted hidden"
            st.caption(count_note)

            with st.container(height=800):
                existing_results = progress["results"].get(document_id, {})
                glossary = load_glossary(session.schema_module)

                results = {}
                shown = 0

                for gi, group in enumerate(plan):
                    is_extracted = extracted_flags[gi]
                    if block_filter == "Extracted" and not is_extracted:
                        continue
                    if block_filter == "Empty" and is_extracted:
                        continue
                    shown += 1

                    with st.expander(f"**{group.class_name}**", expanded=True):
                        group_results = render_group(
                            group,
                            extraction_data,
                            inspector,
                            key_prefix=f"doc_{current_index}_g{gi}",
                            doc_results=existing_results,
                            glossary=glossary,
                        )
                        results.update(group_results)

                        _render_comment_box(
                            session,
                            document_id,
                            group.path,
                            _group_is_incorrect(group_results),
                            progress,
                            block_prefix=f"doc_{current_index}_g{gi}",
                        )

                if shown == 0:
                    st.info(
                        f"No {block_filter.lower()} blocks for this document. "
                        "Switch the filter above to see other blocks."
                    )

                # save results immediately if any non-none values exist
                non_none_results = {
                    k: v for k, v in results.items() if v != "NONE" and v is not None
                }
                if non_none_results:
                    st.session_state.progress = SessionManager(session.id).save_results(
                        document_id, non_none_results
                    )

                st.markdown("---")
                is_completed = document_id in progress.get("completed_files", [])

                # sync session state with actual completion status from progress.json
                st.session_state.doc_complete_checkbox = is_completed

                def toggle_completion():
                    """Toggle completion status and save immediately."""
                    manager = SessionManager(session.id)
                    progress = manager.load_progress()
                    if "completed_files" not in progress:
                        progress["completed_files"] = []

                    if st.session_state.get("doc_complete_checkbox", False):
                        if document_id not in progress["completed_files"]:
                            progress["completed_files"].append(document_id)
                    else:
                        if document_id in progress["completed_files"]:
                            progress["completed_files"].remove(document_id)

                    manager.save_progress(progress)
                    st.session_state.progress = progress

                completed_checkbox = st.checkbox(
                    "Mark document as fully validated",
                    key="doc_complete_checkbox",
                    on_change=toggle_completion,
                )

        ## UI: NAVIGATION
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])

        with col1:
            if current_index > 0:
                if st.button("Previous"):
                    progress["current_file_index"] -= 1
                    SessionManager(session.id).save_progress(progress)
                    st.session_state.progress = progress
                    st.session_state["highlight_query"] = None
                    st.rerun()

        with col2:
            st.write(f"Document {current_index + 1} of {len(progress['files'])}")

        with col3:
            if current_index < len(progress["files"]) - 1:
                if st.button("Next"):
                    progress["current_file_index"] += 1
                    SessionManager(session.id).save_progress(progress)
                    st.session_state.progress = progress
                    st.session_state["highlight_query"] = None
                    st.rerun()

    except Exception as e:
        st.error(f"Error loading document: {e}")
        st.exception(e)
