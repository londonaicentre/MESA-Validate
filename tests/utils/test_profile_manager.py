import json

import pytest

from utils.models import FieldSelection
from utils.profile_manager import list_profiles, load_profile, save_profile
from utils.schema_inspector import SchemaInspector


@pytest.fixture(scope="module")
def inspector():
    return SchemaInspector("oncollamaschemav3", "OncoLlamaModel")


SELECTIONS = [
    FieldSelection(
        selection_type="basemodel_field",
        class_name="PrimaryCancerFacts",
        field_name="topography",
    ),
    FieldSelection(selection_type="basemodel_class", class_name="PerformanceStatus"),
]


def test_save_list_load_round_trip(tmp_path, inspector):
    path = save_profile(
        "My Profile", "oncollamaschemav3", SELECTIONS, profiles_dir=tmp_path
    )
    assert path.name == "my_profile.json"
    profiles = list_profiles(profiles_dir=tmp_path)
    assert [p["name"] for p in profiles] == ["My Profile"]
    assert profiles[0]["num_selections"] == 2
    valid, skipped = load_profile(path, inspector)
    assert valid == SELECTIONS and skipped == []


def test_list_filters_by_schema_module(tmp_path):
    save_profile("A", "oncollamaschemav3", SELECTIONS, profiles_dir=tmp_path)
    save_profile("B", "otherschema", SELECTIONS, profiles_dir=tmp_path)
    assert [
        p["name"] for p in list_profiles("oncollamaschemav3", profiles_dir=tmp_path)
    ] == ["A"]


def test_duplicate_name_raises(tmp_path):
    save_profile("A", "m", SELECTIONS, profiles_dir=tmp_path)
    with pytest.raises(FileExistsError):
        save_profile("A", "m", SELECTIONS, profiles_dir=tmp_path)


def test_load_skips_unknown_fields(tmp_path, inspector):
    data = {
        "name": "Stale",
        "schema_module": "oncollamaschemav3",
        "selections": [
            {
                "selection_type": "basemodel_field",
                "class_name": "PrimaryCancerFacts",
                "field_name": "topography",
            },
            {
                "selection_type": "basemodel_field",
                "class_name": "PrimaryCancerFacts",
                "field_name": "no_such_field",
            },
            {"selection_type": "basemodel_class", "class_name": "NoSuchClass"},
            {
                "selection_type": "enum_value",
                "class_name": "TimelineEventType",
                "enum_value": "no_such_value",
            },
        ],
    }
    path = tmp_path / "stale.json"
    path.write_text(json.dumps(data))
    valid, skipped = load_profile(path, inspector)
    assert len(valid) == 1 and len(skipped) == 3


def test_default_profile_loads_cleanly(inspector):
    profiles = list_profiles("oncollamaschemav3")
    default = next(p for p in profiles if p["name"] == "MESA Protocol v1")
    valid, skipped = load_profile(default["path"], inspector)
    assert skipped == [] and len(valid) == 11
