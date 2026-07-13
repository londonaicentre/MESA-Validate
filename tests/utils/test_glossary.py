import pytest

from utils.glossary import (
    describe_class,
    describe_field_by_name,
    describe_selection,
    enum_field_options,
    load_glossary,
    starter_glossary,
)
from utils.models import FieldSelection
from utils.schema_inspector import SchemaInspector


@pytest.fixture(scope="module")
def inspector():
    return SchemaInspector("oncollamaschemav3", "OncoLlamaModel")


def test_glossary_override_wins(inspector):
    glossary = {"ContextSummary": "My custom summary."}
    assert (
        describe_class("ContextSummary", inspector, glossary) == "My custom summary."
    )


def test_class_falls_back_to_parent_field_description(inspector):
    # PerformanceStatus has no glossary entry but OncoLlamaModel.performance_status
    # is described as "Most recent performance status"
    assert describe_class("PerformanceStatus", inspector, {}) == (
        "Most recent performance status."
    )


def test_field_description_strips_llm_cruft(inspector):
    sel = FieldSelection(
        selection_type="basemodel_field",
        class_name="PrimaryCancerFacts",
        field_name="topography",
    )
    out = describe_selection(sel, inspector, {})
    assert out == "Most suitable anatomical site of primary cancer."
    assert "Use OTHER" not in out


def test_enum_value_humanised(inspector):
    sel = FieldSelection(
        selection_type="enum_value",
        class_name="TimelineEventType",
        enum_value="experienced_toxicity_or_complication_related_to_treatment",
    )
    assert describe_selection(sel, inspector, {}) == (
        "Experienced toxicity or complication related to treatment"
    )


def test_enum_value_glossary_override(inspector):
    sel = FieldSelection(
        selection_type="enum_value",
        class_name="TimelineEventType",
        enum_value="patient_died",
    )
    glossary = {"TimelineEventType.patient_died": "The patient died."}
    assert describe_selection(sel, inspector, glossary) == "The patient died."


def test_describe_field_by_name(inspector):
    assert describe_field_by_name("primary_cancer_facts", inspector, {}) == (
        "Main facts about primary cancer."
    )


def test_missing_returns_none(inspector):
    # a class with no description anywhere and no glossary entry -> None
    assert describe_class("ContextSummary", inspector, {}) is None


def test_load_glossary_missing_returns_empty(tmp_path):
    assert load_glossary("nope", glossary_dir=tmp_path) == {}


def test_load_curated_glossary_covers_gaps(inspector):
    # the committed glossary must fill the classes the schema leaves blank
    glossary = load_glossary("oncollamaschemav3")
    for gap in ["ContextSummary", "FuturePlan", "OtherCancerFacts", "PatientFinding"]:
        assert describe_class(gap, inspector, glossary), f"{gap} has no summary"


def test_starter_glossary_covers_all_classes(inspector):
    starter = starter_glossary(inspector)
    assert "PerformanceStatus" in starter
    assert "PrimaryCancerFacts.topography" in starter
    assert all(isinstance(v, str) and v for v in starter.values())


def test_enum_field_options_lists_values(inspector):
    opts = enum_field_options("PrimaryCancerFacts", "topography", inspector, {})
    assert opts is not None
    assert opts["enum_class"] == "TopographyType"
    vals = [v["value"] for v in opts["values"]]
    assert "lung" in vals
    assert all(set(v.keys()) == {"value", "desc"} for v in opts["values"])


def test_enum_field_options_uses_glossary_desc(inspector):
    glossary = {"TopographyType.lung": "The lung."}
    opts = enum_field_options("PrimaryCancerFacts", "topography", inspector, glossary)
    lung = next(v for v in opts["values"] if v["value"] == "lung")
    assert lung["desc"] == "The lung."
    # a value with no glossary entry has desc None (name-only display)
    other = next(v for v in opts["values"] if v["desc"] is None)
    assert other is not None


def test_enum_field_options_none_for_scalar(inspector):
    assert (
        enum_field_options("PrimaryCancerFacts", "topography_name_desc", inspector, {})
        is None
    )


def test_enum_field_options_none_for_unknown_field(inspector):
    assert enum_field_options("PrimaryCancerFacts", "nope", inspector, {}) is None
