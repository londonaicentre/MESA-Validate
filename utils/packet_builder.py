"""
packet_builder.py - Build self-contained HTML validation packets

Precomputes validation blocks (Python owns schema introspection) and injects
them plus the validator UI template into a single offline HTML file that
clinicians open directly from a network drive (file:// in Edge).
"""

import json
from datetime import datetime
from pathlib import Path

from utils.glossary import (
    describe_class,
    describe_enum_value,
    describe_field,
    describe_field_by_name,
    enum_field_options,
    load_glossary,
)
from utils.predictions_loader import load_prediction_file
from utils.profile_manager import _slugify
from utils.schema_inspector import SchemaInspector
from utils.validation_plan import build_validation_plan, flatten_targets, resolve_target

TEMPLATE_PATH = Path(__file__).parent / "packet_template.html"
TEXTMATCH_PATH = Path(__file__).parent / "textmatch.js"
PACKET_DATA_PLACEHOLDER = "__PACKET_DATA__"
TEXTMATCH_PLACEHOLDER = "__TEXTMATCH_JS__"


def _target_summary(target, inspector, glossary):
    """Resolve a validation_plan target's one-line summary via qualified glossary keys.

    Targets are distinguished by key prefix (see utils/validation_plan.py
    target_key()):
      - "enum::Class.value" targets store the enum value in field_name.
      - "list::Class" targets have an empty field_name and represent a
        list-item class rather than a single field.
      - everything else is a dotted-path leaf or list-field target keyed by
        "Class.field_name".
    """
    if target.key.startswith("enum::"):
        return describe_enum_value(target.class_name, target.field_name, glossary)
    if target.key.startswith("list::") and not target.field_name:
        return describe_class(target.class_name, inspector, glossary)
    if not target.field_name:
        return None
    return describe_field(target.class_name, target.field_name, inspector, glossary)


def _leaf_nested_class(target, inspector):
    """Class of a single nested-BaseModel leaf (rendered as a card), else None."""
    meta = inspector.get_class_fields(target.class_name).get(target.field_name)
    if meta and meta.get("is_basemodel") and not meta.get("is_list"):
        return meta.get("type")
    return None


def _target_to_dict(t, inspector, glossary):
    d = {
        "key": t.key,
        "kind": t.kind,
        "field_name": t.field_name,
        "title": t.title,
        "summary": _target_summary(t, inspector, glossary),
    }
    if t.kind == "leaf":
        # class context for revealing enum allowed values (scalar leaf or the
        # direct fields of a nested-BaseModel leaf card)
        d["owner_class"] = t.class_name
        d["nested_class"] = _leaf_nested_class(t, inspector)
    else:
        d["item_class"] = getattr(t, "item_class_name", None) or t.class_name
    return d


def _group_to_dict(group, inspector, glossary):
    """Serialize a validation_plan Group (with nested subgroups) to plain dicts."""
    return {
        "path": group.path,
        "class_name": group.class_name,
        "title": group.title,
        "summary": describe_class(group.class_name, inspector, glossary),
        "targets": [_target_to_dict(t, inspector, glossary) for t in group.targets],
        "subgroups": [
            _group_to_dict(sg, inspector, glossary) for sg in group.subgroups
        ],
    }


def _build_enum_options(inspector, glossary):
    """Map ``ClassName.field`` -> enum allowed-value metadata for every enum
    field in the schema, so the packet can reveal permitted values per field."""
    out = {}
    for class_name, info in inspector.classes.items():
        if info.get("type") != "BaseModel":
            continue
        for field_name in inspector.get_class_fields(class_name):
            opts = enum_field_options(class_name, field_name, inspector, glossary)
            if opts:
                out[f"{class_name}.{field_name}"] = opts
    return out


def build_packet_data(session, document_ids, packet_name):
    inspector = SchemaInspector(session.schema_module, session.root_class)
    glossary = load_glossary(session.schema_module)

    plan = build_validation_plan(session.selections, inspector)
    targets = flatten_targets(plan)
    plan_data = [_group_to_dict(group, inspector, glossary) for group in plan]

    # field-name -> summary, for nested sub-object headings inside cards
    field_glossary = {}
    for _, info in inspector.classes.items():
        if info["type"] != "BaseModel":
            continue
        for field_name in info["class"].model_fields:
            if field_name not in field_glossary:
                summary = describe_field_by_name(field_name, inspector, glossary)
                if summary:
                    field_glossary[field_name] = summary

    documents = []
    for document_id in document_ids:
        prediction = load_prediction_file(document_id, session.predictions_folder)
        inference = prediction.get("document_inference") or {}
        blocks = {
            target.key: resolve_target(target, inference, inspector)
            for target in targets
        }
        documents.append(
            {
                "document_id": document_id,
                "content": prediction.get("document_content")
                or "No content available",
                "blocks": blocks,
            }
        )

    return {
        "packet_name": packet_name,
        "session_name": session.name,
        "schema_module": session.schema_module,
        "root_class": session.root_class,
        "predictions_folder": session.predictions_folder,
        "sample_size": session.sample_size,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "plan": plan_data,
        "field_glossary": field_glossary,
        "enum_options": _build_enum_options(inspector, glossary),
        "documents": documents,
    }


def build_packet_html(packet_data):
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    payload = json.dumps(packet_data, ensure_ascii=False).replace("<", "\\u003c")
    return template.replace(
        TEXTMATCH_PLACEHOLDER, TEXTMATCH_PATH.read_text(encoding="utf-8")
    ).replace(PACKET_DATA_PLACEHOLDER, payload)


def write_packet(session, document_ids, packet_name, output_dir=Path("packets")):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = _slugify(packet_name)
    data = build_packet_data(session, document_ids, slug)
    path = output_dir / f"{slug}.html"
    path.write_text(build_packet_html(data), encoding="utf-8")
    return path
