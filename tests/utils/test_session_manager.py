import pytest

from utils.session_manager import SessionManager


@pytest.fixture()
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(SessionManager, "SESSIONS_DIR", tmp_path)
    m = SessionManager("sess-1")
    m.session_path.mkdir(parents=True, exist_ok=True)
    return m


def test_load_progress_default_has_comments(manager):
    assert manager.load_progress()["comments"] == {}


def test_save_comment_round_trip(manager):
    manager.save_comment("doc-1", "k1", "looks off")
    assert manager.load_progress()["comments"]["doc-1"]["k1"] == "looks off"


def test_blank_comment_prunes_entry_and_empty_doc_map(manager):
    manager.save_comment("doc-1", "k1", "note")
    manager.save_comment("doc-1", "k1", "   ")
    assert "doc-1" not in manager.load_progress()["comments"]


def test_blank_comment_keeps_sibling_key(manager):
    manager.save_comment("doc-1", "k1", "note one")
    manager.save_comment("doc-1", "k2", "note two")
    manager.save_comment("doc-1", "k1", "")
    comments = manager.load_progress()["comments"]
    assert comments["doc-1"] == {"k2": "note two"}


def test_save_comment_tolerates_legacy_progress_without_comments(manager):
    # simulate an old progress.json lacking the comments key
    manager.save_progress(
        {"current_file_index": 0, "files": [], "results": {}, "completed_files": []}
    )
    manager.save_comment("doc-1", "k1", "added later")
    assert manager.load_progress()["comments"]["doc-1"]["k1"] == "added later"


def test_save_results_clear_keys_removes_cleared_verdict(manager):
    manager.save_results("docX", {"a.b": "PRESENT_CORRECT", "a.c": "PRESENT_INCORRECT"})
    manager.save_results("docX", {"a.c": "PRESENT_INCORRECT"}, clear_keys=["a.b"])
    doc = manager.load_progress()["results"]["docX"]
    assert "a.b" not in doc
    assert doc["a.c"] == "PRESENT_INCORRECT"


def test_save_results_clear_last_key_removes_document_entry(manager):
    manager.save_results("docX", {"a.b": "PRESENT_CORRECT"})
    manager.save_results("docX", {}, clear_keys=["a.b"])
    assert "docX" not in manager.load_progress()["results"]


from utils.models import FieldSelection, Session
from utils.schema_inspector import SchemaInspector
from utils.session_manager import migrate_results_to_paths


def _session(selections):
    return Session(
        id="t", name="t", schema_module="oncollamaschemav3",
        root_class="OncoLlamaModel", predictions_folder=".", sample_size=1,
        selections=selections,
    )


def test_migration_remaps_scalar_field_and_drops_whole_class():
    inspector = SchemaInspector("oncollamaschemav3", "OncoLlamaModel")
    session = _session([
        FieldSelection(selection_type="basemodel_field",
                       class_name="PrimaryCancerFacts", field_name="topography"),
        FieldSelection(selection_type="basemodel_class", class_name="PrimaryCancer"),
    ])
    progress = {
        "results": {
            "doc1": {
                "basemodel_field_PrimaryCancerFacts_topography": "PRESENT_CORRECT",
                "basemodel_class_PrimaryCancer": "PRESENT_CORRECT",  # unrecoverable
            }
        },
        "completed_files": [], "comments": {},
    }
    migrated, dropped = migrate_results_to_paths(progress, session, inspector)
    doc = migrated["results"]["doc1"]
    assert doc["primary_cancer.primary_cancer_facts.topography"] == "PRESENT_CORRECT"
    assert "basemodel_field_PrimaryCancerFacts_topography" not in doc
    assert "basemodel_class_PrimaryCancer" not in doc
    assert "basemodel_class_PrimaryCancer" in dropped


def test_migration_carries_over_enum_value_verdict():
    inspector = SchemaInspector("oncollamaschemav3", "OncoLlamaModel")
    session = _session([
        FieldSelection(selection_type="enum_value",
                       class_name="BiomarkerStatus", enum_value="altered"),
    ])
    progress = {
        "results": {
            "doc1": {"enum_value_BiomarkerStatus_altered": "PRESENT_CORRECT"},
        },
        "completed_files": [], "comments": {},
    }
    migrated, dropped = migrate_results_to_paths(progress, session, inspector)
    doc = migrated["results"]["doc1"]
    assert doc["enum::BiomarkerStatus.altered"] == "PRESENT_CORRECT"
    assert "enum_value_BiomarkerStatus_altered" not in doc
    assert dropped == []


def test_migration_drops_list_typed_field_verdict():
    inspector = SchemaInspector("oncollamaschemav3", "OncoLlamaModel")
    session = _session([
        FieldSelection(selection_type="basemodel_field",
                       class_name="PrimaryCancer", field_name="primary_cancer_scores"),
    ])
    progress = {
        "results": {
            "doc1": {"basemodel_field_PrimaryCancer_primary_cancer_scores": "PRESENT_CORRECT"},
        },
        "completed_files": [], "comments": {},
    }
    migrated, dropped = migrate_results_to_paths(progress, session, inspector)
    doc = migrated["results"]["doc1"]
    assert "basemodel_field_PrimaryCancer_primary_cancer_scores" not in doc
    assert doc == {}
    assert "basemodel_field_PrimaryCancer_primary_cancer_scores" in dropped


def test_migration_is_idempotent_on_already_migrated_progress():
    inspector = SchemaInspector("oncollamaschemav3", "OncoLlamaModel")
    session = _session([
        FieldSelection(selection_type="basemodel_field",
                       class_name="PrimaryCancerFacts", field_name="topography"),
    ])
    progress = {
        "results": {
            "doc1": {"primary_cancer.primary_cancer_facts.topography": "PRESENT_CORRECT"},
        },
        "completed_files": [], "comments": {},
        "schema_keys_version": 2,
    }
    migrated, dropped = migrate_results_to_paths(progress, session, inspector)
    doc = migrated["results"]["doc1"]
    assert doc == {"primary_cancer.primary_cancer_facts.topography": "PRESENT_CORRECT"}
    assert dropped == []
    assert migrated["schema_keys_version"] == 2
