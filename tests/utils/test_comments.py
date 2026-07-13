from utils.comments import format_comments_rows
from utils.models import FieldSelection
from utils.schema_inspector import SchemaInspector

INSPECTOR = SchemaInspector("oncollamaschemav3", "OncoLlamaModel")

SEL = FieldSelection(
    selection_type="basemodel_field",
    class_name="PrimaryCancerFacts",
    field_name="topography",
)
KEY = "primary_cancer.primary_cancer_facts.topography"


def test_known_key_resolves_to_readable_title():
    progress = {"comments": {"doc-1": {KEY: "note A"}}}
    rows = format_comments_rows(progress, [SEL], INSPECTOR)
    assert rows == [
        {
            "document": "doc-1",
            "section": "PrimaryCancerFacts.topography",
            "comment": "note A",
        }
    ]


def test_comment_section_resolves_group_path():
    selections = [FieldSelection(selection_type="basemodel_class", class_name="PrimaryCancer")]
    progress = {"comments": {"doc1": {"primary_cancer.primary_cancer_facts": "looks off"}}}
    rows = format_comments_rows(progress, selections, INSPECTOR)
    assert rows[0]["section"] == "PrimaryCancerFacts"
    assert rows[0]["comment"] == "looks off"


def test_unknown_key_falls_back_to_raw_key():
    progress = {"comments": {"doc-2": {"mystery_key": "note B"}}}
    rows = format_comments_rows(progress, [SEL], INSPECTOR)
    assert rows[0]["section"] == "mystery_key"
    assert rows[0]["comment"] == "note B"


def test_empty_comments_returns_empty_list():
    assert format_comments_rows({"comments": {}}, [SEL], INSPECTOR) == []
    assert format_comments_rows({}, [SEL], INSPECTOR) == []


def test_blank_text_is_skipped():
    progress = {"comments": {"doc-1": {KEY: ""}}}
    assert format_comments_rows(progress, [SEL], INSPECTOR) == []


def test_rows_sorted_by_document_then_section():
    other = FieldSelection(
        selection_type="basemodel_field",
        class_name="PrimaryCancerFacts",
        field_name="morphology",
    )
    other_key = "primary_cancer.primary_cancer_facts.morphology"
    progress = {
        "comments": {
            "doc-2": {KEY: "z"},
            "doc-1": {other_key: "b", KEY: "a"},
        }
    }
    rows = format_comments_rows(progress, [SEL, other], INSPECTOR)
    assert [(r["document"], r["section"]) for r in rows] == [
        ("doc-1", "PrimaryCancerFacts.morphology"),
        ("doc-1", "PrimaryCancerFacts.topography"),
        ("doc-2", "PrimaryCancerFacts.topography"),
    ]
