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
    describe_field_by_name,
    describe_selection,
    load_glossary,
)
from utils.predictions_loader import load_prediction_file
from utils.profile_manager import _slugify
from utils.schema_inspector import SchemaInspector
from utils.selection_resolver import resolve_selection, selection_kind, selection_title

TEMPLATE_PATH = Path(__file__).parent / "packet_template.html"
TEXTMATCH_PATH = Path(__file__).parent / "textmatch.js"
PACKET_DATA_PLACEHOLDER = "__PACKET_DATA__"
TEXTMATCH_PLACEHOLDER = "__TEXTMATCH_JS__"


def build_packet_data(session, document_ids, packet_name):
    inspector = SchemaInspector(session.schema_module, session.root_class)
    glossary = load_glossary(session.schema_module)

    selections_meta = [
        {
            "key": s.build_key(),
            "title": selection_title(s),
            "kind": selection_kind(s, inspector),
            "desc": describe_selection(s, inspector, glossary),
        }
        for s in session.selections
    ]

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
        blocks = {
            s.build_key(): resolve_selection(
                s, prediction.get("document_inference") or {}, inspector
            )
            for s in session.selections
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
        "selections": selections_meta,
        "field_glossary": field_glossary,
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
