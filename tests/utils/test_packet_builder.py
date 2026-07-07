import json
import re

import pytest

from utils.models import FieldSelection, Session
from utils.packet_builder import build_packet_data, build_packet_html, write_packet


@pytest.fixture()
def session():
    return Session(
        id="test-session-id",
        name="test_val",
        schema_module="oncollamaschemav3",
        root_class="OncoLlamaModel",
        predictions_folder="predictions/test",
        sample_size=8,
        selections=[
            FieldSelection(
                selection_type="basemodel_field",
                class_name="PrimaryCancerFacts",
                field_name="topography",
            ),
            FieldSelection(
                selection_type="basemodel_class",
                class_name="MolecularBiomarkerProfile",
            ),
            FieldSelection(
                selection_type="enum_value",
                class_name="TimelineEventType",
                enum_value="evidence_of_metastatic_progression",
            ),
        ],
    )


@pytest.fixture()
def document_ids(session):
    from utils.predictions_loader import get_prediction_files

    return get_prediction_files(session.predictions_folder)[:2]


def test_packet_data_shape(session, document_ids):
    data = build_packet_data(session, document_ids, "dr_smith")
    assert data["packet_name"] == "dr_smith"
    assert data["session_name"] == "test_val"
    assert len(data["documents"]) == 2
    assert len(data["selections"]) == 3
    keys = {s["key"] for s in data["selections"]}
    doc = data["documents"][0]
    assert set(doc["blocks"]) == keys
    assert isinstance(doc["content"], str) and doc["document_id"]
    kinds = {s["key"]: s["kind"] for s in data["selections"]}
    for key, block in doc["blocks"].items():
        assert block["kind"] == kinds[key]


def test_html_embeds_escaped_json(session, document_ids):
    data = build_packet_data(session, document_ids, "dr_smith")
    data["documents"][0]["content"] = 'evil </script><script>alert(1)</script>'
    html = build_packet_html(data)
    payload = re.search(
        r'<script type="application/json" id="packet-data">(.*?)</script>',
        html,
        re.DOTALL,
    ).group(1)
    assert "<" not in payload  # every < escaped as <
    assert json.loads(payload)["documents"][0]["content"].startswith("evil ")


def test_write_packet(tmp_path, session, document_ids):
    path = write_packet(session, document_ids, "Dr Smith", output_dir=tmp_path)
    assert path == tmp_path / "dr_smith.html"
    assert "packet-data" in path.read_text(encoding="utf-8")


def test_selections_carry_summaries(session, document_ids):
    data = build_packet_data(session, document_ids, "dr_smith")
    by_key = {s["key"]: s for s in data["selections"]}
    topo = by_key["basemodel_field_PrimaryCancerFacts_topography"]
    assert topo["desc"] == "The body site where the primary cancer started (e.g. breast, lung)."
    # field_glossary is available for nested sub-object headings
    assert isinstance(data["field_glossary"], dict)


def test_unknown_document_id_raises(session):
    with pytest.raises(FileNotFoundError):
        build_packet_data(session, ["nope"], "x")
