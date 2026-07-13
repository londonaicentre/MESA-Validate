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


def target_key(obj, inspector=None):
    """Canonical results key for a FieldSelection or a target.

    Leaf/list fields -> dotted data path. Enum filters and list-item classes
    have no single path, so they get a stable synthetic key. A whole-class
    selection of a nested (non-list-item) object has no single group-level
    key either -- it expands into many per-field keys -- so it returns None.
    Resolving a dotted path for a bare basemodel_class/basemodel_field
    selection requires walking the schema, so an inspector must be supplied
    for those cases; without one, None is returned (mirrors the "unresolved"
    state used while building a plan).
    """
    # already-built target
    if isinstance(obj, (LeafTarget, ListTarget)):
        return obj.key

    # FieldSelection
    if obj.selection_type == "enum_value":
        return f"enum::{obj.class_name}.{obj.enum_value}"

    if inspector is None:
        return None  # class/field keys need schema traversal to resolve

    if obj.selection_type == "basemodel_class":
        if inspector.is_class_used_as_list_item(obj.class_name):
            return f"list::{obj.class_name}"
        # A whole-class selection of a nested (non-list-item) object expands
        # into many per-field keys with no single group-level key of its own,
        # so there is nothing valid to return here.
        return None

    if obj.selection_type == "basemodel_field":
        class_path = _class_path(obj.class_name, inspector)
        if class_path is None:
            return None
        return f"{class_path}.{obj.field_name}"

    return None


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
                if sub is not None and not any(s is sub for s in group.subgroups):
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
    source_selection = getattr(target, "source_selection", None)
    if source_selection is not None:
        return resolve_selection(source_selection, extraction_data, inspector)
    value = extract_field_value(extraction_data or {}, target.path)
    if target.kind == "list":
        return {"kind": "list", "items": value if isinstance(value, list) else []}
    return {"kind": "single", "value": value}


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
