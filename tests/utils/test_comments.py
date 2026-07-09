from utils.comments import format_comments_rows
from utils.models import FieldSelection

SEL = FieldSelection(
    selection_type="basemodel_field",
    class_name="PrimaryCancerFacts",
    field_name="topography",
)
KEY = SEL.build_key()


def test_known_key_resolves_to_readable_title():
    progress = {"comments": {"doc-1": {KEY: "note A"}}}
    rows = format_comments_rows(progress, [SEL])
    assert rows == [
        {
            "document": "doc-1",
            "section": "PrimaryCancerFacts.topography",
            "comment": "note A",
        }
    ]


def test_unknown_key_falls_back_to_raw_key():
    progress = {"comments": {"doc-2": {"mystery_key": "note B"}}}
    rows = format_comments_rows(progress, [SEL])
    assert rows[0]["section"] == "mystery_key"
    assert rows[0]["comment"] == "note B"


def test_empty_comments_returns_empty_list():
    assert format_comments_rows({"comments": {}}, [SEL]) == []
    assert format_comments_rows({}, [SEL]) == []


def test_blank_text_is_skipped():
    progress = {"comments": {"doc-1": {KEY: ""}}}
    assert format_comments_rows(progress, [SEL]) == []


def test_rows_sorted_by_document_then_section():
    other = FieldSelection(
        selection_type="basemodel_field",
        class_name="PrimaryCancerFacts",
        field_name="morphology",
    )
    progress = {
        "comments": {
            "doc-2": {KEY: "z"},
            "doc-1": {other.build_key(): "b", KEY: "a"},
        }
    }
    rows = format_comments_rows(progress, [SEL, other])
    assert [(r["document"], r["section"]) for r in rows] == [
        ("doc-1", "PrimaryCancerFacts.morphology"),
        ("doc-1", "PrimaryCancerFacts.topography"),
        ("doc-2", "PrimaryCancerFacts.topography"),
    ]
