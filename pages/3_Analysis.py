"""
3_Analysis.py - Results analysis and metrics visualization
"""

import pandas as pd
import streamlit as st

from mesa_validate.metrics import (
    aggregate_metrics,
    export_to_csv_string,
    format_metrics_summary,
)
from mesa_validate.session_manager import SessionManager

st.set_page_config(page_title="Analysis", layout="wide")
st.logo("aic_logo.png")

st.title("Results Analysis")

sessions = SessionManager.list_all()

if not sessions:
    st.info("No sessions found. Create a session first.")
else:
    session_options = {s.name: s for s in sessions}
    selected_session_name = st.selectbox(
        "Select session to analyze", options=list(session_options.keys())
    )

    if selected_session_name:
        session = session_options[selected_session_name]

        progress = SessionManager(session.id).load_progress()

        st.markdown("---")

        ## UI: SESSION OVERVIEW
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Files", len(progress.get("files", [])))

        with col2:
            st.metric("Completed", len(progress.get("completed_files", [])))

        with col3:
            completion = 0
            if progress.get("files"):
                completion = (
                    len(progress.get("completed_files", []))
                    / len(progress["files"])
                    * 100
                )
            st.metric("Completion", f"{completion:.1f}%")

        with col4:
            st.metric("Selections", len(session.selections))

        st.markdown("---")

        ## UI: METRICS SUMMARY
        if not progress.get("completed_files"):
            st.info(
                "No completed documents yet. Mark documents as complete to see analysis."
            )
        else:
            metrics = aggregate_metrics(progress, session.selections)

            if not metrics:
                st.info("No metrics to display")
            else:
                st.subheader("Metrics Summary")

                summary = format_metrics_summary(metrics)

                binary_metrics = [m for m in summary if m["type"] == "Binary"]
                list_metrics = [m for m in summary if m["type"] == "List"]

                if binary_metrics:
                    st.markdown("### Binary Validations")

                    df_binary = pd.DataFrame(binary_metrics)
                    st.dataframe(df_binary, use_container_width=True, hide_index=True)

                if list_metrics:
                    st.markdown("### List Validations")

                    df_list = pd.DataFrame(list_metrics)
                    st.dataframe(df_list, use_container_width=True, hide_index=True)

                st.markdown("---")

                ## UI: EXPORT RESULTS
                st.subheader("Export Results")

                csv_data = export_to_csv_string(progress, session.selections)

                st.download_button(
                    label="Download Results CSV",
                    data=csv_data,
                    file_name=f"{session.name}_results.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

                ## UI: DETAILED RESULTS
                st.markdown("---")
                st.subheader("Detailed Results")

                with st.expander("View All Results", expanded=False):
                    results_data = []
                    completed_files = set(progress.get("completed_files", []))

                    for file_path, file_results in progress.get("results", {}).items():
                        if file_path not in completed_files:
                            continue

                        row = {"file": file_path.split("/")[-1]}

                        for key, value in file_results.items():
                            if isinstance(value, str):
                                row[key] = value
                            elif isinstance(value, dict):
                                items = value.get("items", [])
                                # only count evaluated items (not none)
                                evaluated = [item for item in items if item is not None]
                                correct = sum(1 for item in evaluated if item is True)
                                total = len(evaluated)
                                missed = value.get("missed", 0)
                                row[key] = f"{correct}/{total} (missed: {missed})"

                        results_data.append(row)

                    if results_data:
                        df_results = pd.DataFrame(results_data)
                        st.dataframe(
                            df_results, use_container_width=True, hide_index=True
                        )
