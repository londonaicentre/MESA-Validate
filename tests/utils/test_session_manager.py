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
