# Field Profiles, Packet Export & Validator UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reusable field-selection profiles, self-contained HTML validation packets for zero-install clinician use, jump-to-source + expanded-card UX in both the packet and the Streamlit Validate page, and packet-results import into Analysis.

**Architecture:** Python (Streamlit) remains the coordinator tool and keeps all Pydantic schema introspection; a UI-free `selection_resolver` feeds both the Streamlit validation UI and a packet builder that injects precomputed blocks into a self-contained HTML template. Results use the existing `progress.json` value format everywhere so `utils/metrics.py` is reused untouched.

**Tech Stack:** Python 3.13, Streamlit ≥1.58, Pydantic v2, pytest; plain HTML/CSS/JS (no framework, no build step) for the packet; shared `utils/textmatch.js` for text matching in both UIs.

## Global Constraints

- Python: `.venv/bin/python` (repo venv, Python 3.13). Tests: `.venv/bin/python -m pytest`.
- No new Python dependencies. No CDN/network fetches in any generated HTML (NHS offline `file://` use in Edge).
- Validation value storage format is frozen: binary → `"PRESENT_CORRECT" | "ABSENT_CORRECT" | "PRESENT_INCORRECT" | "ABSENT_INCORRECT"`; list → `{"items": [true|false|null, ...], "missed": <int>}`.
- Packet JSON is embedded with every `<` escaped as `<`; clinical strings only ever enter the DOM via `textContent`.
- Selection keys come from `FieldSelection.build_key()` — never hand-build them.
- `packets/` and `results/` contain clinical data → gitignored. `profiles/` is committed.

---

### Task 1: UI-free selection resolver (extracted from validation_ui)

**Files:**
- Create: `utils/selection_resolver.py`
- Create: `tests/utils/test_selection_resolver.py`
- Modify: `utils/validation_ui.py` (delete inlined resolution logic, call resolver)

**Interfaces:**
- Consumes: `SchemaInspector` (existing), `FieldSelection` (existing), `extract_field_value` (existing).
- Produces: `resolve_selection(selection, extraction_data, inspector) -> dict` returning `{"kind": "list", "items": list}` or `{"kind": "single", "value": Any}`; `selection_title(selection) -> str`; `selection_kind(selection, inspector) -> "list" | "single"`.

- [ ] **Step 1: Write failing tests** (`tests/utils/test_selection_resolver.py`) using the real `oncollamaschemav3` module and hand-built extraction dicts:

```python
import pytest
from utils.models import FieldSelection
from utils.schema_inspector import SchemaInspector
from utils.selection_resolver import resolve_selection, selection_kind, selection_title


@pytest.fixture(scope="module")
def inspector():
    return SchemaInspector("oncollamaschemav3", "OncoLlamaModel")


EXTRACTION = {
    "document_has_primary_cancer_flag": True,
    "primary_cancer": {
        "primary_cancer_facts": {"topography": "lung", "diagnosis_year": 2024},
        "primary_cancer_tumour_facts": {
            "molecular_biomarker_profiles": [
                {"biomarker": "kit", "biomarker_status": "altered"},
                {"biomarker": "braf", "biomarker_status": "negative"},
            ]
        },
        "primary_cancer_timeline_events": [
            {"event_type": "had_surgical_treatment_performed", "event_year": 2019},
            {"event_type": "evidence_of_metastatic_progression", "event_year": 2023},
        ],
    },
    "performance_status": {"ps_scale": "ecog", "ps_score_value": 1},
}


def test_field_resolves_to_single(inspector):
    sel = FieldSelection(selection_type="basemodel_field",
                         class_name="PrimaryCancerFacts", field_name="topography")
    assert resolve_selection(sel, EXTRACTION, inspector) == {"kind": "single", "value": "lung"}


def test_singleton_class_resolves_to_single_dict(inspector):
    sel = FieldSelection(selection_type="basemodel_class", class_name="PerformanceStatus")
    block = resolve_selection(sel, EXTRACTION, inspector)
    assert block["kind"] == "single"
    assert block["value"]["ps_score_value"] == 1


def test_list_class_resolves_to_items(inspector):
    sel = FieldSelection(selection_type="basemodel_class", class_name="MolecularBiomarkerProfile")
    block = resolve_selection(sel, EXTRACTION, inspector)
    assert block["kind"] == "list"
    assert [i["biomarker"] for i in block["items"]] == ["kit", "braf"]


def test_enum_value_filters_items(inspector):
    sel = FieldSelection(selection_type="enum_value", class_name="TimelineEventType",
                         enum_value="evidence_of_metastatic_progression")
    block = resolve_selection(sel, EXTRACTION, inspector)
    assert block["kind"] == "list"
    assert len(block["items"]) == 1 and block["items"][0]["event_year"] == 2023


def test_absent_field_resolves_to_none(inspector):
    sel = FieldSelection(selection_type="basemodel_field",
                         class_name="PrimaryCancerFacts", field_name="tnm_stage")
    assert resolve_selection(sel, EXTRACTION, inspector) == {"kind": "single", "value": None}


def test_selection_kind(inspector):
    assert selection_kind(FieldSelection(selection_type="basemodel_class",
                                         class_name="MolecularBiomarkerProfile"), inspector) == "list"
    assert selection_kind(FieldSelection(selection_type="basemodel_class",
                                         class_name="PerformanceStatus"), inspector) == "single"
    assert selection_kind(FieldSelection(selection_type="basemodel_field",
                                         class_name="PrimaryCancerFacts", field_name="topography"),
                          inspector) == "single"
    assert selection_kind(FieldSelection(selection_type="enum_value", class_name="TimelineEventType",
                                         enum_value="patient_died"), inspector) == "list"


def test_selection_title():
    assert selection_title(FieldSelection(selection_type="basemodel_class", class_name="A")) == "A"
    assert selection_title(FieldSelection(selection_type="basemodel_field",
                                          class_name="A", field_name="b")) == "A.b"
    assert selection_title(FieldSelection(selection_type="enum_value",
                                          class_name="E", enum_value="v")) == "E.v"
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/utils/test_selection_resolver.py -q` → ImportError (module missing).

- [ ] **Step 3: Implement `utils/selection_resolver.py`** by moving the resolution logic out of `generate_validation_block` (lines 229–359 of validation_ui.py):

```python
"""
selection_resolver.py - UI-free resolution of FieldSelections against extraction data

Single source of truth for what data a selection points at; used by the
Streamlit validation UI and by the packet builder.
"""

from typing import get_args, get_origin

from utils.predictions_loader import extract_field_value


def selection_title(selection):
    if selection.selection_type == "basemodel_class":
        return selection.class_name
    if selection.selection_type == "basemodel_field":
        return f"{selection.class_name}.{selection.field_name}"
    return f"{selection.class_name}.{selection.enum_value}"


def selection_kind(selection, inspector):
    """'list' selections validate item-by-item with a missed count; 'single' are binary."""
    if selection.selection_type == "enum_value":
        return "list"
    if selection.selection_type == "basemodel_class" and inspector.is_class_used_as_list_item(
        selection.class_name
    ):
        return "list"
    return "single"


def _collect_list_items(class_name, extraction_data, inspector):
    """Find every List[class_name] field in the schema and pull its items."""
    found_items = []
    for parent_class_name, parent_class_info in inspector.classes.items():
        if parent_class_info["type"] != "BaseModel":
            continue
        parent_class = parent_class_info["class"]
        for field_name, field_info in parent_class.model_fields.items():
            annotation = field_info.annotation
            origin = get_origin(annotation)
            if str(origin) == "typing.Union":
                for arg in get_args(annotation):
                    if arg is not type(None):
                        annotation = arg
                        break
            if get_origin(annotation) is list:
                args = get_args(annotation)
                if args and getattr(args[0], "__name__", None) == class_name:
                    parent_path = inspector.find_class_path(parent_class_name)
                    if parent_path:
                        items = extract_field_value(
                            extraction_data, ".".join(parent_path + [field_name])
                        )
                        if isinstance(items, list):
                            found_items.extend(items)
    return found_items


def _filter_by_enum_value(items, enum_field_name, enum_value):
    if not isinstance(items, list):
        return []
    return [
        item
        for item in items
        if isinstance(item, dict) and item.get(enum_field_name) == enum_value
    ]


def resolve_selection(selection, extraction_data, inspector):
    """
    Resolve a FieldSelection to display-ready data.

    Returns:
        {"kind": "list", "items": [...]} or {"kind": "single", "value": Any}
    """
    if selection.selection_type == "basemodel_class":
        if inspector.is_class_used_as_list_item(selection.class_name):
            return {
                "kind": "list",
                "items": _collect_list_items(
                    selection.class_name, extraction_data or {}, inspector
                ),
            }
        path = inspector.find_class_path(selection.class_name)
        value = (
            extract_field_value(extraction_data or {}, ".".join(path)) if path else None
        )
        return {"kind": "single", "value": value}

    if selection.selection_type == "basemodel_field":
        path = inspector.find_class_path(selection.class_name)
        value = (
            extract_field_value(
                extraction_data or {}, ".".join(path + [selection.field_name])
            )
            if path
            else None
        )
        return {"kind": "single", "value": value}

    if selection.selection_type == "enum_value":
        found_items = []
        for container_class_name, enum_field_name in inspector.find_enum_containers(
            selection.class_name
        ):
            container_path = inspector.find_class_path(container_class_name)
            if container_path:
                items = extract_field_value(
                    extraction_data or {}, ".".join(container_path)
                )
                found_items.extend(
                    _filter_by_enum_value(items, enum_field_name, selection.enum_value)
                )
        return {"kind": "list", "items": found_items}

    raise ValueError(f"Unknown selection_type: {selection.selection_type}")
```

- [ ] **Step 4: Refactor `utils/validation_ui.py`** — `generate_validation_block` becomes a thin wrapper: call `resolve_selection`, keep all `st.*` display behaviour identical (existing display of items/values, `show_item_validation` calls with `show_missed_count=(kind == "list")`). Delete the moved logic and the local `filter_by_enum_value`. Keep public signature unchanged.

- [ ] **Step 5: Run full suite** — `.venv/bin/python -m pytest -q` → all pass (60 existing + 7 new).

- [ ] **Step 6: Commit** — `git add -A && git commit -m "refactor: extract UI-free selection resolver from validation_ui"`

---

### Task 2: Profile manager + default protocol profile

**Files:**
- Create: `utils/profile_manager.py`, `profiles/mesa_protocol_v1.json`
- Create: `tests/utils/test_profile_manager.py`

**Interfaces:**
- Produces: `list_profiles(schema_module=None, profiles_dir=Path("profiles")) -> list[dict]` (each `{"name", "schema_module", "path", "num_selections"}`); `save_profile(name, schema_module, selections, profiles_dir=...) -> Path` (raises `FileExistsError` on duplicate slug); `load_profile(path, inspector) -> tuple[list[FieldSelection], list[str]]` (valid selections, human-readable skipped descriptions).

- [ ] **Step 1: Failing tests**

```python
import json
import pytest
from utils.models import FieldSelection
from utils.profile_manager import list_profiles, load_profile, save_profile
from utils.schema_inspector import SchemaInspector


@pytest.fixture(scope="module")
def inspector():
    return SchemaInspector("oncollamaschemav3", "OncoLlamaModel")


SELECTIONS = [
    FieldSelection(selection_type="basemodel_field", class_name="PrimaryCancerFacts",
                   field_name="topography"),
    FieldSelection(selection_type="basemodel_class", class_name="PerformanceStatus"),
]


def test_save_list_load_round_trip(tmp_path, inspector):
    path = save_profile("My Profile", "oncollamaschemav3", SELECTIONS, profiles_dir=tmp_path)
    assert path.name == "my_profile.json"
    profiles = list_profiles(profiles_dir=tmp_path)
    assert [p["name"] for p in profiles] == ["My Profile"]
    assert profiles[0]["num_selections"] == 2
    valid, skipped = load_profile(path, inspector)
    assert valid == SELECTIONS and skipped == []


def test_list_filters_by_schema_module(tmp_path):
    save_profile("A", "oncollamaschemav3", SELECTIONS, profiles_dir=tmp_path)
    save_profile("B", "otherschema", SELECTIONS, profiles_dir=tmp_path)
    assert [p["name"] for p in list_profiles("oncollamaschemav3", profiles_dir=tmp_path)] == ["A"]


def test_duplicate_name_raises(tmp_path):
    save_profile("A", "m", SELECTIONS, profiles_dir=tmp_path)
    with pytest.raises(FileExistsError):
        save_profile("A", "m", SELECTIONS, profiles_dir=tmp_path)


def test_load_skips_unknown_fields(tmp_path, inspector):
    data = {"name": "Stale", "schema_module": "oncollamaschemav3", "selections": [
        {"selection_type": "basemodel_field", "class_name": "PrimaryCancerFacts",
         "field_name": "topography"},
        {"selection_type": "basemodel_field", "class_name": "PrimaryCancerFacts",
         "field_name": "no_such_field"},
        {"selection_type": "basemodel_class", "class_name": "NoSuchClass"},
        {"selection_type": "enum_value", "class_name": "TimelineEventType",
         "enum_value": "no_such_value"},
    ]}
    path = tmp_path / "stale.json"
    path.write_text(json.dumps(data))
    valid, skipped = load_profile(path, inspector)
    assert len(valid) == 1 and len(skipped) == 3


def test_default_profile_loads_cleanly(inspector):
    profiles = list_profiles("oncollamaschemav3")
    default = next(p for p in profiles if p["name"] == "MESA Protocol v1")
    valid, skipped = load_profile(default["path"], inspector)
    assert skipped == [] and len(valid) == 11
```

- [ ] **Step 2: Verify failure** — `.venv/bin/python -m pytest tests/utils/test_profile_manager.py -q` → ImportError.

- [ ] **Step 3: Implement `utils/profile_manager.py`**

```python
"""
profile_manager.py - Save/load reusable field-selection profiles

A profile is a named, schema-scoped list of FieldSelections stored as JSON
in profiles/. Loading validates each selection against the live schema.
"""

import json
import re
from pathlib import Path

from utils.models import FieldSelection

PROFILES_DIR = Path("profiles")


def _slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not slug:
        raise ValueError(f"Profile name '{name}' has no usable characters")
    return slug


def list_profiles(schema_module=None, profiles_dir=PROFILES_DIR):
    profiles = []
    if not Path(profiles_dir).exists():
        return profiles
    for path in sorted(Path(profiles_dir).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profiles.append(
                {
                    "name": data["name"],
                    "schema_module": data["schema_module"],
                    "path": path,
                    "num_selections": len(data.get("selections", [])),
                }
            )
        except (json.JSONDecodeError, KeyError):
            continue
    if schema_module is not None:
        profiles = [p for p in profiles if p["schema_module"] == schema_module]
    return profiles


def save_profile(name, schema_module, selections, profiles_dir=PROFILES_DIR):
    profiles_dir = Path(profiles_dir)
    profiles_dir.mkdir(parents=True, exist_ok=True)
    path = profiles_dir / f"{_slugify(name)}.json"
    if path.exists():
        raise FileExistsError(f"A profile named '{name}' already exists")
    payload = {
        "name": name,
        "schema_module": schema_module,
        "selections": [s.model_dump() for s in selections],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _selection_is_valid(selection, inspector):
    class_info = inspector.classes.get(selection.class_name)
    if not class_info:
        return False
    if selection.selection_type == "basemodel_class":
        return class_info["type"] == "BaseModel"
    if selection.selection_type == "basemodel_field":
        return (
            class_info["type"] == "BaseModel"
            and selection.field_name in class_info["fields"]
        )
    if selection.selection_type == "enum_value":
        return (
            class_info["type"] == "Enum"
            and selection.enum_value in class_info["values"]
        )
    return False


def load_profile(path, inspector):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    valid, skipped = [], []
    for raw in data.get("selections", []):
        selection = FieldSelection(**raw)
        if _selection_is_valid(selection, inspector):
            valid.append(selection)
        else:
            from utils.selection_resolver import selection_title

            skipped.append(selection_title(selection))
    return valid, skipped
```

- [ ] **Step 4: Create `profiles/mesa_protocol_v1.json`** (verified against the installed schema — all names exist):

```json
{
  "name": "MESA Protocol v1",
  "schema_module": "oncollamaschemav3",
  "selections": [
    {"selection_type": "basemodel_field", "class_name": "PrimaryCancerFacts", "field_name": "topography", "enum_value": null},
    {"selection_type": "basemodel_field", "class_name": "PrimaryCancerFacts", "field_name": "morphology", "enum_value": null},
    {"selection_type": "basemodel_field", "class_name": "PrimaryCancerFacts", "field_name": "diagnosis_year", "enum_value": null},
    {"selection_type": "basemodel_field", "class_name": "PrimaryCancerFacts", "field_name": "diagnosis_month", "enum_value": null},
    {"selection_type": "basemodel_field", "class_name": "PrimaryCancerFacts", "field_name": "tnm_stage", "enum_value": null},
    {"selection_type": "basemodel_class", "class_name": "MolecularBiomarkerProfile", "field_name": null, "enum_value": null},
    {"selection_type": "basemodel_class", "class_name": "PerformanceStatus", "field_name": null, "enum_value": null},
    {"selection_type": "enum_value", "class_name": "TimelineEventType", "field_name": null, "enum_value": "experienced_toxicity_or_complication_related_to_treatment"},
    {"selection_type": "enum_value", "class_name": "TimelineEventType", "field_name": null, "enum_value": "evidence_of_metastatic_progression"},
    {"selection_type": "enum_value", "class_name": "TimelineEventType", "field_name": null, "enum_value": "radiology_evidence_of_disease_progression"},
    {"selection_type": "enum_value", "class_name": "TimelineEventType", "field_name": null, "enum_value": "experienced_treatment_reduction_or_stop"}
  ]
}
```

- [ ] **Step 5: Run** — `.venv/bin/python -m pytest tests/utils/test_profile_manager.py -q` → 6 pass; full suite passes.

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: field-selection profiles with MESA protocol default"`

---

### Task 3: Profile UI in wizard Step 2

**Files:**
- Modify: `pages/1_Sessions.py` (Step 2 block, lines 216–318)

**Interfaces:**
- Consumes: `list_profiles`, `load_profile`, `save_profile` from Task 2.
- Produces: nothing programmatic (UI only). Checkbox keys stay `class_{C}`, `field_{C}_{F}`, `enum_{C}_{V}`.

- [ ] **Step 1: Add profile load UI** at the top of Step 2 (right after `st.subheader("Step 2: Field Selection")`); applying a profile pre-sets the existing checkbox `st.session_state` keys then reruns:

```python
from utils.profile_manager import list_profiles, load_profile, save_profile

# inside step 2, after subheader:
profiles = list_profiles(st.session_state.setup_data["schema_module"])
if profiles:
    pcol1, pcol2 = st.columns([3, 1])
    with pcol1:
        profile_by_name = {p["name"]: p for p in profiles}
        chosen_profile = st.selectbox(
            "Load a profile", options=list(profile_by_name.keys()),
            index=None, placeholder="Choose a saved field profile...",
        )
    with pcol2:
        st.write("")  # vertical alignment
        if st.button("Apply profile", disabled=chosen_profile is None):
            valid, skipped = load_profile(
                profile_by_name[chosen_profile]["path"], inspector
            )
            # clear any existing ticks, then set the profile's
            for k in list(st.session_state.keys()):
                if k.startswith(("class_", "field_", "enum_")):
                    st.session_state[k] = False
            for sel in valid:
                if sel.selection_type == "basemodel_class":
                    st.session_state[f"class_{sel.class_name}"] = True
                elif sel.selection_type == "basemodel_field":
                    st.session_state[f"field_{sel.class_name}_{sel.field_name}"] = True
                else:
                    st.session_state[f"enum_{sel.class_name}_{sel.enum_value}"] = True
            if skipped:
                st.session_state["profile_skipped"] = skipped
            st.rerun()
if st.session_state.pop("profile_skipped", None) is not None:
    pass  # replaced below — see note
```

Note: show skip warning by reading without popping before widgets render:

```python
skipped = st.session_state.pop("profile_skipped", [])
if skipped:
    st.warning(
        "Skipped selections not in this schema: " + ", ".join(skipped)
    )
```

- [ ] **Step 2: Add save UI** just above the Back/Next buttons (after selections are collected):

```python
with st.container():
    scol1, scol2 = st.columns([3, 1])
    with scol1:
        new_profile_name = st.text_input(
            "Save current selection as profile",
            placeholder="e.g., MESA Protocol v2",
            label_visibility="collapsed",
        )
    with scol2:
        if st.button("Save profile", disabled=not new_profile_name or not selections):
            try:
                save_profile(
                    new_profile_name,
                    st.session_state.setup_data["schema_module"],
                    selections,
                )
                st.success(f"Profile '{new_profile_name}' saved")
            except (FileExistsError, ValueError) as e:
                st.error(str(e))
```

- [ ] **Step 3: Manual check** — `.venv/bin/streamlit run Home.py` via preview: create session → Step 2 → apply "MESA Protocol v1" → 11 boxes ticked; tweak one, save under new name → file appears in `profiles/`.

- [ ] **Step 4: Full test suite still green; commit** — `git commit -m "feat: load/save field-selection profiles in session wizard"`

---

### Task 4: Shared text-matching JS

**Files:**
- Create: `utils/textmatch.js`
- Create: `tests/utils/test_textmatch.py` (runs the JS core under `node` if present, else skips)

**Interfaces:**
- Produces (JS, attached to `window.TextMatch` and usable in plain script context):
  - `findMatches(docText, query) -> {strategy: "exact"|"normalized"|"fuzzy"|null, ranges: [{start, end}]}` (char offsets into `docText`; empty ranges + null strategy when no match)
  - `isExcerptField(fieldName, value) -> bool` (locate-chip heuristic)

- [ ] **Step 1: Write `utils/textmatch.js`** — pure functions, no DOM access, so both the packet and the Streamlit iframe can use them and node can test them:

```javascript
/* textmatch.js - shared text matching for jump-to-source (packet + Streamlit pane) */
(function (global) {
  "use strict";

  function isExcerptField(fieldName, value) {
    if (typeof value !== "string" || value.trim().length === 0) return false;
    if (/_desc$|_name_desc$|_summary$/.test(fieldName)) return true;
    return value.trim().length >= 12;
  }

  function exactRanges(docText, query) {
    var ranges = [];
    var hay = docText.toLowerCase();
    var needle = query.toLowerCase().trim();
    if (!needle) return ranges;
    var from = 0, idx;
    while ((idx = hay.indexOf(needle, from)) !== -1) {
      ranges.push({ start: idx, end: idx + needle.length });
      from = idx + needle.length;
    }
    return ranges;
  }

  /* Collapse whitespace runs but remember original offsets. */
  function normalizedRanges(docText, query) {
    var chars = [], map = [];
    var prevSpace = false;
    for (var i = 0; i < docText.length; i++) {
      var ch = docText[i];
      if (/\s/.test(ch)) {
        if (!prevSpace) { chars.push(" "); map.push(i); }
        prevSpace = true;
      } else {
        chars.push(ch.toLowerCase()); map.push(i);
        prevSpace = false;
      }
    }
    var normDoc = chars.join("");
    var normQuery = query.toLowerCase().trim().replace(/\s+/g, " ");
    if (!normQuery) return [];
    var ranges = [], from = 0, idx;
    while ((idx = normDoc.indexOf(normQuery, from)) !== -1) {
      ranges.push({ start: map[idx], end: map[idx + normQuery.length - 1] + 1 });
      from = idx + normQuery.length;
    }
    return ranges;
  }

  function tokenize(text) {
    var tokens = [], re = /[a-z0-9]+/gi, m;
    while ((m = re.exec(text)) !== null) {
      tokens.push({ text: m[0].toLowerCase(), start: m.index, end: m.index + m[0].length });
    }
    return tokens;
  }

  /* Best window of doc tokens covering >=60% of query tokens. */
  function fuzzyRange(docText, query) {
    var queryTokens = tokenize(query).map(function (t) { return t.text; });
    if (queryTokens.length === 0) return null;
    var docTokens = tokenize(docText);
    var windowSize = Math.max(queryTokens.length, 3);
    var best = null;
    for (var i = 0; i + windowSize <= docTokens.length + 1 && i < docTokens.length; i++) {
      var window = docTokens.slice(i, i + windowSize);
      var windowSet = {};
      window.forEach(function (t) { windowSet[t.text] = true; });
      var hits = 0;
      queryTokens.forEach(function (q) { if (windowSet[q]) hits++; });
      if (best === null || hits > best.hits) {
        best = { hits: hits, start: window[0].start, end: window[window.length - 1].end };
      }
    }
    if (!best || best.hits < Math.ceil(queryTokens.length * 0.6)) return null;
    return { start: best.start, end: best.end };
  }

  function findMatches(docText, query) {
    var ranges = exactRanges(docText, query);
    if (ranges.length) return { strategy: "exact", ranges: ranges };
    ranges = normalizedRanges(docText, query);
    if (ranges.length) return { strategy: "normalized", ranges: ranges };
    var fuzzy = fuzzyRange(docText, query);
    if (fuzzy) return { strategy: "fuzzy", ranges: [fuzzy] };
    return { strategy: null, ranges: [] };
  }

  global.TextMatch = {
    findMatches: findMatches,
    isExcerptField: isExcerptField,
  };
})(typeof window !== "undefined" ? window : globalThis);
```

- [ ] **Step 2: Node-backed pytest** (`tests/utils/test_textmatch.py`):

```python
import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
JS = Path("utils/textmatch.js").resolve()


def run_match(doc, query):
    script = (
        f"require({json.dumps(str(JS))});"
        "const r = globalThis.TextMatch.findMatches("
        f"{json.dumps(doc)}, {json.dumps(query)});"
        "console.log(JSON.stringify(r));"
    )
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


@pytest.mark.skipif(NODE is None, reason="node not installed")
class TestFindMatches:
    def test_exact_match(self):
        r = run_match("The post-operative recovery was slow.", "The post-operative recovery")
        assert r["strategy"] == "exact"
        assert r["ranges"] == [{"start": 0, "end": 27}]

    def test_case_insensitive(self):
        assert run_match("KIT exon 11 mutation", "kit exon 11")["strategy"] == "exact"

    def test_whitespace_normalized(self):
        r = run_match("recovery was\n   complicated by ileus", "recovery was complicated")
        assert r["strategy"] == "normalized"
        assert len(r["ranges"]) == 1

    def test_fuzzy(self):
        r = run_match(
            "The patient was discharged on post-operative day 8 after an ileus.",
            "discharged post-operative day eight ileus",
        )
        assert r["strategy"] == "fuzzy"

    def test_no_match(self):
        r = run_match("Cardiology consultation note.", "pancreatic adenocarcinoma metastasis")
        assert r == {"strategy": None, "ranges": []}
```

(Note: `require()` of a bare script executes it; the IIFE attaches to `globalThis`.)

- [ ] **Step 3: Run** — `.venv/bin/python -m pytest tests/utils/test_textmatch.py -v` → pass (or all-skip if node missing; node exists on this machine).

- [ ] **Step 4: Commit** — `git commit -m "feat: shared text-matching JS for jump-to-source"`

---

### Task 5: Streamlit Validate page — expanded cards + jump-to-source

**Files:**
- Modify: `utils/validation_ui.py` (card renderer replaces `st.json`; locate buttons)
- Create: `utils/document_pane.py`
- Modify: `pages/2_Validate.py` (document pane → component; highlight state)

**Interfaces:**
- Consumes: `TextMatch.findMatches` (Task 4), `resolve_selection` (Task 1).
- Produces: `render_entity_card(item, key_prefix)` in validation_ui (renders dict as label/value rows + locate buttons); `render_document_pane(content, highlight_query, height=800)` in document_pane.

- [ ] **Step 1: Card renderer in `utils/validation_ui.py`** — replace every `st.json(item, expanded=False)` (three call sites: `display_field_value` list branch, `display_field_value` dict branch, `show_item_validation` item loop):

```python
import html as html_lib

EXCERPT_SUFFIXES = ("_desc", "_name_desc", "_summary")


def _is_excerpt_field(field_name, value):
    if not isinstance(value, str) or not value.strip():
        return False
    if field_name.endswith(EXCERPT_SUFFIXES):
        return True
    return len(value.strip()) >= 12


def _set_highlight(value):
    st.session_state["highlight_query"] = value


def render_entity_card(item, key_prefix):
    """Render a dict as a fully-expanded card; excerpt values get locate buttons."""
    if not isinstance(item, dict):
        st.markdown(f"{html_lib.escape(str(item))}")
        return
    rows = []
    excerpts = []
    for field_name, value in item.items():
        if value is None:
            rendered = "<span class='mesa-null'>—</span>"
        else:
            rendered = html_lib.escape(str(value))
        rows.append(
            f"<div class='mesa-row'><span class='mesa-label'>{html_lib.escape(field_name)}</span>"
            f"<span class='mesa-value'>{rendered}</span></div>"
        )
        if _is_excerpt_field(field_name, value):
            excerpts.append((field_name, value))
    st.markdown(
        f"<div class='mesa-card'>{''.join(rows)}</div>", unsafe_allow_html=True
    )
    for field_name, value in excerpts:
        st.button(
            f"🔎 locate: {value[:60]}{'…' if len(value) > 60 else ''}",
            key=f"{key_prefix}_locate_{field_name}",
            on_click=_set_highlight,
            args=(value,),
        )
```

`.mesa-card/.mesa-row/.mesa-label/.mesa-value/.mesa-null` styles are appended to `VALIDATE_PAGE_STYLES` in `utils/styles.py` (card: light border + padding; label: 600 weight, muted, 40% width; null: #999 italic). `on_click` callbacks run **before** the rerun renders, so the document pane picks up `highlight_query` in the same rerun.

Call sites change to `render_entity_card(item, key_prefix=...)`; `show_item_validation` gains a `key_prefix`-derived card key (`f"{key_prefix}_card_{i}"`); `display_field_value` gets an optional `key_prefix=""` parameter for its dict/list branches.

- [ ] **Step 2: `utils/document_pane.py`** — iframe component with shared JS:

```python
"""
document_pane.py - document text pane with highlight + scroll (Streamlit component)
"""

import html as html_lib
import json
from pathlib import Path

import streamlit.components.v1 as components

TEXTMATCH_JS = (Path(__file__).parent / "textmatch.js").read_text(encoding="utf-8")


def render_document_pane(content, highlight_query=None, height=800):
    doc_json = json.dumps(content).replace("<", "\\u003c")
    query_json = json.dumps(highlight_query or "").replace("<", "\\u003c")
    page = f"""
<style>
  body {{ margin: 0; font-family: "Source Sans Pro", sans-serif; }}
  #doc {{ white-space: pre-wrap; word-wrap: break-word; padding: 10px;
         background: #f5f5f5; border: 1px solid #ddd; border-radius: 5px;
         font-size: 0.95rem; line-height: 1.5; }}
  mark {{ background: #ffd54d; padding: 0 1px; }}
  mark.active {{ background: #ff9800; }}
  #notfound {{ background: #fff3cd; border: 1px solid #ffe08a; padding: 6px 10px;
               border-radius: 4px; margin-bottom: 8px; font-size: 0.85rem; }}
</style>
<div id="banner"></div>
<div id="doc"></div>
<script>{TEXTMATCH_JS}</script>
<script>
  const docText = {doc_json};
  const query = {query_json};
  const docEl = document.getElementById("doc");
  const banner = document.getElementById("banner");
  if (!query) {{
    docEl.textContent = docText;
  }} else {{
    const m = TextMatch.findMatches(docText, query);
    if (!m.ranges.length) {{
      docEl.textContent = docText;
      banner.innerHTML = '<div id="notfound">Text not found verbatim in document</div>';
    }} else {{
      let cursor = 0;
      m.ranges.forEach((r, i) => {{
        docEl.appendChild(document.createTextNode(docText.slice(cursor, r.start)));
        const mark = document.createElement("mark");
        if (i === 0) mark.className = "active";
        mark.textContent = docText.slice(r.start, r.end);
        docEl.appendChild(mark);
        cursor = r.end;
      }});
      docEl.appendChild(document.createTextNode(docText.slice(cursor)));
      const first = docEl.querySelector("mark");
      if (first) first.scrollIntoView({{ block: "center" }});
    }}
  }}
</script>
"""
    components.html(page, height=height, scrolling=True)
```

- [ ] **Step 3: Wire into `pages/2_Validate.py`** — replace the `doc_col` body (`st.container(height=800)` + markdown div) with:

```python
with doc_col:
    st.markdown("### Document")
    highlight = st.session_state.get("highlight_query")
    if highlight:
        hcol1, hcol2 = st.columns([5, 1])
        with hcol1:
            st.caption(f"Highlighting: “{highlight[:80]}”")
        with hcol2:
            if st.button("Clear", key="clear_highlight"):
                st.session_state["highlight_query"] = None
                st.rerun()
    render_document_pane(
        prediction_data.get("document_content", "No content available"),
        highlight_query=highlight,
        height=800,
    )
```

Also clear `highlight_query` in the Previous/Next button handlers (stale highlights across documents).

- [ ] **Step 4: Manual verification via preview** — load `test_val`-style session, confirm: cards fully expanded (no JSON triangles), locate button highlights + scrolls doc pane, no-match banner shows for fabricated text, results still save to progress.json.

- [ ] **Step 5: Full pytest; commit** — `git commit -m "feat: expanded entity cards and jump-to-source in Validate page"`

---

### Task 6: Packet builder (data + HTML generation)

**Files:**
- Create: `utils/packet_builder.py`
- Create: `tests/utils/test_packet_builder.py`
- Modify: `.gitignore` (add `packets/`, `results/`)
- (Template file itself is Task 7; this task creates builder + a minimal placeholder template so tests can run.)

**Interfaces:**
- Consumes: `resolve_selection`, `selection_title`, `selection_kind` (Task 1); `load_prediction_file` (existing); `SchemaInspector`.
- Produces:
  - `build_packet_data(session, document_ids, packet_name) -> dict` (spec's packet-data shape; blocks keyed by `selection.build_key()`)
  - `build_packet_html(packet_data) -> str`
  - `write_packet(session, document_ids, packet_name, output_dir=Path("packets")) -> Path`
  - `PACKET_DATA_PLACEHOLDER = "__PACKET_DATA__"`, `TEXTMATCH_PLACEHOLDER = "__TEXTMATCH_JS__"`

- [ ] **Step 1: Failing tests**

```python
import json
import re
from pathlib import Path

import pytest
from utils.models import FieldSelection, Session
from utils.packet_builder import build_packet_data, build_packet_html, write_packet


@pytest.fixture()
def session():
    return Session(
        id="test-session-id",
        name="test_val",
        schema_module="oncollamaschemav3",
        root_class="OncoLlamaModel",
        predictions_folder="predictions/test",
        sample_size=8,
        selections=[
            FieldSelection(selection_type="basemodel_field",
                           class_name="PrimaryCancerFacts", field_name="topography"),
            FieldSelection(selection_type="basemodel_class",
                           class_name="MolecularBiomarkerProfile"),
            FieldSelection(selection_type="enum_value", class_name="TimelineEventType",
                           enum_value="evidence_of_metastatic_progression"),
        ],
    )


@pytest.fixture()
def document_ids(session):
    from utils.predictions_loader import get_prediction_files
    return get_prediction_files(session.predictions_folder)[:2]


def test_packet_data_shape(session, document_ids):
    data = build_packet_data(session, document_ids, "dr_smith")
    assert data["packet_name"] == "dr_smith"
    assert data["session_name"] == "test_val"
    assert len(data["documents"]) == 2
    assert len(data["selections"]) == 3
    keys = {s["key"] for s in data["selections"]}
    doc = data["documents"][0]
    assert set(doc["blocks"]) == keys
    assert isinstance(doc["content"], str) and doc["document_id"]
    kinds = {s["key"]: s["kind"] for s in data["selections"]}
    for key, block in doc["blocks"].items():
        assert block["kind"] == kinds[key]


def test_html_embeds_escaped_json(session, document_ids):
    data = build_packet_data(session, document_ids, "dr_smith")
    data["documents"][0]["content"] = 'evil </script><script>alert(1)</script>'
    html = build_packet_html(data)
    payload = re.search(
        r'<script type="application/json" id="packet-data">(.*?)</script>',
        html, re.DOTALL,
    ).group(1)
    assert "</script>" not in payload.replace("<\\/script>", "")  # no raw close tag
    assert "<" not in payload  # all < escaped as <
    assert json.loads(payload)["documents"][0]["content"].startswith("evil ")


def test_write_packet(tmp_path, session, document_ids):
    path = write_packet(session, document_ids, "Dr Smith", output_dir=tmp_path)
    assert path == tmp_path / "dr_smith.html"
    assert "packet-data" in path.read_text(encoding="utf-8")


def test_unknown_document_id_raises(session):
    with pytest.raises(FileNotFoundError):
        build_packet_data(session, ["nope"], "x")
```

- [ ] **Step 2: Verify failure**, then **Step 3: Implement `utils/packet_builder.py`**

```python
"""
packet_builder.py - Build self-contained HTML validation packets

Precomputes validation blocks (Python owns schema introspection) and injects
them plus the validator UI template into a single offline HTML file.
"""

import json
from datetime import datetime
from pathlib import Path

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

    selections_meta = [
        {
            "key": s.build_key(),
            "title": selection_title(s),
            "kind": selection_kind(s, inspector),
        }
        for s in session.selections
    ]

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
                "content": prediction.get("document_content") or "No content available",
                "blocks": blocks,
            }
        )

    return {
        "packet_name": packet_name,
        "session_name": session.name,
        "schema_module": session.schema_module,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "selections": selections_meta,
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
```

`_slugify` moves to a shared spot? No — import from profile_manager is fine (documented import, avoids duplication).

Minimal placeholder template (replaced in Task 7) so tests pass:

```html
<!doctype html>
<html><head><meta charset="utf-8"><title>MESA Validate Packet</title></head>
<body>
<script>__TEXTMATCH_JS__</script>
<script type="application/json" id="packet-data">__PACKET_DATA__</script>
</body></html>
```

- [ ] **Step 4: Add to `.gitignore`**: `packets/` and `results/` lines.
- [ ] **Step 5: Run tests; full suite; commit** — `git commit -m "feat: packet builder generating self-contained HTML data payloads"`

---

### Task 7: Packet validator template (the clinician UI)

**Files:**
- Modify: `utils/packet_template.html` (replace placeholder with full app)

**Interfaces:**
- Consumes: embedded JSON (`#packet-data`, escaped per Task 6), `TextMatch` (inlined at `__TEXTMATCH_JS__`).
- Produces: results JSON file per spec: `{packet_name, session_name, schema_module, saved_at, completed_files: [...], results: {document_id: {selection_key: value}}}` with frozen value formats.

Single HTML file; all CSS/JS inline; no external requests. Structure and behaviour:

- [ ] **Step 1: Layout + state.** Sticky header: packet name, `Document x of y`, completed count, save-state chip, buttons `Save results` / `Load results file` / `Download results`. Body: doc nav row (`◀ Previous`, jump `<select>` listing `document_id`s with ✓ markers, `Next ▶`), then two panes (CSS grid `1fr 1fr`, each `overflow-y: auto`, height `calc(100vh - header - nav)`): `#doc-pane` and `#val-pane`. Core state module:

```javascript
const DATA = JSON.parse(document.getElementById("packet-data").textContent);
const STORE_KEY = "mesa-packet:" + DATA.packet_name + ":" + DATA.created_at;
let state = {
  currentIndex: 0,
  results: {},          // document_id -> selection_key -> value (frozen formats)
  completed: [],        // document_ids
  savedAt: null,
  dirty: false,
};
let fileHandle = null;  // remembered showSaveFilePicker handle

function loadLocal() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) {
      const saved = JSON.parse(raw);
      state.results = saved.results || {};
      state.completed = saved.completed_files || [];
      state.savedAt = saved.saved_at || null;
    }
  } catch (e) { showBanner("localStorage unavailable — save manually and often."); }
}
function persistLocal() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(resultsPayload()));
  } catch (e) { /* banner once */ }
}
function resultsPayload() {
  return {
    packet_name: DATA.packet_name,
    session_name: DATA.session_name,
    schema_module: DATA.schema_module,
    saved_at: new Date().toISOString(),
    completed_files: state.completed,
    results: state.results,
  };
}
function setValue(documentId, selectionKey, value) {
  (state.results[documentId] = state.results[documentId] || {})[selectionKey] = value;
  state.dirty = true;
  persistLocal();
  updateHeader();
}
```

- [ ] **Step 2: Rendering.** `renderDocument(index)` fills both panes for `DATA.documents[index]`:
  - Doc pane: `#doc-text` div (`white-space: pre-wrap`), populated via `textContent`.
  - Val pane: one section per `DATA.selections`; `block.kind === "single"` → one entity card (dict → label/value rows built with `createElement` + `textContent`; null → dimmed `—`; missing value entirely → "Not present" note) + 3-way radio (None/Correct/Incorrect). Radio maps exactly like Streamlit: presence test = value not null/empty-string/empty-array/empty-object; Correct → `PRESENT_CORRECT`/`ABSENT_CORRECT`, Incorrect → `PRESENT_INCORRECT`/`ABSENT_INCORRECT`, None → delete the key.
  - `block.kind === "list"` → card per item each with its own radio (None→`null`, Correct→`true`, Incorrect→`false`, stored at its index in `items`) + one `missed` number input per section; value stored as `{items: [...], missed: n}`. A list value where every item radio is None and missed is 0 is treated as "no answer" and the key is deleted (mirrors Streamlit's non-none filter).
  - Every excerpt-like string value (`TextMatch.isExcerptField(fieldName, value)`) renders with a `🔎` locate chip.
  - "Mark document as fully validated" checkbox at the bottom of the val pane toggles membership in `state.completed`.
- [ ] **Step 3: Jump-to-source.** Locate chip click → `TextMatch.findMatches(docText, value)` → wrap ranges in `<mark>` (rebuild `#doc-text` from text nodes + marks, never innerHTML), scroll first into view (`scrollIntoView({block:"center"})`), repeated clicks on the same chip cycle the `active` mark through occurrences. No match → transient "not found verbatim" tooltip on the chip. Fuzzy match → mark gets a dashed underline style + `title="approximate match"`.
- [ ] **Step 4: Save/load.**

```javascript
async function saveResults() {
  const payload = JSON.stringify(resultsPayload(), null, 2);
  if ("showSaveFilePicker" in window) {
    try {
      if (!fileHandle) {
        fileHandle = await window.showSaveFilePicker({
          suggestedName: DATA.packet_name + "_results.json",
          types: [{ description: "JSON", accept: { "application/json": [".json"] } }],
        });
      }
      const writable = await fileHandle.createWritable();
      await writable.write(payload);
      await writable.close();
      markSaved("Saved to " + fileHandle.name);
      return;
    } catch (e) {
      if (e.name === "AbortError") return;   // user cancelled — keep dirty
      fileHandle = null;                      // fall through to download
    }
  }
  downloadResults(payload);
}
function downloadResults(payload) {
  payload = payload || JSON.stringify(resultsPayload(), null, 2);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([payload], { type: "application/json" }));
  a.download = DATA.packet_name + "_results.json";
  a.click();
  URL.revokeObjectURL(a.href);
  markSaved("Downloaded " + a.download);
}
```

  `Load results file` → hidden `<input type="file">`; parse JSON; sanity-check `packet_name` matches (warn + confirm on mismatch); if localStorage state exists, keep whichever `saved_at` is newer and tell the user which won. `beforeunload` warns when `state.dirty`.
- [ ] **Step 5: Verify in browser** (covered again in Task 10): open a generated packet via `file://`, radios persist across reload, save produces valid JSON, locate works for exact/normalized/fuzzy/no-match.
- [ ] **Step 6: Commit** — `git commit -m "feat: clinician validator UI in packet template"`

---

### Task 8: Export-packet panel on Sessions page

**Files:**
- Modify: `pages/1_Sessions.py` (active-session block, lines 31–46)

**Interfaces:**
- Consumes: `write_packet` (Task 6), `SessionManager(session.id).load_progress()` / `initialize_files` (existing) for the valid document list.

- [ ] **Step 1: Add expander under the active-session banner:**

```python
from utils.packet_builder import write_packet

if st.session_state.active_session:
    session = st.session_state.active_session
    # ... existing Start Validation / Close Session buttons ...

    with st.expander("Export validation packet"):
        manager = SessionManager(session.id)
        progress, _ = manager.initialize_files(session)
        available_ids = progress["files"]

        packet_name = st.text_input(
            "Packet name (e.g. clinician name)", key="packet_name"
        )
        pasted = st.text_area(
            "Document IDs (optional — paste newline/comma-separated to preselect)",
            key="packet_paste", height=68,
        )
        preselected = [t.strip() for t in pasted.replace(",", "\n").splitlines() if t.strip()]
        unknown = [t for t in preselected if t not in available_ids]
        if unknown:
            st.warning(f"Not in this session (ignored): {', '.join(unknown)}")
        chosen_ids = st.multiselect(
            "Documents to include",
            options=available_ids,
            default=[t for t in preselected if t in available_ids] or available_ids,
            key="packet_docs",
        )
        st.caption(f"{len(chosen_ids)} of {len(available_ids)} documents selected")
        if st.button("Generate packet", disabled=not packet_name or not chosen_ids):
            try:
                path = write_packet(session, chosen_ids, packet_name)
                st.success(f"Packet written to `{path}` — copy it to the network drive.")
            except Exception as e:
                st.error(f"Error generating packet: {e}")
```

(Default = all documents selected; overwrite is acceptable because the name is the clinician slug and regenerating is the common case — the success message names the exact path.)

- [ ] **Step 2: Manual verify via preview** (packet generates from the test session; file opens).
- [ ] **Step 3: Full pytest; commit** — `git commit -m "feat: export validation packets from Sessions page"`

---

### Task 9: Analysis import of packet results

**Files:**
- Create: `utils/results_import.py`
- Create: `tests/utils/test_results_import.py`
- Modify: `pages/3_Analysis.py`

**Interfaces:**
- Consumes: `aggregate_metrics`, `format_metrics_summary` (existing, unchanged).
- Produces:
  - `parse_results_payload(data: dict) -> tuple[dict, dict]` → `(meta, progress)` where `meta = {"packet_name", "session_name", "schema_module", "saved_at"}` and `progress = {"results": ..., "completed_files": ...}`; raises `ValueError` on missing keys.
  - `combine_progress(parsed: list[tuple[dict, dict]]) -> dict` → single progress dict with keys namespaced `f"{packet_name}::{document_id}"` so the same document validated in two packets contributes twice.

- [ ] **Step 1: Failing tests**

```python
import pytest
from utils.metrics import aggregate_metrics
from utils.models import FieldSelection
from utils.results_import import combine_progress, parse_results_payload

SEL = FieldSelection(selection_type="basemodel_field",
                     class_name="PrimaryCancerFacts", field_name="topography")
KEY = SEL.build_key()

PAYLOAD = {
    "packet_name": "dr_smith",
    "session_name": "test_val",
    "schema_module": "oncollamaschemav3",
    "saved_at": "2026-07-05T10:00:00",
    "completed_files": ["doc-1"],
    "results": {"doc-1": {KEY: "PRESENT_CORRECT"}, "doc-2": {KEY: "PRESENT_INCORRECT"}},
}


def test_parse_results_payload():
    meta, progress = parse_results_payload(PAYLOAD)
    assert meta["packet_name"] == "dr_smith"
    assert progress["completed_files"] == ["doc-1"]
    assert progress["results"]["doc-1"][KEY] == "PRESENT_CORRECT"


def test_parse_rejects_garbage():
    with pytest.raises(ValueError):
        parse_results_payload({"foo": "bar"})


def test_packet_metrics_match_native_progress():
    _, progress = parse_results_payload(PAYLOAD)
    native = {"results": PAYLOAD["results"], "completed_files": ["doc-1"],
              "current_file_index": 0, "files": ["doc-1", "doc-2"]}
    assert aggregate_metrics(progress, [SEL]) == aggregate_metrics(native, [SEL])


def test_combine_progress_namespaces_documents():
    p1 = parse_results_payload(PAYLOAD)
    p2 = parse_results_payload({**PAYLOAD, "packet_name": "dr_jones",
                                "results": {"doc-1": {KEY: "ABSENT_INCORRECT"}},
                                "completed_files": ["doc-1"]})
    combined = combine_progress([p1, p2])
    assert set(combined["completed_files"]) == {"dr_smith::doc-1", "dr_jones::doc-1"}
    metrics = aggregate_metrics(combined, [SEL])
    assert metrics[KEY]["total"] == 2  # both clinicians' doc-1 counted
```

- [ ] **Step 2: Verify failure; Step 3: Implement `utils/results_import.py`**

```python
"""
results_import.py - Import clinician packet results into Analysis

Converts packet results files back into the progress.json shape consumed by
utils/metrics.py.
"""

REQUIRED_KEYS = ("packet_name", "results", "completed_files")


def parse_results_payload(data):
    if not isinstance(data, dict) or any(k not in data for k in REQUIRED_KEYS):
        raise ValueError(
            "Not a MESA packet results file (expected keys: "
            + ", ".join(REQUIRED_KEYS) + ")"
        )
    meta = {
        "packet_name": data["packet_name"],
        "session_name": data.get("session_name", ""),
        "schema_module": data.get("schema_module", ""),
        "saved_at": data.get("saved_at", ""),
    }
    progress = {
        "results": data["results"],
        "completed_files": data["completed_files"],
    }
    return meta, progress


def combine_progress(parsed):
    combined = {"results": {}, "completed_files": []}
    for meta, progress in parsed:
        prefix = meta["packet_name"] + "::"
        for document_id, doc_results in progress["results"].items():
            combined["results"][prefix + document_id] = doc_results
        combined["completed_files"].extend(
            prefix + document_id for document_id in progress["completed_files"]
        )
    return combined
```

- [ ] **Step 4: Analysis page section** — in `pages/3_Analysis.py`, after the session selectbox and before the existing overview, add:

```python
import json
from utils.results_import import combine_progress, parse_results_payload

st.markdown("---")
st.subheader("Import packet results")
uploads = st.file_uploader(
    "Packet results files (*_results.json)", type="json", accept_multiple_files=True
)
parsed_packets = []
for upload in uploads or []:
    try:
        meta, packet_progress = parse_results_payload(json.load(upload))
        if meta["session_name"] and meta["session_name"] != session.name:
            st.warning(
                f"{upload.name}: saved from session '{meta['session_name']}', "
                f"analyzing against '{session.name}'"
            )
        parsed_packets.append((meta, packet_progress))
    except (ValueError, json.JSONDecodeError) as e:
        st.error(f"{upload.name}: {e}")

if parsed_packets:
    for meta, packet_progress in parsed_packets:
        st.markdown(
            f"#### Packet: {meta['packet_name']} "
            f"({len(packet_progress['completed_files'])} completed docs)"
        )
        packet_metrics = aggregate_metrics(packet_progress, session.selections)
        if packet_metrics:
            st.dataframe(pd.DataFrame(format_metrics_summary(packet_metrics)),
                         use_container_width=True, hide_index=True)
        else:
            st.info("No completed results in this packet")
    if len(parsed_packets) > 1:
        st.markdown("#### All packets combined")
        combined = combine_progress(parsed_packets)
        combined_metrics = aggregate_metrics(combined, session.selections)
        st.dataframe(pd.DataFrame(format_metrics_summary(combined_metrics)),
                     use_container_width=True, hide_index=True)
```

(The existing session-progress analysis below stays untouched.)

- [ ] **Step 5: Run tests + full suite; commit** — `git commit -m "feat: import clinician packet results into Analysis"`

---

### Task 10: End-to-end verification + docs

**Files:**
- Modify: `README.md` (profiles, packet workflow, results import sections)

- [ ] **Step 1: Full pytest** — `.venv/bin/python -m pytest -q` → all green.
- [ ] **Step 2: End-to-end via preview:** run the app; create a session with the MESA Protocol v1 profile against `predictions/test`; export a packet for two documents; open `packets/<x>.html` in a real browser (file://); validate one document fully (exact + fuzzy locate, list missed count); save results JSON; upload it on the Analysis page; confirm metrics match the entered values.
- [ ] **Step 3: README** — add "Field profiles", "Deploying to clinicians (validation packets)" (generate → copy to network drive → clinician opens in Edge → save results to `results/`), and "Importing results" sections.
- [ ] **Step 4: Commit** — `git commit -m "docs: profile + packet workflow documentation"`

## Self-review notes

- Spec coverage: profiles (T2/T3), exporter incl. manual doc picker (T6/T8), packet UI incl. jump-to-source/persistence (T4/T7), Streamlit Validate UX (T5), Analysis import (T9), gitignore/data-governance (T6), docs+E2E (T10). Overwrite-confirm for packets was simplified to always-overwrite-with-explicit-path-message (noted in T8) — deviation from spec accepted for wizard simplicity.
- Type consistency: `resolve_selection` block shape (`kind`/`items`/`value`) used identically in T1/T5/T6/T7; results value formats identical in T5/T7/T9; `build_key()` used everywhere.
