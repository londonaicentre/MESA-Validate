import json
import re

import pytest

from utils.models import FieldSelection, Session
from utils.packet_builder import build_packet_data, build_packet_html, write_packet
from utils.schema_inspector import SchemaInspector
from utils.validation_plan import build_validation_plan, flatten_targets


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

    inspector = SchemaInspector(session.schema_module, session.root_class)
    plan = build_validation_plan(session.selections, inspector)
    targets = flatten_targets(plan)
    keys = {t.key for t in targets}
    kinds = {t.key: ("list" if t.kind == "list" else "single") for t in targets}

    assert data["plan"] and data["plan"][0]["class_name"] == plan[0].class_name

    doc = data["documents"][0]
    assert set(doc["blocks"]) == keys
    assert isinstance(doc["content"], str) and doc["document_id"]
    for key, block in doc["blocks"].items():
        assert block["kind"] == kinds[key]

    # a concrete key from the fixture's PrimaryCancerFacts.topography selection
    assert "primary_cancer.primary_cancer_facts.topography" in doc["blocks"]


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


def test_plan_targets_carry_summaries(session, document_ids):
    data = build_packet_data(session, document_ids, "dr_smith")
    group = next(g for g in data["plan"] if g["class_name"] == "PrimaryCancerFacts")
    topo = next(t for t in group["targets"] if t["field_name"] == "topography")
    assert topo["summary"] == "Most suitable anatomical site of primary cancer."
    # field_glossary is available for nested sub-object headings
    assert isinstance(data["field_glossary"], dict)


def test_packet_data_has_no_comments(session, document_ids):
    # comments are runtime validator input, never seeded into packet DATA
    data = build_packet_data(session, document_ids, "dr_smith")
    assert "comments" not in data


def test_template_has_comment_hooks():
    from pathlib import Path

    html = Path("utils/packet_template.html").read_text(encoding="utf-8")
    assert "function getComment" in html
    assert "function setComment" in html
    assert "comment-input" in html
    assert "comments: state.comments" in html  # persisted in resultsPayload


def test_unknown_document_id_raises(session):
    with pytest.raises(FileNotFoundError):
        build_packet_data(session, ["nope"], "x")
