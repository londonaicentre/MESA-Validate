# Per-field grouped validation — design

**Date:** 2026-07-13
**Status:** Approved (design), pending implementation plan
**Branch:** feature/profiles-packets-ux

## Problem

The validation UI renders every `FieldSelection` as an independent block. When a
validator selects overlapping targets — a whole class (`PrimaryCancer`), a nested
class (`PrimaryCancerFacts`), *and* individual fields (`topography`) — the same
data point is displayed and validated multiple times, at conflicting
granularities:

- A whole-class selection (`basemodel_class`) renders the entire class as one card
  with a **single** Correct/Incorrect verdict.
- An individual-field selection renders that one field with its **own** verdict.

So `topography` can appear inside the PrimaryCancer card, inside the
PrimaryCancerFacts card, and as its own block — validated up to three times. Each
field is also a full expander block, consuming large vertical space. The selection
builder only prevents overlap *within* a single class (whole-class disables sibling
field checkboxes), never across nested classes.

## Goals

- Each data point appears **exactly once**, regardless of how many selections
  reference it.
- Validation granularity is **per-field**: the validator ticks Correct/Incorrect
  on individual lines; the class/group is a visual container, not a verdict.
- Group-, class-, and document-level results are **derived** from leaf verdicts,
  never stored — one source of truth.
- Compact rows, not a full block per field.
- The Validate page and the offline clinician packet stay in lockstep on the
  results format.

## Non-goals

- Redesigning the session/profile creation wizard beyond the minimal changes
  below.
- Changing the verdict vocabulary (`PRESENT_CORRECT` / `ABSENT_CORRECT` /
  `PRESENT_INCORRECT` / `ABSENT_INCORRECT` / `NOT_APPLICABLE`) or the list-metric
  math.

## Decisions (locked with user)

1. **Granularity: per-field only** (Option 1). Group-level verdicts are derived.
2. **Toggle: two tap-icons ✓ / ✗.** Untapped = unreviewed (stored as `NONE`/null).
   Tapping the lit icon clears back to unreviewed. Presence (present vs absent) is
   inferred at save time from the extracted value, exactly as today.
3. **Hierarchy: nested.** One header for the selected class, indented sub-sections
   for nested objects and list fields, with a single class-wide derived roll-up.
4. **Scope: both surfaces together** — Validate page and `packet_template.html` —
   so app and packet always agree on the new path-keyed results and
   `results_import` keeps reconciling them.

## Architecture

### New module: `utils/validation_plan.py`

The single source of truth for *what to validate and in what order*, reconciling
the flat `session.selections` against each other and against the schema tree.

```
build_validation_plan(selections, inspector) -> ValidationPlan
```

A `ValidationPlan` is an **ordered tree of groups**, each group holding **targets**:

- **Group** — corresponds to an object in the schema (a `BaseModel`), identified by
  its dotted data path (e.g. `primary_cancer.primary_cancer_facts`). Carries a
  display title, glossary summary, and an ordered list of child targets and
  sub-groups (nested rendering).
- **Leaf target** — a single scalar/enum field. Renders as a compact ✓/✗ row.
  Stores one verdict string.
- **List target** — a `List[...]` field, or an enum-value filter over list items.
  Renders as per-item ✓/✗ rows plus a "missed" count. Stores `{items, missed}`.

**Expansion rules** (per selection):

| Selection | Expands to |
|---|---|
| `basemodel_field` scalar/enum | one leaf target |
| `basemodel_field` that is `List[...]` | one list target |
| `basemodel_class` (nested object) | recurse fields: scalars/enums → leaf targets; nested objects → sub-groups; `List[...]` → list targets |
| `basemodel_class` used as a list item | one list target (today's behavior) |
| `enum_value` | one list target (filtered) |

**Dedup:** targets are keyed by canonical path; a field reached through multiple
selections is inserted once. Grouping follows the field's real parent path, so a
field pulled in via an explicit `basemodel_field` selection still nests under its
owning object's group.

**Ordering:** schema declaration order within each object; groups appear in the
order their first target is encountered across `selections`.

### Canonical key

The results key for each target is its **dotted data path**, e.g.
`primary_cancer.primary_cancer_facts.topography`. This replaces
`selection.build_key()` everywhere results are keyed. It is stable regardless of
which selection pulled the field in — the property that makes dedup and
cross-consumer agreement (Validate page, metrics, packet) work.

The plan-builder reuses `SchemaInspector.find_class_path` and the schema
introspection already used by `selection_resolver`.

### Derived roll-ups

`derive_group_result(group, results_for_doc)` computes, at read time:
- counts of correct / incorrect / unvalidated leaves,
- a group "fully correct" boolean,
rolled up recursively to class and document level. Nothing derived is persisted.

## Rendering

### Validate page (`pages/2_Validate.py`, `utils/validation_ui.py`)

- Replace the "one expander per selection" loop with "one block per top-level group
  in the plan."
- Each group: header (title + glossary summary + derived roll-up line), then nested
  sub-sections (indented) and rows.
- Leaf row: `label` + `value` (+ 🔎 locate button for excerpt-like values, as today)
  on the left; a two-icon ✓/✗ control on the right. Icon state reflects the stored
  verdict; clicking writes through `SessionManager.save_results` immediately (as
  today). Clicking the lit icon clears to unreviewed.
- List target: per-item ✓/✗ rows + "Missed items" number input.
- The existing **All / Extracted / Empty** filter operates on leaf rows: Empty hides
  rows whose value is absent; a group with no visible rows under the active filter
  is hidden. Counts recomputed from leaves.
- Per-group freetext comment box (keyed by group path), reusing the existing
  comment mechanism.

### Packet (`utils/packet_builder.py`, `utils/packet_template.html`, `utils/textmatch.js`)

- `build_packet_data` consumes the **same** `build_validation_plan`, emitting the
  group/target tree + path keys into the packet JSON (instead of per-selection
  `resolve_selection` blocks). Python keeps ownership of schema introspection.
- `packet_template.html` JS is ported to render the nested groups + ✓/✗ rows +
  per-item list validation, and to collect verdicts under the **same path keys**,
  so exported results import cleanly via `results_import`.

## Storage & results shape

`progress.json` structure is unchanged; only keys and the class-level entries
change:

```jsonc
"results": {
  "<document_id>": {
    "primary_cancer.primary_cancer_facts.topography": "PRESENT_CORRECT",
    "primary_cancer.primary_cancer_facts.morphology_name_desc": "PRESENT_INCORRECT",
    "primary_cancer.primary_cancer_scores": { "items": [true, false], "missed": 0 }
  }
},
"comments": { "<document_id>": { "primary_cancer.primary_cancer_facts": "…" } }
```

`metrics.calculate_binary_accuracy` / `calculate_list_metrics` are unchanged.
`aggregate_metrics` iterates plan targets (path keys) instead of
`selection.build_key()`; CSV/summary rows label rows by path/title.

## Migration

Old results are keyed by `build_key()`; some hold a single whole-class verdict that
cannot be split per field.

**Best-effort migration**, run once when loading a session's progress:
- Map old `basemodel_field`, list, and `enum_value` keys to the new path keys
  (1:1 where the target still exists in the plan). Carry the verdict over.
- **Drop** old whole-class single verdicts (unrecoverable per-field; and precisely
  the ambiguous kind being removed).
- Surface a one-time note listing blocks that reverted to unreviewed.
- Keep a backup of the pre-migration `progress.json`.

## Downstream changes summary

| File | Change |
|---|---|
| `utils/validation_plan.py` | **New.** Plan builder, target tree, path keys, roll-ups. |
| `utils/validation_ui.py` | Grouped/nested rendering; ✓/✗ leaf rows; list rows. |
| `pages/2_Validate.py` | Iterate plan groups; filter/comments/save by path key. |
| `utils/metrics.py` | `aggregate_metrics` + row labels keyed by plan targets. |
| `utils/comments.py` | Titles keyed by group path. |
| `utils/packet_builder.py` | Build packet data from the plan; path-keyed blocks. |
| `utils/packet_template.html` | Port grouped ✓/✗ rendering + verdict collection. |
| `pages/1_Sessions.py` | "Select entire class" = all leaf fields; relax sibling-disable. |
| `utils/session_manager.py` | One-time best-effort results migration + backup. |
| `pages/3_Analysis.py` | Consume path-keyed metrics; optional derived group roll-ups. |

## Testing

- **Unit — plan builder:** overlapping selections dedup to one target each; nested
  objects produce sub-groups; list/enum fields produce list targets; ordering
  matches schema declaration order.
- **Unit — roll-ups:** derived group result matches hand-computed counts from leaf
  verdicts.
- **Unit — migration:** field/list verdicts carry over to path keys; whole-class
  verdicts dropped; backup written.
- **Unit — metrics:** `aggregate_metrics` over path-keyed results reproduces
  expected precision/recall/F1.
- **Parity:** app-collected results and packet-collected results for the same
  document produce identical keys and import cleanly.
- **Manual:** drive the Validate page in the browser preview — grouped rows, ✓/✗
  write-through, filter, comments, completion, packet round-trip.
