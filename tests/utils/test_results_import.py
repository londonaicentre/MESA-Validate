import pytest

from utils.metrics import aggregate_metrics
from utils.models import FieldSelection
from utils.results_import import combine_progress, parse_results_payload

SEL = FieldSelection(
    selection_type="basemodel_field",
    class_name="PrimaryCancerFacts",
    field_name="topography",
)
KEY = SEL.build_key()

PAYLOAD = {
    "packet_name": "dr_smith",
    "session_name": "test_val",
    "schema_module": "oncollamaschemav3",
    "saved_at": "2026-07-05T10:00:00",
    "completed_files": ["doc-1"],
    "results": {
        "doc-1": {KEY: "PRESENT_CORRECT"},
        "doc-2": {KEY: "PRESENT_INCORRECT"},
    },
}


def test_parse_results_payload():
    meta, progress = parse_results_payload(PAYLOAD)
    assert meta["packet_name"] == "dr_smith"
    assert progress["completed_files"] == ["doc-1"]
    assert progress["results"]["doc-1"][KEY] == "PRESENT_CORRECT"


def test_parse_rejects_garbage():
    with pytest.raises(ValueError):
        parse_results_payload({"foo": "bar"})


def test_packet_metrics_match_native_progress():
    _, progress = parse_results_payload(PAYLOAD)
    native = {
        "results": PAYLOAD["results"],
        "completed_files": ["doc-1"],
        "current_file_index": 0,
        "files": ["doc-1", "doc-2"],
    }
    assert aggregate_metrics(progress, [SEL]) == aggregate_metrics(native, [SEL])


def test_combine_progress_namespaces_documents():
    p1 = parse_results_payload(PAYLOAD)
    p2 = parse_results_payload(
        {
            **PAYLOAD,
            "packet_name": "dr_jones",
            "results": {"doc-1": {KEY: "ABSENT_INCORRECT"}},
            "completed_files": ["doc-1"],
        }
    )
    combined = combine_progress([p1, p2])
    assert set(combined["completed_files"]) == {
        "dr_smith::doc-1",
        "dr_jones::doc-1",
    }
    metrics = aggregate_metrics(combined, [SEL])
    assert metrics[KEY]["total"] == 2  # both clinicians' doc-1 counted
