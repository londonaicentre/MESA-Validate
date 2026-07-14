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
from typing import Optional, get_args, get_origin

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
    # Name of the list ITEM class, populated only for path-based list-field
    # targets (built from a container recursing into a List[Item] field).
    # None for "list::Class" and "enum::" targets, whose class_name already
    # names the item class.
    item_class_name: Optional[str] = None


@dataclass
class Group:
    path: str
    class_name: str
    title: str
    targets: list = field(default_factory=list)
    subgroups: list = field(default_factory=list)


def _class_path(class_name, inspector):
    """Dotted data path to a class object, or None if it is not reachable.

    The root class is reachable at an empty path (""), which is distinct from
    None ("not found") -- so its own scalar/list fields still get validated.
    """
    parts = inspector.find_class_path(class_name)
    return None if parts is None else ".".join(parts)


def _field_path(class_path, field_name):
    """Data path for a field, without a leading dot for root-class fields."""
    return f"{class_path}.{field_name}" if class_path else field_name


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
        return _field_path(class_path, obj.field_name)

    return None


def _list_item_class_name(owner_class_name, field_name, inspector):
    """Name of the item class for a List[Item] (optionally Optional[...]) field.

    Returns None if the field isn't found, isn't a list, or the item type has
    no name (e.g. a bare scalar list).
    """
    class_info = inspector.classes.get(owner_class_name)
    if not class_info or class_info["type"] != "BaseModel":
        return None
    model_fields = class_info["class"].model_fields
    field_info = model_fields.get(field_name)
    if field_info is None:
        return None
    annotation = field_info.annotation

    # unwrap Optional[...]/Union[...]
    origin = get_origin(annotation)
    if str(origin) == "typing.Union":
        args = get_args(annotation)
        annotation = next((a for a in args if a is not type(None)), annotation)
        origin = get_origin(annotation)

    if origin is not list:
        return None
    args = get_args(annotation)
    if not args:
        return None
    item_type = args[0]
    return getattr(item_type, "__name__", None)


def _leaf_or_list_target(class_name, field_name, field_meta, class_path, inspector=None):
    path = _field_path(class_path, field_name)
    if field_meta["is_list"]:
        item_class_name = (
            _list_item_class_name(class_name, field_name, inspector)
            if inspector is not None
            else None
        )
        return ListTarget(
            key=path,
            path=path,
            field_name=field_name,
            class_name=class_name,
            title=f"{class_name}.{field_name}",
            item_class_name=item_class_name,
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
                    group,
                    _leaf_or_list_target(
                        class_name, field_name, meta, class_path, self.inspector
                    ),
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
                group,
                _leaf_or_list_target(
                    selection.class_name,
                    selection.field_name,
                    meta,
                    class_path,
                    insp,
                ),
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


# Canonical clinical order for top-level validation blocks. Groups whose
# class_name appears here are shown in this order; anything not listed (future
# classes, leftover enum blocks) keeps its first-seen order after these. The
# through-line is: case overview -> primary cancer core -> biology ->
# staging/spread -> history -> patient status/findings -> other cancers -> plan.
CLINICAL_BLOCK_ORDER = [
    "ContextSummary",
    "PrimaryCancer",
    "PrimaryCancerFacts",
    "PrimaryCancerTumourFacts",
    "MolecularBiomarkerProfile",
    "PrimaryCancerScore",
    "PrimaryCancerSpread",
    "PrimaryCancerTimelineEvent",
    "PerformanceStatus",
    "PatientFinding",
    "OtherCancerFacts",
    "FuturePlan",
]
_ORDER_RANK = {name: i for i, name in enumerate(CLINICAL_BLOCK_ORDER)}


def _clinical_rank(group):
    """Sort rank for a top-level block: the root class (empty path) leads,
    then CLINICAL_BLOCK_ORDER; unranked classes fall to the end."""
    if group.path == "":  # the root class group, whatever it is named
        return -1
    return _ORDER_RANK.get(group.class_name, len(_ORDER_RANK))


def _clinical_sort(groups):
    """Order top-level groups: root class first, then CLINICAL_BLOCK_ORDER,
    stably. Unranked classes keep their existing relative order at the end
    (never dropped)."""
    return [
        g
        for _, g in sorted(
            enumerate(groups), key=lambda p: (_clinical_rank(p[1]), p[0])
        )
    ]


def build_validation_plan(selections, inspector):
    """Return an ordered list of top-level Groups for the given selections.

    Nested objects become subgroups (rendered indented); list fields and enum
    filters become list targets; every leaf appears exactly once. Top-level
    blocks are ordered by CLINICAL_BLOCK_ORDER.
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
    top_level = [g for g in all_groups if g.path not in nested_paths]
    return _clinical_sort(_dedup_prefer_nested(top_level))


def _collect_nested_paths(group, acc):
    for sg in group.subgroups:
        acc.add(sg.path)
        _collect_nested_paths(sg, acc)


def _dedup_prefer_nested(groups):
    """Drop redundant "list::Class" groups whose data is already covered by
    a nested path-based List[Class] field elsewhere in the plan.

    A validator may select both a container (e.g. PrimaryCancer) and a
    list-item class it contains (e.g. PrimaryCancerScore). That produces two
    targets over the same underlying data: a nested path-based list field
    (key like "primary_cancer.primary_cancer_scores") and a synthetic
    top-level "list::PrimaryCancerScore" target. Prefer the nested one and
    remove the synthetic duplicate; if that empties its group, drop the
    group too.
    """
    covered_item_classes = {
        t.item_class_name
        for t in flatten_targets(groups)
        if isinstance(t, ListTarget) and t.item_class_name is not None
    }
    if not covered_item_classes:
        return groups

    for g in groups:
        _remove_redundant_list_class_targets(g, covered_item_classes)

    return [g for g in groups if g.targets or g.subgroups]


def _remove_redundant_list_class_targets(group, covered_item_classes):
    group.targets = [
        t
        for t in group.targets
        if not (
            isinstance(t, ListTarget)
            and t.key.startswith("list::")
            and t.key[len("list::") :] in covered_item_classes
        )
    ]
    group.subgroups = [
        sg
        for sg in group.subgroups
        if _keep_subgroup(sg, covered_item_classes)
    ]


def _keep_subgroup(subgroup, covered_item_classes):
    _remove_redundant_list_class_targets(subgroup, covered_item_classes)
    return bool(subgroup.targets or subgroup.subgroups)


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
