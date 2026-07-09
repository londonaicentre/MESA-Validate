"""
comments.py - Flatten the per-block comments map into display/export rows.
"""

from utils.selection_resolver import selection_title


def format_comments_rows(progress, selections):
    """
    Return [{document, section, comment}] sorted by document then section.

    ``section`` resolves a selection_key to its readable title when known,
    otherwise falls back to the raw key so legacy/unknown keys still surface
    to the coordinator.
    """
    key_to_title = {s.build_key(): selection_title(s) for s in selections}
    rows = []
    for document_id, doc_comments in (progress.get("comments") or {}).items():
        for selection_key, text in doc_comments.items():
            if not text:
                continue
            rows.append(
                {
                    "document": document_id,
                    "section": key_to_title.get(selection_key, selection_key),
                    "comment": text,
                }
            )
    rows.sort(key=lambda r: (r["document"], r["section"]))
    return rows
