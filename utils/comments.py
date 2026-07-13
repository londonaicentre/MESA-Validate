"""
comments.py - Flatten the per-block comments map into display/export rows.
"""

from utils.validation_plan import build_validation_plan, flatten_targets


def _collect_group_titles(groups, out):
    for group in groups:
        out[group.path] = group.class_name
        _collect_group_titles(group.subgroups, out)


def format_comments_rows(progress, selections, inspector):
    """
    Return [{document, section, comment}] sorted by document then section.

    Comments are keyed by group path or target key (see
    ``utils.validation_plan``). ``section`` resolves that key to its readable
    title -- a group's ``class_name`` or a target's ``title`` -- when known,
    otherwise falls back to the raw key so legacy/unknown keys still surface
    to the coordinator.
    """
    plan = build_validation_plan(selections, inspector)
    key_to_title = {}
    _collect_group_titles(plan, key_to_title)
    for target in flatten_targets(plan):
        key_to_title[target.key] = target.title
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
