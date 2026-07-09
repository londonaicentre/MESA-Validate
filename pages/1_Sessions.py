"""
1_Sessions.py - management and setup of validation sessions
"""

import uuid

import streamlit as st

from mesa_validate.models import FieldSelection, Session
from mesa_validate.predictions_loader import list_prediction_folders
from mesa_validate.schema_inspector import SchemaInspector
from mesa_validate.schema_loader import get_schema_list
from mesa_validate.session_manager import SessionManager

st.set_page_config(page_title="Sessions", layout="wide")
st.logo("aic_logo.png")

st.title("Sessions")

if "active_session" not in st.session_state:
    st.session_state.active_session = None

if "progress" not in st.session_state:
    st.session_state.progress = None

if "delete_confirm" not in st.session_state:
    st.session_state.delete_confirm = None

sessions = SessionManager.list_all()

if st.session_state.active_session:
    session = st.session_state.active_session

    st.success(f"Active Session: **{session.name}**")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Start Validation", use_container_width=True):
            st.switch_page("pages/2_Validate.py")
    with col2:
        if st.button("Close Session", use_container_width=True):
            st.session_state.active_session = None
            st.session_state.progress = None
            st.rerun()

    st.markdown("---")

## UI: SESSION LIST
st.subheader("Existing Sessions")

if not sessions:
    st.info("No sessions found. Create a new session below.")
else:
    for session in sessions:
        progress = SessionManager(session.id).load_progress()
        validated = len(progress.get("completed_files", []))
        total = (
            len(progress.get("files", []))
            if progress.get("files")
            else session.sample_size
        )

        with st.container():
            col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 1, 1])

            with col1:
                st.markdown(f"**{session.name}**")
                st.caption(f"Schema: {session.schema_module}")

            with col2:
                st.caption(f"Files: {total}")

            with col3:
                progress_pct = (validated / total * 100) if total > 0 else 0
                st.caption(f"Progress: {validated}/{total} ({progress_pct:.0f}%)")

            with col4:
                is_active = (
                    st.session_state.active_session
                    and st.session_state.active_session.id == session.id
                )
                if not is_active:
                    if st.button("Load", key=f"load_{session.id}"):
                        st.session_state.active_session = session
                        st.session_state.progress = None
                        st.rerun()
                else:
                    st.caption("Active")

            with col5:
                if st.button("Delete", key=f"delete_{session.id}"):
                    st.session_state.delete_confirm = session.id
                    st.rerun()

            st.markdown("---")

## UI: DELETE CONFIRMATION
if st.session_state.delete_confirm:
    session_to_delete = next(
        (s for s in sessions if s.id == st.session_state.delete_confirm), None
    )

    if session_to_delete:
        st.warning(
            f"Are you sure you want to delete session **{session_to_delete.name}**?"
        )
        st.caption(
            "This will permanently delete all session data, progress, and results."
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Cancel", use_container_width=True):
                st.session_state.delete_confirm = None
                st.rerun()

        with col2:
            if st.button("Confirm Delete", type="primary", use_container_width=True):
                try:
                    SessionManager(st.session_state.delete_confirm).delete()

                    # clear active
                    if (
                        st.session_state.active_session
                        and st.session_state.active_session.id
                        == st.session_state.delete_confirm
                    ):
                        st.session_state.active_session = None
                        st.session_state.progress = None

                    st.session_state.delete_confirm = None
                    st.success(
                        f"Session '{session_to_delete.name}' deleted successfully"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Error deleting session: {e}")

        st.markdown("---")


def create_setup_data():
    return {
        "schema_module": None,
        "root_class": None,
        "inspector": None,
        "classes": None,
        "selections": [],
        "predictions_folder": None,
        "sample_size": 10,
    }


if "setup_step" not in st.session_state:
    st.session_state.setup_step = 1

if "setup_data" not in st.session_state:
    st.session_state.setup_data = create_setup_data()


def next_step():
    st.session_state.setup_step += 1


def prev_step():
    st.session_state.setup_step -= 1


def reset_wizard():
    st.session_state.setup_step = 1
    st.session_state.setup_data = create_setup_data()


## UI: CREATE NEW SESSION 'WIZARD'

with st.expander("Create New Session", expanded=False):
    if st.session_state.setup_step == 1:
        st.subheader("Step 1: Schema Selection")

        schemas = get_schema_list()

        if not schemas:
            st.error("No schemas configured in schemas.yaml")
        else:
            st.write(f"Found {len(schemas)} schema(s)")

            selected_schema = st.selectbox(
                "Select schema", options=[s["name"] for s in schemas], index=0
            )

            schema_info = next(
                (s for s in schemas if s["name"] == selected_schema), None
            )

            if schema_info and st.button("Next"):
                try:
                    inspector = SchemaInspector(
                        schema_info["module"],
                        root_class_name=schema_info.get("root_class"),
                    )
                    classes = inspector.classes

                    st.session_state.setup_data["schema_module"] = schema_info["module"]
                    st.session_state.setup_data["root_class"] = schema_info[
                        "root_class"
                    ]
                    st.session_state.setup_data["inspector"] = inspector
                    st.session_state.setup_data["classes"] = classes

                    st.success(f"Loaded {len(classes)} classes from schema")
                    next_step()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error loading schema: {e}")

    elif st.session_state.setup_step == 2:
        st.subheader("Step 2: Field Selection")

        classes = st.session_state.setup_data["classes"]
        inspector = st.session_state.setup_data["inspector"]

        if not classes:
            st.error("No classes loaded")
        else:
            st.write("Select classes, fields, or enum values to validate:")

            selections = []

            basemodel_classes = {
                name: info
                for name, info in classes.items()
                if info["type"] == "BaseModel"
            }
            enum_classes = {
                name: info for name, info in classes.items() if info["type"] == "Enum"
            }

            st.markdown("### BaseModel Classes")

            for class_name, class_info in basemodel_classes.items():
                with st.expander(f"**{class_name}**", expanded=False):
                    whole_class = st.checkbox(
                        f"Select entire {class_name} class", key=f"class_{class_name}"
                    )

                    if whole_class:
                        selections.append(
                            FieldSelection(
                                selection_type="basemodel_class", class_name=class_name
                            )
                        )

                    st.markdown("**Individual Fields:**")
                    fields = class_info["fields"]

                    for field_name, field_info in fields.items():
                        field_selected = st.checkbox(
                            f"{field_name} ({field_info['type']})",
                            key=f"field_{class_name}_{field_name}",
                            disabled=whole_class,
                        )

                        if field_selected and not whole_class:
                            selections.append(
                                FieldSelection(
                                    selection_type="basemodel_field",
                                    class_name=class_name,
                                    field_name=field_name,
                                )
                            )

            if enum_classes:
                st.markdown("### Enum Classes")
                st.caption("Only showing enums used in list fields")

                for class_name, class_info in enum_classes.items():
                    enum_class = class_info["class"]

                    # only show enums that are used in list contexts
                    if inspector.is_enum_used_in_list_context(class_name):
                        with st.expander(f"**{class_name}**", expanded=False):
                            st.write(
                                "Select specific enum values to filter and validate:"
                            )

                            for enum_value in class_info["values"]:
                                value_selected = st.checkbox(
                                    enum_value, key=f"enum_{class_name}_{enum_value}"
                                )

                                if value_selected:
                                    selections.append(
                                        FieldSelection(
                                            selection_type="enum_value",
                                            class_name=class_name,
                                            enum_value=enum_value,
                                        )
                                    )

            st.markdown("---")

            col1, col2 = st.columns([1, 1])

            with col1:
                if st.button("Back"):
                    prev_step()
                    st.rerun()

            with col2:
                if st.button("Next", disabled=len(selections) == 0):
                    st.session_state.setup_data["selections"] = selections
                    next_step()
                    st.rerun()

            if len(selections) == 0:
                st.warning("Please select at least one item to continue")
            else:
                st.info(f"{len(selections)} selection(s) made")

    elif st.session_state.setup_step == 3:
        st.subheader("Step 3: Predictions Folder")

        folders = list_prediction_folders()

        if not folders:
            st.error("No folders found in 'predictions/' directory")
        else:
            st.write(f"Found {len(folders)} folder(s) with predictions")

            folder_options = {
                f"{f['name']} ({f['num_files']} files)": f for f in folders
            }

            selected_folder = st.selectbox(
                "Select predictions folder", options=list(folder_options.keys())
            )

            folder_info = folder_options[selected_folder]
            num_files = int(folder_info["num_files"])

            sample_size = st.number_input(
                "Sample size",
                min_value=1,
                max_value=num_files,
                value=min(10, num_files),
            )

            percentage = (
                (sample_size / num_files * 100)
                if num_files > 0
                else 0
            )
            st.info(
                f"Selected {sample_size} of {num_files} files ({percentage:.1f}%)"
            )

            st.markdown("---")

            col1, col2 = st.columns([1, 1])

            with col1:
                if st.button("Back"):
                    prev_step()
                    st.rerun()

            with col2:
                if st.button("Next"):
                    st.session_state.setup_data["predictions_folder"] = folder_info[
                        "path"
                    ]
                    st.session_state.setup_data["sample_size"] = sample_size
                    next_step()
                    st.rerun()

    elif st.session_state.setup_step == 4:
        st.subheader("Step 4: Review & Create")

        st.write("Review your session configuration:")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Schema**")
            st.code(st.session_state.setup_data["schema_module"])

            st.markdown("**Predictions Folder**")
            st.code(st.session_state.setup_data["predictions_folder"])

            st.markdown("**Sample Size**")
            st.code(st.session_state.setup_data["sample_size"])

        with col2:
            st.markdown(
                f"**Selections ({len(st.session_state.setup_data['selections'])})**"
            )

            for selection in st.session_state.setup_data["selections"]:
                if selection.selection_type == "basemodel_class":
                    st.write(f"- {selection.class_name} (entire class)")
                elif selection.selection_type == "basemodel_field":
                    st.write(f"- {selection.class_name}.{selection.field_name}")
                elif selection.selection_type == "enum_value":
                    st.write(f"- {selection.class_name}.{selection.enum_value}")

        st.markdown("---")

        session_name = st.text_input(
            "Session name", placeholder="e.g., Batch 1 Validation"
        )

        col1, col2 = st.columns([1, 1])

        with col1:
            if st.button("Back"):
                prev_step()
                st.rerun()

        with col2:
            if st.button("Create Session", disabled=not session_name):
                try:
                    # ensure unique session names
                    existing_sessions = SessionManager.list_all()
                    if any(s.name == session_name for s in existing_sessions):
                        st.error(
                            f"Session '{session_name}' already exists. Please choose a different name."
                        )
                    else:
                        session = Session(
                            id=str(uuid.uuid4()),
                            name=session_name,
                            schema_module=st.session_state.setup_data["schema_module"],
                            root_class=st.session_state.setup_data["root_class"],
                            predictions_folder=st.session_state.setup_data[
                                "predictions_folder"
                            ],
                            sample_size=st.session_state.setup_data["sample_size"],
                            selections=st.session_state.setup_data["selections"],
                        )

                        SessionManager.create_new(session)

                        st.session_state.active_session = session

                        reset_wizard()

                        st.rerun()

                except Exception as e:
                    st.error(f"Error creating session: {e}")

        if not session_name:
            st.warning("Please enter a session name to continue")
