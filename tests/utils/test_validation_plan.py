import pytest

from utils.models import FieldSelection
from utils.schema_inspector import SchemaInspector
from utils.validation_plan import (
    build_validation_plan,
    flatten_targets,
    group_rollup,
    resolve_target,
    summarize_results,
    target_key,
)


@pytest.fixture(scope="module")
def inspector():
    return SchemaInspector("oncollamaschemav3", "OncoLlamaModel")


EXTRACTION = {
    "primary_cancer": {
        "primary_cancer_facts": {"topography": "lung", "tnm_stage": "T2N1M0"},
        "primary_cancer_scores": [
            {"score": "er", "score_value": "positive"},
            {"score": "her2", "score_value": "negative"},
        ],
    },
}


def test_whole_class_expands_to_nested_groups_and_dedupes(inspector):
    selections = [
        FieldSelection(selection_type="basemodel_class", class_name="PrimaryCancer"),
        FieldSelection(
            selection_type="basemodel_field",
            class_name="PrimaryCancerFacts",
            field_name="topography",
        ),
    ]
    groups = build_validation_plan(selections, inspector)

    # one top-level group for the selected class
    assert [g.class_name for g in groups] == ["PrimaryCancer"]

    # nested object -> subgroup; list field -> list target
    facts = next(
        sg for sg in groups[0].subgroups if sg.class_name == "PrimaryCancerFacts"
    )
    leaf_keys = [t.key for t in facts.targets]
    # topography appears exactly once despite being selected twice
    assert leaf_keys.count("primary_cancer.primary_cancer_facts.topography") == 1

    all_targets = flatten_targets(groups)
    scores = next(
        t for t in all_targets if t.key == "primary_cancer.primary_cancer_scores"
    )
    assert scores.kind == "list"


def test_scalar_field_key_is_dotted_path(inspector):
    sel = FieldSelection(
        selection_type="basemodel_field",
        class_name="PrimaryCancerFacts",
        field_name="topography",
    )
    assert target_key(sel, inspector) == "primary_cancer.primary_cancer_facts.topography"


def test_whole_nonlist_class_key_is_none(inspector):
    # A whole-class selection of a nested (non-list-item) object has no
    # single group-level results key -- it expands into many per-field
    # keys -- so target_key must return None rather than a bare class path.
    sel = FieldSelection(selection_type="basemodel_class", class_name="PrimaryCancer")
    assert target_key(sel, inspector) is None


def test_resolve_leaf_and_list(inspector):
    groups = build_validation_plan(
        [FieldSelection(selection_type="basemodel_class", class_name="PrimaryCancer")],
        inspector,
    )
    targets = {t.key: t for t in flatten_targets(groups)}

    leaf = targets["primary_cancer.primary_cancer_facts.topography"]
    assert resolve_target(leaf, EXTRACTION, inspector) == {
        "kind": "single",
        "value": "lung",
    }

    lst = targets["primary_cancer.primary_cancer_scores"]
    resolved = resolve_target(lst, EXTRACTION, inspector)
    assert resolved["kind"] == "list"
    assert len(resolved["items"]) == 2


def test_summarize_counts_leaves_and_list_items(inspector):
    groups = build_validation_plan(
        [FieldSelection(selection_type="basemodel_class", class_name="PrimaryCancer")],
        inspector,
    )
    targets = flatten_targets(groups)
    doc_results = {
        "primary_cancer.primary_cancer_facts.topography": "PRESENT_CORRECT",
        "primary_cancer.primary_cancer_facts.tnm_stage": "PRESENT_INCORRECT",
        "primary_cancer.primary_cancer_scores": {"items": [True, False], "missed": 1},
    }
    summary = summarize_results(targets, doc_results)
    # topography correct; tnm_stage incorrect; scores: 1 correct item, 1 incorrect item + 1 missed
    assert summary["correct"] == 2          # topography + 1 score item
    assert summary["incorrect"] == 3        # tnm_stage + 1 score item + 1 missed
    assert summary["unvalidated"] >= 1      # remaining untouched leaves


def test_group_rollup_matches_summarize(inspector):
    groups = build_validation_plan(
        [FieldSelection(selection_type="basemodel_class", class_name="PrimaryCancer")],
        inspector,
    )
    doc_results = {"primary_cancer.primary_cancer_facts.topography": "PRESENT_CORRECT"}
    assert group_rollup(groups[0], doc_results) == summarize_results(
        flatten_targets([groups[0]]), doc_results
    )
