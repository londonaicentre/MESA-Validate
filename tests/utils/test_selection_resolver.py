import pytest

from utils.models import FieldSelection
from utils.schema_inspector import SchemaInspector
from utils.selection_resolver import resolve_selection, selection_kind, selection_title


@pytest.fixture(scope="module")
def inspector():
    return SchemaInspector("oncollamaschemav3", "OncoLlamaModel")


EXTRACTION = {
    "document_has_primary_cancer_flag": True,
    "primary_cancer": {
        "primary_cancer_facts": {"topography": "lung", "diagnosis_year": 2024},
        "primary_cancer_tumour_facts": {
            "molecular_biomarker_profiles": [
                {"biomarker": "kit", "biomarker_status": "altered"},
                {"biomarker": "braf", "biomarker_status": "negative"},
            ]
        },
        "primary_cancer_timeline_events": [
            {"event_type": "had_surgical_treatment_performed", "event_year": 2019},
            {"event_type": "evidence_of_metastatic_progression", "event_year": 2023},
        ],
    },
    "performance_status": {"ps_scale": "ecog", "ps_score_value": 1},
}


def test_field_resolves_to_single(inspector):
    sel = FieldSelection(
        selection_type="basemodel_field",
        class_name="PrimaryCancerFacts",
        field_name="topography",
    )
    assert resolve_selection(sel, EXTRACTION, inspector) == {
        "kind": "single",
        "value": "lung",
    }


def test_singleton_class_resolves_to_single_dict(inspector):
    sel = FieldSelection(
        selection_type="basemodel_class", class_name="PerformanceStatus"
    )
    block = resolve_selection(sel, EXTRACTION, inspector)
    assert block["kind"] == "single"
    assert block["value"]["ps_score_value"] == 1


def test_list_class_resolves_to_items(inspector):
    sel = FieldSelection(
        selection_type="basemodel_class", class_name="MolecularBiomarkerProfile"
    )
    block = resolve_selection(sel, EXTRACTION, inspector)
    assert block["kind"] == "list"
    assert [i["biomarker"] for i in block["items"]] == ["kit", "braf"]


def test_enum_value_filters_items(inspector):
    sel = FieldSelection(
        selection_type="enum_value",
        class_name="TimelineEventType",
        enum_value="evidence_of_metastatic_progression",
    )
    block = resolve_selection(sel, EXTRACTION, inspector)
    assert block["kind"] == "list"
    assert len(block["items"]) == 1 and block["items"][0]["event_year"] == 2023


def test_absent_field_resolves_to_none(inspector):
    sel = FieldSelection(
        selection_type="basemodel_field",
        class_name="PrimaryCancerFacts",
        field_name="tnm_stage",
    )
    assert resolve_selection(sel, EXTRACTION, inspector) == {
        "kind": "single",
        "value": None,
    }


def test_selection_kind(inspector):
    assert (
        selection_kind(
            FieldSelection(
                selection_type="basemodel_class",
                class_name="MolecularBiomarkerProfile",
            ),
            inspector,
        )
        == "list"
    )
    assert (
        selection_kind(
            FieldSelection(
                selection_type="basemodel_class", class_name="PerformanceStatus"
            ),
            inspector,
        )
        == "single"
    )
    assert (
        selection_kind(
            FieldSelection(
                selection_type="basemodel_field",
                class_name="PrimaryCancerFacts",
                field_name="topography",
            ),
            inspector,
        )
        == "single"
    )
    assert (
        selection_kind(
            FieldSelection(
                selection_type="enum_value",
                class_name="TimelineEventType",
                enum_value="patient_died",
            ),
            inspector,
        )
        == "list"
    )


def test_selection_title():
    assert (
        selection_title(
            FieldSelection(selection_type="basemodel_class", class_name="A")
        )
        == "A"
    )
    assert (
        selection_title(
            FieldSelection(
                selection_type="basemodel_field", class_name="A", field_name="b"
            )
        )
        == "A.b"
    )
    assert (
        selection_title(
            FieldSelection(
                selection_type="enum_value", class_name="E", enum_value="v"
            )
        )
        == "E.v"
    )
