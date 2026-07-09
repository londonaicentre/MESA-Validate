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
