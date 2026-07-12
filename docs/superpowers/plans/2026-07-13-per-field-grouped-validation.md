# Per-field Grouped Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the one-block-per-selection validation UI with a grouped, per-field interface where every data point appears exactly once and each leaf field carries its own Correct/Incorrect verdict, with group/class results derived at read time.

**Architecture:** A new `utils/validation_plan.py` reconciles the flat `session.selections` into an ordered, deduplicated tree of validation targets (leaf fields and list fields grouped under their owning schema objects), keyed by canonical dotted data path. Every consumer — the Streamlit Validate page, `metrics.py`, and the offline clinician packet — reads this one structure. Group-level results are derived from leaf verdicts, never stored.

**Tech Stack:** Python 3, Pydantic v2, Streamlit, pytest (with `pytest-mock`), vanilla JS (packet template).

## Global Constraints

- Verdict vocabulary unchanged: `PRESENT_CORRECT`, `ABSENT_CORRECT`, `PRESENT_INCORRECT`, `ABSENT_INCORRECT`, `NOT_APPLICABLE`, and `NONE`/null for unreviewed.
- List target result shape unchanged: `{"items": [true|false|null, ...], "missed": int}`.
- Results are keyed in `progress.json` by **canonical target key** (see Task 1), replacing `FieldSelection.build_key()`.
- Toggle semantics: untouched = unreviewed (`NONE`); ✓ = correct; ✗ = incorrect; clicking the lit icon clears to unreviewed. Presence (present vs absent) is inferred at save time from the extracted value.
- Hierarchy is **nested**: one header per selected class, indented sub-sections for nested objects and list fields.
- Tests use the real schema: `SchemaInspector("oncollamaschemav3", "OncoLlamaModel")`.
- Run tests with `.venv/bin/pytest`. Commit after every task.

---

## File Structure

| File | Responsibility |
|---|---|
| `utils/validation_plan.py` | **New.** Target dataclasses, `build_validation_plan`, `target_key`, `resolve_target`, `flatten_targets`, `summarize_results`. |
| `tests/utils/test_validation_plan.py` | **New.** Unit tests for the plan builder, resolution, and roll-ups. |
| `utils/session_manager.py` | Add one-time best-effort results migration + backup. |
| `tests/utils/test_session_manager.py` | Add migration tests. |
| `utils/metrics.py` | `aggregate_metrics` iterates plan targets; row labels by target. |
| `tests/utils/test_metrics.py` | **New.** Metrics over path-keyed results. |
| `utils/validation_ui.py` | Grouped/nested rendering; ✓/✗ leaf rows; list rows. |
| `pages/2_Validate.py` | Iterate plan groups; filter / comments / save by target key. |
| `utils/comments.py` | Titles keyed by target/group. |
| `utils/packet_builder.py` | Build packet data from the plan (path-keyed). |
| `utils/packet_template.html` | Port grouped ✓/✗ rendering + verdict collection. |
| `pages/1_Sessions.py` | "Select entire class" = all leaf fields; relax sibling-disable. |
| `pages/3_Analysis.py` | Consume path-keyed metrics (mostly transparent). |

---

## Task 1: Validation plan builder — targets, keys, resolution

**Files:**
- Create: `utils/validation_plan.py`
- Test: `tests/utils/test_validation_plan.py`

**Interfaces:**
- Consumes: `utils.schema_inspector.SchemaInspector` (`find_class_path`, `get_class_fields`, `is_class_used_as_list_item`), `utils.selection_resolver.resolve_selection`, `utils.predictions_loader.extract_field_value`, `utils.models.FieldSelection`.
- Produces:
  - `LeafTarget(key, path, field_name, class_name, title)`, `ListTarget(key, path, field_name, class_name, title, source_selection=None)` — dataclasses; each has attribute `kind` = `"leaf"` / `"list"`.
  - `Group(path, class_name, title, targets: list, subgroups: list)`.
  - `build_validation_plan(selections, inspector) -> list[Group]` (ordered top-level groups).
  - `target_key(selection_or_target) -> str`.
  - `resolve_target(target, extraction_data, inspector) -> dict` (`{"kind":"single","value":...}` or `{"kind":"list","items":[...]}`).
  - `flatten_targets(groups) -> list` (all leaf+list targets, depth-first, in render order).

- [ ] **Step 1: Write the failing test**

```python
# tests/utils/test_validation_plan.py
import pytest

from utils.models import FieldSelection
from utils.schema_inspector import SchemaInspector
from utils.validation_plan import (
    build_validation_plan,
    flatten_targets,
    resolve_target,
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
    assert target_key(sel) == "primary_cancer.primary_cancer_facts.topography"


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/utils/test_validation_plan.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'utils.validation_plan'`.

- [ ] **Step 3: Write the implementation**

```python
# utils/validation_plan.py
"""
validation_plan.py - Reconcile flat FieldSelections into an ordered,
deduplicated tree of validation targets.

A plan is a list of top-level Groups. Each Group corresponds to a schema
object (BaseModel) at a dotted data path; it holds ordered leaf/list targets
plus nested subgroups. Every consumer (Validate page, metrics, packet) reads
this one structure so a data point selected via several overlapping selections
is validated exactly once.
"""

from dataclasses import dataclass, field
from typing import Optional

from utils.predictions_loader import extract_field_value
from utils.selection_resolver import resolve_selection


@dataclass
class LeafTarget:
    key: str
    path: str
    field_name: str
    class_name: str
    title: str
    kind: str = "leaf"


@dataclass
class ListTarget:
    key: str
    path: str
    field_name: str
    class_name: str
    title: str
    source_selection: Optional[object] = None  # for enum / list-item-class resolution
    kind: str = "list"


@dataclass
class Group:
    path: str
    class_name: str
    title: str
    targets: list = field(default_factory=list)
    subgroups: list = field(default_factory=list)


def _class_path(class_name, inspector):
    """Dotted data path to a class object, or None if it is not reachable."""
    parts = inspector.find_class_path(class_name)
    return ".".join(parts) if parts else None


def target_key(obj):
    """Canonical results key for a FieldSelection or a target.

    Leaf/list fields -> dotted data path. Enum filters and list-item classes
    have no single path, so they get a stable synthetic key.
    """
    # already-built target
    if isinstance(obj, (LeafTarget, ListTarget)):
        return obj.key
    # FieldSelection
    if obj.selection_type == "enum_value":
        return f"enum::{obj.class_name}.{obj.enum_value}"
    return None  # class/field keys are computed during expansion where paths are known


def _leaf_or_list_target(class_name, field_name, field_meta, class_path):
    path = f"{class_path}.{field_name}"
    if field_meta["is_list"]:
        return ListTarget(
            key=path,
            path=path,
            field_name=field_name,
            class_name=class_name,
            title=f"{class_name}.{field_name}",
        )
    return LeafTarget(
        key=path,
        path=path,
        field_name=field_name,
        class_name=class_name,
        title=f"{class_name}.{field_name}",
    )


class _PlanAccumulator:
    """Builds groups on demand, keyed by object path, preserving first-seen order."""

    def __init__(self, inspector):
        self.inspector = inspector
        self._by_path = {}
        self._order = []
        self._seen_target_keys = set()

    def group_for(self, class_name, class_path):
        if class_path not in self._by_path:
            self._by_path[class_path] = Group(
                path=class_path, class_name=class_name, title=class_name
            )
            self._order.append(class_path)
        return self._by_path[class_path]

    def add_target(self, group, target):
        if target.key in self._seen_target_keys:
            return
        self._seen_target_keys.add(target.key)
        group.targets.append(target)

    def _expand_class(self, class_name):
        """Recurse a BaseModel's fields into its group (leaves/lists) + subgroups."""
        class_path = _class_path(class_name, self.inspector)
        if class_path is None:
            return None
        group = self.group_for(class_name, class_path)
        fields = self.inspector.get_class_fields(class_name)
        for field_name, meta in fields.items():
            if meta["is_basemodel"] and not meta["is_list"]:
                sub = self._expand_class(meta["type"])
                if sub is not None and sub not in group.subgroups:
                    group.subgroups.append(sub)
            else:
                self.add_target(
                    group, _leaf_or_list_target(class_name, field_name, meta, class_path)
                )
        return group

    def add_selection(self, selection):
        insp = self.inspector
        if selection.selection_type == "basemodel_class":
            if insp.is_class_used_as_list_item(selection.class_name):
                key = f"list::{selection.class_name}"
                group = self.group_for(selection.class_name, key)
                self.add_target(
                    group,
                    ListTarget(
                        key=key,
                        path=key,
                        field_name="",
                        class_name=selection.class_name,
                        title=selection.class_name,
                        source_selection=selection,
                    ),
                )
            else:
                self._expand_class(selection.class_name)

        elif selection.selection_type == "basemodel_field":
            class_path = _class_path(selection.class_name, insp)
            if class_path is None:
                return
            group = self.group_for(selection.class_name, class_path)
            meta = insp.get_class_fields(selection.class_name).get(selection.field_name)
            if meta is None:
                return
            self.add_target(
                group, _leaf_or_list_target(selection.class_name, selection.field_name, meta, class_path)
            )

        elif selection.selection_type == "enum_value":
            key = f"enum::{selection.class_name}.{selection.enum_value}"
            group = self.group_for(selection.class_name, f"enum::{selection.class_name}")
            self.add_target(
                group,
                ListTarget(
                    key=key,
                    path=key,
                    field_name=selection.enum_value,
                    class_name=selection.class_name,
                    title=f"{selection.class_name}.{selection.enum_value}",
                    source_selection=selection,
                ),
            )

    def top_level_groups(self):
        return [self._by_path[p] for p in self._order]


def build_validation_plan(selections, inspector):
    """Return an ordered list of top-level Groups for the given selections.

    Nested objects become subgroups (rendered indented); list fields and enum
    filters become list targets; every leaf appears exactly once.
    """
    acc = _PlanAccumulator(inspector)
    for selection in selections:
        acc.add_selection(selection)
    # Subgroups may also have been created as top-level via _class_path collisions;
    # keep only groups that are not nested under another group.
    all_groups = acc.top_level_groups()
    nested_paths = set()
    for g in all_groups:
        _collect_nested_paths(g, nested_paths)
    return [g for g in all_groups if g.path not in nested_paths]


def _collect_nested_paths(group, acc):
    for sg in group.subgroups:
        acc.add(sg.path)
        _collect_nested_paths(sg, acc)


def flatten_targets(groups):
    """All leaf/list targets depth-first in render order."""
    out = []
    for g in groups:
        out.extend(g.targets)
        out.extend(flatten_targets(g.subgroups))
    return out


def resolve_target(target, extraction_data, inspector):
    """Resolve a target to display data, mirroring selection_resolver output."""
    if target.source_selection is not None:
        return resolve_selection(target.source_selection, extraction_data, inspector)
    value = extract_field_value(extraction_data or {}, target.path)
    if target.kind == "list":
        return {"kind": "list", "items": value if isinstance(value, list) else []}
    return {"kind": "single", "value": value}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/utils/test_validation_plan.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add utils/validation_plan.py tests/utils/test_validation_plan.py
git commit -m "feat: validation plan builder with deduplicated target tree"
```

---

## Task 2: Derived roll-ups

**Files:**
- Modify: `utils/validation_plan.py`
- Test: `tests/utils/test_validation_plan.py`

**Interfaces:**
- Consumes: `flatten_targets`, target `kind`/`key` from Task 1.
- Produces: `summarize_results(targets, doc_results) -> {"correct": int, "incorrect": int, "unvalidated": int}` and `group_rollup(group, doc_results) -> same dict` (recursive over a group's own targets + subgroups).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/utils/test_validation_plan.py
from utils.validation_plan import group_rollup, summarize_results


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/utils/test_validation_plan.py::test_summarize_counts_leaves_and_list_items -v`
Expected: FAIL with `ImportError: cannot import name 'summarize_results'`.

- [ ] **Step 3: Add the implementation**

```python
# append to utils/validation_plan.py
def summarize_results(targets, doc_results):
    """Derive correct/incorrect/unvalidated counts from stored leaf verdicts.

    List items count individually; missed items count as incorrect (the model
    failed to extract an expected item).
    """
    correct = incorrect = unvalidated = 0
    doc_results = doc_results or {}
    for t in targets:
        value = doc_results.get(t.key)
        if t.kind == "leaf":
            if not isinstance(value, str) or value in ("", "NONE"):
                unvalidated += 1
            elif value.endswith("_CORRECT"):
                correct += 1
            elif value.endswith("_INCORRECT"):
                incorrect += 1
            else:
                unvalidated += 1
        else:  # list
            items = value.get("items", []) if isinstance(value, dict) else []
            missed = value.get("missed", 0) if isinstance(value, dict) else 0
            if not items and not missed:
                unvalidated += 1
                continue
            for item in items:
                if item is True:
                    correct += 1
                elif item is False:
                    incorrect += 1
                else:
                    unvalidated += 1
            incorrect += int(missed or 0)
    return {"correct": correct, "incorrect": incorrect, "unvalidated": unvalidated}


def group_rollup(group, doc_results):
    """Roll a group (and its subgroups) up to correct/incorrect/unvalidated."""
    return summarize_results(flatten_targets([group]), doc_results)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/utils/test_validation_plan.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add utils/validation_plan.py tests/utils/test_validation_plan.py
git commit -m "feat: derived group roll-ups from leaf verdicts"
```

---

## Task 3: Best-effort results migration

**Files:**
- Modify: `utils/session_manager.py`
- Test: `tests/utils/test_session_manager.py`

**Interfaces:**
- Consumes: `SchemaInspector`, `FieldSelection.build_key()`, `utils.validation_plan.target_key`, `inspector.get_class_fields`, `inspector.find_class_path`.
- Produces: module function `migrate_results_to_paths(progress, session, inspector) -> (progress, dropped_keys: list[str])`, invoked once inside `SessionManager.load_progress` when `progress.get("schema_keys_version") != 2`. Writes a `progress.json.bak` backup before rewriting.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/utils/test_session_manager.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/utils/test_session_manager.py::test_migration_remaps_scalar_field_and_drops_whole_class -v`
Expected: FAIL with `ImportError: cannot import name 'migrate_results_to_paths'`.

- [ ] **Step 3: Add the migration function and wire it in**

Add this module-level function to `utils/session_manager.py` (after imports; also `from utils.schema_inspector import SchemaInspector` and `from utils.validation_plan import target_key`):

```python
def _old_to_new_key(selection, inspector):
    """Map one selection's legacy build_key() to its new target key, or None to drop.

    Drops whole-object-class verdicts (single verdict can't split per field) and
    list-typed field verdicts (single string can't become per-item).
    """
    old = selection.build_key()
    if selection.selection_type == "enum_value":
        return old, f"enum::{selection.class_name}.{selection.enum_value}"
    if selection.selection_type == "basemodel_class":
        if inspector.is_class_used_as_list_item(selection.class_name):
            return old, f"list::{selection.class_name}"
        return old, None  # object class -> unrecoverable
    if selection.selection_type == "basemodel_field":
        meta = inspector.get_class_fields(selection.class_name).get(selection.field_name)
        parts = inspector.find_class_path(selection.class_name)
        if meta is None or not parts or meta["is_list"]:
            return old, None  # list-field single verdict can't migrate
        return old, ".".join(parts + [selection.field_name])
    return old, None


def migrate_results_to_paths(progress, session, inspector):
    """Best-effort in-place remap of legacy build_key() results to path keys.

    Returns (progress, dropped_keys). Idempotent: sets schema_keys_version=2.
    """
    mapping = {}
    for selection in session.selections:
        old, new = _old_to_new_key(selection, inspector)
        mapping[old] = new

    dropped = []
    for _document_id, doc_results in progress.get("results", {}).items():
        remapped = {}
        for old_key, value in doc_results.items():
            new_key = mapping.get(old_key, old_key)
            if new_key is None:
                dropped.append(old_key)
                continue
            remapped[new_key] = value
        doc_results.clear()
        doc_results.update(remapped)

    # comments are keyed by group/selection; remap where we can, else keep
    for _document_id, doc_comments in progress.get("comments", {}).items():
        remapped = {k: v for k, v in (
            (mapping.get(ck, ck), cv) for ck, cv in doc_comments.items()
        ) if k is not None}
        doc_comments.clear()
        doc_comments.update(remapped)

    progress["schema_keys_version"] = 2
    return progress, dropped
```

Then wire it into `load_progress` — after the JSON is loaded and before returning, run migration once. Replace the final `return progress_data` in `load_progress` with:

```python
        if progress_data.get("schema_keys_version") != 2 and progress_data.get("results"):
            try:
                session = self.load_config()
                inspector = SchemaInspector(session.schema_module, session.root_class)
                if self.progress_path.exists():
                    shutil.copyfile(self.progress_path, self.progress_path.with_suffix(".json.bak"))
                progress_data, _dropped = migrate_results_to_paths(
                    progress_data, session, inspector
                )
                self.save_progress(progress_data)
            except Exception:
                pass  # never block loading on migration

        return progress_data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/utils/test_session_manager.py -v`
Expected: PASS (existing tests + the new one).

- [ ] **Step 5: Commit**

```bash
git add utils/session_manager.py tests/utils/test_session_manager.py
git commit -m "feat: best-effort migration of legacy results to path keys"
```

---

## Task 4: Metrics over plan targets

**Files:**
- Modify: `utils/metrics.py`
- Test: `tests/utils/test_metrics.py`

**Interfaces:**
- Consumes: `build_validation_plan`, `flatten_targets` (Task 1); target `.key`, `.kind`, `.title`.
- Produces: `aggregate_metrics(progress_data, selections)` unchanged signature, but keyed by target key and driven by the plan; `calculate_binary_accuracy` / `calculate_list_metrics` unchanged. `_build_metrics_rows` / `format_metrics_summary` label rows by `target.title`.

- [ ] **Step 1: Write the failing test**

```python
# tests/utils/test_metrics.py
from utils.metrics import aggregate_metrics
from utils.models import FieldSelection


def test_aggregate_metrics_uses_path_keys():
    selections = [
        FieldSelection(selection_type="basemodel_field",
                       class_name="PrimaryCancerFacts", field_name="topography"),
    ]
    progress = {
        "completed_files": ["doc1", "doc2"],
        "results": {
            "doc1": {"primary_cancer.primary_cancer_facts.topography": "PRESENT_CORRECT"},
            "doc2": {"primary_cancer.primary_cancer_facts.topography": "PRESENT_INCORRECT"},
        },
    }
    metrics = aggregate_metrics(progress, selections)
    key = "primary_cancer.primary_cancer_facts.topography"
    assert key in metrics
    assert metrics[key]["type"] == "binary"
    assert metrics[key]["tp"] == 1
    assert metrics[key]["fp"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/utils/test_metrics.py -v`
Expected: FAIL — `aggregate_metrics` still keys by `build_key()`, so `key` is absent.

- [ ] **Step 3: Update `aggregate_metrics`**

Replace the body of `aggregate_metrics` in `utils/metrics.py` with a plan-driven version (add `from utils.schema_inspector import SchemaInspector` and `from utils.validation_plan import build_validation_plan, flatten_targets` at the top; the schema module/root come from the selections' shared session — pass them via the first selection's inspector is not possible, so accept them from the caller). Change the signature to `aggregate_metrics(progress_data, selections, inspector)` and update callers (`export_to_csv`, `export_to_csv_string`, and `pages/3_Analysis.py`) to pass an inspector.

```python
def aggregate_metrics(progress_data, selections, inspector):
    metrics = {}
    completed_files = set(progress_data.get("completed_files", []))
    targets = flatten_targets(build_validation_plan(selections, inspector))

    for target in targets:
        results_for_target = [
            file_results[target.key]
            for file_path, file_results in progress_data.get("results", {}).items()
            if file_path in completed_files and target.key in file_results
        ]
        if not results_for_target:
            continue
        first = results_for_target[0]
        if isinstance(first, str):
            metrics[target.key] = {
                "type": "binary", "target": target,
                **calculate_binary_accuracy(results_for_target),
            }
        elif isinstance(first, dict):
            metrics[target.key] = {
                "type": "list", "target": target,
                **calculate_list_metrics(results_for_target),
            }
    return metrics
```

In `_build_metrics_rows` and `format_metrics_summary`, replace the `selection = metric_data["selection"]` + name branching with:

```python
        name = metric_data["target"].title
```

Update `export_to_csv` / `export_to_csv_string` to take and forward an `inspector` argument.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/utils/test_metrics.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add utils/metrics.py tests/utils/test_metrics.py
git commit -m "feat: aggregate metrics over plan targets by path key"
```

---

## Task 5: Grouped rendering on the Validate page

**Files:**
- Modify: `utils/validation_ui.py`
- Modify: `pages/2_Validate.py`
- Modify: `utils/styles.py` (add row/toggle CSS)

**Interfaces:**
- Consumes: `build_validation_plan`, `flatten_targets`, `resolve_target`, `group_rollup` (Tasks 1–2); `describe_class` / `describe_field_by_name` (glossary).
- Produces: `render_group(group, extraction_data, inspector, key_prefix, doc_results, glossary, depth=0) -> dict` returning `{target_key: verdict}` for all targets it rendered; `render_leaf_toggle(...)` and `render_list_target(...)` helpers. No stored group verdicts.

- [ ] **Step 1: Add the toggle helper (✓/✗) with a focused test**

Add to `utils/validation_ui.py` a pure mapping helper and test it:

```python
def toggle_to_storage(choice, is_present):
    """Map a ✓/✗/None choice + presence to a storage verdict (or None)."""
    if choice == "correct":
        return "PRESENT_CORRECT" if is_present else "ABSENT_CORRECT"
    if choice == "incorrect":
        return "PRESENT_INCORRECT" if is_present else "ABSENT_INCORRECT"
    return None


def storage_to_choice(stored):
    """Inverse: storage verdict -> 'correct' | 'incorrect' | None."""
    if isinstance(stored, str) and stored.endswith("_CORRECT"):
        return "correct"
    if isinstance(stored, str) and stored.endswith("_INCORRECT"):
        return "incorrect"
    return None
```

```python
# tests/utils/test_validation_ui.py  (new)
from utils.validation_ui import storage_to_choice, toggle_to_storage


def test_toggle_round_trip_present():
    assert toggle_to_storage("correct", True) == "PRESENT_CORRECT"
    assert toggle_to_storage("incorrect", False) == "ABSENT_INCORRECT"
    assert toggle_to_storage(None, True) is None
    assert storage_to_choice("PRESENT_INCORRECT") == "incorrect"
    assert storage_to_choice(None) is None
```

- [ ] **Step 2: Run test to verify it passes**

Run: `.venv/bin/pytest tests/utils/test_validation_ui.py -v`
Expected: PASS.

- [ ] **Step 3: Implement the ✓/✗ leaf row**

Add `render_leaf_toggle(target, resolved, key_prefix, stored)` to `utils/validation_ui.py`. It renders a compact row: label + value (+ 🔎 locate button when `_is_excerpt_field`) in a wide left column, and two icon buttons (✓ / ✗) in a slim right column. Clicking a lit icon clears to unreviewed. Return the storage verdict.

```python
def render_leaf_toggle(target, resolved, key_prefix, stored):
    value = resolved["value"]
    is_present = is_value_present(value)
    choice = storage_to_choice(stored)

    c_text, c_ok, c_no = st.columns([6, 1, 1], vertical_alignment="center")
    with c_text:
        st.markdown(_field_row_html(target.field_name, value), unsafe_allow_html=True)
        if _is_excerpt_field(target.field_name, value):
            st.button("🔎", key=f"{key_prefix}_locate", on_click=_set_highlight,
                      args=(value,), help=f"Locate: {str(value)[:80]}")

    def _toggle(new_choice):
        # clicking the lit icon clears back to unreviewed
        st.session_state[f"{key_prefix}_choice"] = (
            None if st.session_state.get(f"{key_prefix}_choice") == new_choice else new_choice
        )

    if f"{key_prefix}_choice" not in st.session_state:
        st.session_state[f"{key_prefix}_choice"] = choice

    with c_ok:
        st.button("✓", key=f"{key_prefix}_ok",
                  type="primary" if st.session_state[f"{key_prefix}_choice"] == "correct" else "secondary",
                  on_click=_toggle, args=("correct",))
    with c_no:
        st.button("✗", key=f"{key_prefix}_no",
                  type="primary" if st.session_state[f"{key_prefix}_choice"] == "incorrect" else "secondary",
                  on_click=_toggle, args=("incorrect",))

    return toggle_to_storage(st.session_state[f"{key_prefix}_choice"], is_present)
```

- [ ] **Step 4: Implement `render_list_target` and `render_group`**

`render_list_target` reuses the existing per-item radio/missed logic from `show_item_validation` (rename/refactor is fine) but with ✓/✗ per item. `render_group` renders the group header (title via `describe_class`, roll-up line via `group_rollup`), then its targets as rows, then its subgroups indented (`depth+1`). It accumulates and returns `{target.key: verdict}`.

```python
def render_group(group, extraction_data, inspector, key_prefix, doc_results, glossary, depth=0):
    from utils.glossary import describe_class
    from utils.validation_plan import group_rollup

    results = {}
    summary = describe_class(group.class_name, inspector, glossary or {})
    roll = group_rollup(group, doc_results)
    header = group.class_name if depth == 0 else group.class_name
    st.markdown(f"{'&nbsp;'*4*depth}**{header}**", unsafe_allow_html=True)
    if summary:
        st.caption(summary)
    st.caption(f"▸ {roll['incorrect']} incorrect · {roll['unvalidated']} unvalidated")

    for i, target in enumerate(group.targets):
        resolved = resolve_target(target, extraction_data, inspector)
        tk = f"{key_prefix}_{target.key}"
        if target.kind == "leaf":
            results[target.key] = render_leaf_toggle(target, resolved, tk, doc_results.get(target.key))
        else:
            results[target.key] = render_list_target(target, resolved, tk, doc_results.get(target.key))

    for sub in group.subgroups:
        results.update(
            render_group(sub, extraction_data, inspector, key_prefix, doc_results, glossary, depth + 1)
        )
    return results
```

- [ ] **Step 5: Rewrite the Validate page loop**

In `pages/2_Validate.py`, replace the `for i, selection in enumerate(session.selections)` block (lines ~220-266) with a plan-driven loop:

```python
from utils.validation_plan import build_validation_plan, flatten_targets, resolve_target

plan = build_validation_plan(session.selections, inspector)
existing_results = progress["results"].get(document_id, {})

# extracted/empty filter now works per group (any extracted target)
def _group_has_extracted(group):
    for t in flatten_targets([group]):
        r = resolve_target(t, extraction_data, inspector)
        if (r["kind"] == "list" and r["items"]) or (r["kind"] == "single" and is_value_present(r["value"])):
            return True
    return False

results = {}
for gi, group in enumerate(plan):
    extracted = _group_has_extracted(group)
    if block_filter == "Extracted" and not extracted:
        continue
    if block_filter == "Empty" and extracted:
        continue
    with st.expander(f"**{group.class_name}**", expanded=True):
        results.update(
            render_group(group, extraction_data, inspector,
                         key_prefix=f"doc_{current_index}_g{gi}",
                         doc_results=existing_results, glossary=glossary)
        )
        _render_comment_box(session, document_id, group.path, results.get(group.path),
                            progress, block_prefix=f"doc_{current_index}_g{gi}")
```

Recompute the `n_extracted` / `n_empty` caption counts from `plan` groups. Keep the immediate-save block (`non_none_results`) unchanged — it already saves `results` by key.

- [ ] **Step 6: Add CSS**

Add to `utils/styles.py` `VALIDATE_PAGE_STYLES`: tighten button padding for the ✓/✗ columns and reduce row vertical spacing (target `div[data-testid="column"] button` inside the validation container). Keep it minimal.

- [ ] **Step 7: Verify in the browser**

Start the app and drive the Validate page. Confirm: overlapping selections show each field once; ✓/✗ writes through (reload shows persisted state); the All/Extracted/Empty filter hides empty groups; comments attach per group; roll-up line updates. Fix issues in source and re-check.

Run: `.venv/bin/pytest tests/utils/test_validation_ui.py -v` (unit) then manual browser verification per the harness preview workflow.

- [ ] **Step 8: Commit**

```bash
git add utils/validation_ui.py pages/2_Validate.py utils/styles.py tests/utils/test_validation_ui.py
git commit -m "feat: grouped per-field validation UI on Validate page"
```

---

## Task 6: Comments keyed by group

**Files:**
- Modify: `utils/comments.py`
- Test: `tests/utils/test_comments.py`

**Interfaces:**
- Consumes: `build_validation_plan` groups (`.path`, `.class_name`), `flatten_targets` for target titles.
- Produces: `flatten_comments(progress, selections, inspector)` resolving a comment key (group path or target key) to a readable `section` title.

- [ ] **Step 1: Write the failing test**

```python
# adapt tests/utils/test_comments.py
from utils.comments import flatten_comments
from utils.models import FieldSelection
from utils.schema_inspector import SchemaInspector


def test_comment_section_resolves_group_path():
    inspector = SchemaInspector("oncollamaschemav3", "OncoLlamaModel")
    selections = [FieldSelection(selection_type="basemodel_class", class_name="PrimaryCancer")]
    progress = {"comments": {"doc1": {"primary_cancer.primary_cancer_facts": "looks off"}}}
    rows = flatten_comments(progress, selections, inspector)
    assert rows[0]["section"] == "PrimaryCancerFacts"
    assert rows[0]["comment"] == "looks off"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/utils/test_comments.py -v`
Expected: FAIL — current `flatten_comments` keys titles by `build_key()`.

- [ ] **Step 3: Update `flatten_comments`**

Read the current `utils/comments.py`, then build the key→title map from the plan: walk `build_validation_plan(selections, inspector)`; map each `group.path -> group.class_name` and each `target.key -> target.title`. Fall back to the raw key when unknown.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/utils/test_comments.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add utils/comments.py tests/utils/test_comments.py
git commit -m "feat: resolve comment sections by group/target title"
```

---

## Task 7: Packet data from the plan

**Files:**
- Modify: `utils/packet_builder.py`
- Test: `tests/utils/test_packet_builder.py`

**Interfaces:**
- Consumes: `build_validation_plan`, `flatten_targets`, `resolve_target`, `group_rollup`.
- Produces: packet JSON with a `plan` tree (serialized groups/targets) and per-document `blocks` keyed by `target.key`; `selections_meta` replaced by a serialized plan. Verdict-collection keys in the packet match `target.key`.

- [ ] **Step 1: Write the failing test**

```python
# adapt tests/utils/test_packet_builder.py
from utils.packet_builder import build_packet_data
# ... build a Session over oncollamaschemav3 with a PrimaryCancer whole-class selection
def test_packet_blocks_keyed_by_target_path(session_fixture):
    data = build_packet_data(session_fixture, [DOC_ID], "packet-1")
    doc = data["documents"][0]
    assert "primary_cancer.primary_cancer_facts.topography" in doc["blocks"]
    # plan tree present
    assert data["plan"][0]["class_name"] == "PrimaryCancer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/utils/test_packet_builder.py -v`
Expected: FAIL — blocks are keyed by `build_key()`, no `plan` key.

- [ ] **Step 3: Rewrite `build_packet_data`**

Serialize the plan to plain dicts (`_group_to_dict(group)` → `{"path","class_name","title","summary","targets":[{"key","kind","field_name","title","summary"}...],"subgroups":[...]}`) and set `blocks[target.key] = resolve_target(target, inference, inspector)` for every `flatten_targets` target. Keep `field_glossary`. Replace `selections` with `plan`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/utils/test_packet_builder.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add utils/packet_builder.py tests/utils/test_packet_builder.py
git commit -m "feat: build packet data from validation plan (path-keyed blocks)"
```

---

## Task 8: Packet template grouped rendering (JS)

**Files:**
- Modify: `utils/packet_template.html`

**Interfaces:**
- Consumes: `DATA.plan` (group tree) + `doc.blocks[target.key]` from Task 7.
- Produces: JS that renders nested groups with ✓/✗ leaf rows and per-item list validation, collecting verdicts under `target.key` (matching the app), so `results_import` reconciles both.

- [ ] **Step 1: Replace the selection loop with a plan walk**

In `renderDocument()` (line ~824), iterate `DATA.plan` recursively instead of `DATA.selections`. Add `renderGroup(container, doc, group, depth)` that renders the header + roll-up, then each target via a new `renderLeaf(...)` (two ✓/✗ buttons; toggling the lit one clears) and the existing list logic refactored into `renderListTarget(...)`, then recurses subgroups.

- [ ] **Step 2: Update state keys**

`setValue` / `getValue` / `getComment` / `setComment` already key by an opaque string — pass `target.key`. Keep the `resultsPayload()` shape (`results`, `comments`, `completed_files`) so `parse_results_payload` still works.

- [ ] **Step 3: Update the Extracted/Empty filter**

`blockIsExtracted` now operates per group: a group is "extracted" if any of its (recursive) targets has a present value / non-empty list. Hide empty groups under the Empty/Extracted filter.

- [ ] **Step 4: Verify the packet in the browser**

Generate a packet (via the app's packet page or `build_packet_html`), open the HTML file, and confirm grouped ✓/✗ rendering, list validation, comments, filter, and that "Save results" produces a JSON whose `results` keys are dotted paths. Import it via the Analysis page to confirm round-trip.

- [ ] **Step 5: Commit**

```bash
git add utils/packet_template.html
git commit -m "feat: grouped per-field validation in offline packet"
```

---

## Task 9: Selection builder semantics

**Files:**
- Modify: `pages/1_Sessions.py`

**Interfaces:**
- Consumes: nothing new; produces the same `FieldSelection` list. Behaviour change only.

- [ ] **Step 1: Relax the whole-class disabling**

Remove `disabled=whole_class` on the individual-field checkboxes (line ~423) since overlap is now deduped by the plan. Update the "Select entire {class} class" caption/help to read "validate every field individually."

- [ ] **Step 2: Verify in the browser**

In the session wizard, select a whole class plus some of its fields plus a nested class; proceed to Validate and confirm each field renders exactly once (no duplication, no error).

- [ ] **Step 3: Commit**

```bash
git add pages/1_Sessions.py
git commit -m "feat: whole-class selection means all fields individually"
```

---

## Task 10: Analysis page wiring + end-to-end parity

**Files:**
- Modify: `pages/3_Analysis.py`

**Interfaces:**
- Consumes: `aggregate_metrics(progress, selections, inspector)` (Task 4 signature).

- [ ] **Step 1: Pass an inspector to metrics calls**

Find every `aggregate_metrics(...)` / `export_to_csv*(...)` call in `pages/3_Analysis.py`; construct `SchemaInspector(session.schema_module, session.root_class)` and pass it. The imported-packet path already yields path-keyed results, so no key translation is needed.

- [ ] **Step 2: Verify end-to-end**

Run the full suite: `.venv/bin/pytest -q`. Then in the browser: create a session, validate a document per-field on the Validate page, mark complete, open Analysis and confirm per-field metrics; generate a packet, validate offline, import, and confirm the imported results merge and produce metrics with matching path keys.

- [ ] **Step 3: Commit**

```bash
git add pages/3_Analysis.py
git commit -m "feat: analysis metrics over path-keyed plan targets"
```

---

## Self-review notes

- **Spec coverage:** plan builder + dedup (T1), derived roll-ups (T2), migration (T3), metrics (T4), Validate UI with ✓/✗ nested groups (T5), comments (T6), packet data (T7), packet JS (T8), builder semantics (T9), analysis + parity (T10). All spec sections mapped.
- **Type consistency:** `target.key` is the single results key across T1–T8; `aggregate_metrics(progress, selections, inspector)` signature is introduced in T4 and consumed in T4/T10; `render_group` returns `{key: verdict}` consumed by T5's save block.
- **Verify-before-done:** T5, T8, T9, T10 include browser verification because Streamlit rendering and packet JS are not unit-testable; pure logic (T1–T4, T6, T7) is covered by pytest.
