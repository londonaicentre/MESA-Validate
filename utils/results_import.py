"""
results_import.py - Import clinician packet results into Analysis

Converts packet results files back into the progress.json shape consumed by
utils/metrics.py.
"""

REQUIRED_KEYS = ("packet_name", "results", "completed_files")


def parse_results_payload(data):
    """
    Validate and split a packet results payload.

    Returns:
        (meta, progress) where progress matches the progress.json shape
        expected by aggregate_metrics.
    """
    if not isinstance(data, dict) or any(k not in data for k in REQUIRED_KEYS):
        raise ValueError(
            "Not a MESA packet results file (expected keys: "
            + ", ".join(REQUIRED_KEYS)
            + ")"
        )
    meta = {
        "packet_name": data["packet_name"],
        "session_name": data.get("session_name", ""),
        "schema_module": data.get("schema_module", ""),
        "saved_at": data.get("saved_at", ""),
    }
    progress = {
        "results": data["results"],
        "completed_files": data["completed_files"],
    }
    return meta, progress


def combine_progress(parsed):
    """
    Pool multiple packets into one progress dict. Document ids are namespaced
    by packet so the same document validated by two clinicians counts twice.
    """
    combined = {"results": {}, "completed_files": []}
    for meta, progress in parsed:
        prefix = meta["packet_name"] + "::"
        for document_id, doc_results in progress["results"].items():
            combined["results"][prefix + document_id] = doc_results
        combined["completed_files"].extend(
            prefix + document_id for document_id in progress["completed_files"]
        )
    return combined
