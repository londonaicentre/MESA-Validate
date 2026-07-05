# MESA-Validate: Field Profiles, Packet Export, and Clinician HTML Validator

**Date:** 2026-07-05
**Status:** Approved

## Problem

MESA-Validate is a Streamlit app for human-in-the-loop validation of OncoLlama
(LLM oncology entity extraction) outputs. Three usability/deployment gaps block
a rollout to ~10 clinicians validating ~600 documents:

1. **No reusable field selection.** The session wizard's Step 2 requires
   re-ticking every class/field/enum checkbox for each session, even though the
   validation protocol (GUIDE.md) fixes the field set.
2. **Collapsed entity display.** The Validate page renders extracted entities
   via `st.json(expanded=False)`, forcing validators to expand each item with
   tiny disclosure triangles.
3. **No jump-to-source.** There is no link from an extracted entity to the
   document text it came from; validators resort to browser Ctrl-F.
4. **Deployment.** Clinicians use NHS Windows desktops with Edge, no web
   server, no default Python. A network drive is available. The solution must
   run with zero installation.

## Decisions (user-confirmed)

- **Architecture:** Streamlit app remains the coordinator's tool; it exports
  one **self-contained HTML validation packet** per clinician.
- **Results flow:** packets save a results JSON directly to the network drive
  via the browser file picker, with localStorage autosave and a download
  fallback.
- **Document assignment:** manual — the coordinator picks which documents go
  into each packet.
- **Scope:** the polished validation UX (expanded cards, jump-to-source) is
  built only in the HTML validator. The Streamlit Validate page is unchanged.
  No automatic split/overlap logic.

## Architecture

```
Coordinator (Streamlit, existing app)
├── Sessions wizard
│   └── Step 2 + NEW: load/save field-selection profiles (profiles/*.json)
├── NEW: Export packet panel (active session)
│   └── writes packets/<name>.html  (documents + precomputed blocks + UI, inline)
└── Analysis page
    └── NEW: import packet results (results/*_results.json) → existing metrics.py

Clinician (Edge, file:// from network drive)
└── packets/<name>.html
    ├── validates documents (expanded cards, jump-to-source)
    ├── autosaves to localStorage (results only, no clinical text)
    └── saves results/<name>_results.json to the network drive
```

Python keeps all Pydantic schema introspection; the browser receives only
display-ready data. Validation values use the **same storage format as
`progress.json`** (`PRESENT_CORRECT`, `ABSENT_CORRECT`, `PRESENT_INCORRECT`,
`ABSENT_INCORRECT`, `{"items": [true|false|null,...], "missed": n}`) so the
existing `utils/metrics.py` is reused without modification.

## Component 1: Field-selection profiles

- New directory `profiles/` (repo root). One JSON file per profile:

  ```json
  {
    "name": "MESA Protocol v1",
    "schema_module": "oncollamaschemav3",
    "selections": [ {FieldSelection.model_dump()}, ... ]
  }
  ```

- New module `utils/profile_manager.py`: `list_profiles(schema_module=None)`,
  `load_profile(path)`, `save_profile(name, schema_module, selections)`.
  Loading validates selections against the live schema via `SchemaInspector`
  and returns `(valid_selections, skipped)` so the UI can warn about fields
  that no longer exist.
- Wizard Step 2 (pages/1_Sessions.py):
  - "Load profile" selectbox listing profiles whose `schema_module` matches
    the chosen schema, plus an Apply button. Applying pre-sets the
    `st.session_state` keys backing the existing checkboxes, then reruns —
    the user can still tweak before continuing.
  - "Save selection as profile" text input + button below the selection UI,
    enabled when ≥1 selection exists. Duplicate names prompt an error.
- A default profile file matching GUIDE.md ships in the repo
  (`profiles/mesa_protocol_v1.json`): PrimaryCancerFacts.topography,
  .morphology, .diagnosis_year, .diagnosis_month, .tnm_stage;
  MolecularBiomarkerProfile and PerformanceStatus entire classes; the four
  TimelineEventType enum values listed in GUIDE.md. Field names are verified
  against the actual installed schema during implementation and adjusted to
  the real names if GUIDE.md is stale.

## Component 2: Packet exporter

- New module `utils/packet_builder.py` + UI panel on the Sessions page shown
  when a session is active ("Export validation packet").
- UI inputs: packet name (required, filesystem-safe), document picker — a
  multiselect over the session's valid document IDs with "Select all" and a
  paste-a-list text area (IDs separated by newlines/commas; unknown IDs
  reported, not silently dropped) — and an output directory (default
  `packets/`).
- **Block precomputation.** For each document and each `FieldSelection`, the
  builder resolves the selection to a display-ready block using the same
  resolution semantics as `utils/validation_ui.py`:
  - `basemodel_class` used as list item → `{"kind": "list", "items": [...]}`
  - `basemodel_class` singleton → `{"kind": "single", "value": {...}}`
  - `basemodel_field` → `{"kind": "single", "value": <scalar/obj>}`
  - `enum_value` → `{"kind": "list", "items": [filtered items]}`
  The shared resolution logic is extracted from `validation_ui.py` into a
  UI-free function (in `utils/selection_resolver.py`) that both the Streamlit
  page and the packet builder call, so semantics cannot drift.
- **Packet data** (injected as JSON):

  ```json
  {
    "packet_name": "...",
    "session_name": "...",
    "schema_module": "...",
    "created_at": "ISO8601",
    "selections": [{"key": "...", "title": "...", "kind": "list|single"}],
    "documents": [
      {"document_id": "...", "content": "...", "blocks": {"<selection_key>": <block>}}
    ]
  }
  ```

- **Template**: `utils/packet_template.html`, fully self-contained (inline
  CSS/JS, no CDN, no fonts, no fetches). The builder replaces a single
  `__PACKET_DATA__` placeholder with the JSON (embedded in a
  `<script type="application/json">` tag; `</script>` sequences in clinical
  text escaped as `<\/script>`).
- Output: `packets/<packet_name>.html`. Existing file → confirm overwrite.

## Component 3: Clinician validator (packet UI)

Plain HTML/CSS/JS, no framework, no build step. Target browser: Edge
(Chromium) on Windows via `file://`.

- **Layout**: sticky header (packet name, document progress `x/y`, save-state
  indicator), document navigation (prev/next + jump dropdown listing document
  IDs with a done/undone marker), two side-by-side scrollable panes: document
  text (left, `white-space: pre-wrap`), validation blocks (right).
- **Entity cards**: each block item renders as a card showing **every field**
  as a label/value row — no collapsing. Null/absent values are rendered dimmed
  (`—`). List blocks show one card per item plus the "Number of items missed"
  input; single blocks show one card (or "Not present" state) with the
  None/Correct/Incorrect radios. Radios and missed counts map to the exact
  storage format of the Streamlit app (see Architecture).
- **Jump-to-source**: any string field value that plausibly quotes the
  document (fields ending `_desc`, `_name_desc`, `_summary`, plus any string
  value ≥ 12 chars) is rendered as a clickable "locate" chip.
  Matching strategy, in order:
  1. exact case-insensitive substring match;
  2. whitespace-normalized match (collapse runs of whitespace/newlines);
  3. fuzzy fallback: best window by token overlap (match the longest run of
     consecutive tokens from the value found in the document).
  On match: highlight all occurrences, scroll the first into view, and cycle
  through occurrences on repeated clicks. On no match: show a transient
  "not found verbatim in document" note on the chip (itself a validation
  signal). Only one active highlight set at a time.
- **Persistence**:
  - Every change writes to `localStorage` under a key derived from
    `packet_name` + `created_at`. Stored payload = results only (no document
    text): `{results: {document_id: {selection_key: value}}, completed:
    [document_id,...], meta}`.
  - "Save results" button: uses `window.showSaveFilePicker` when available
    (suggested name `<packet_name>_results.json`), remembering the handle for
    subsequent one-click saves during the session; falls back to an
    `<a download>` blob download when the API is unavailable or permission is
    refused.
  - Save-state indicator: "Unsaved changes" / "Saved HH:MM".
  - "Load results file" button (file input) restores state from a previously
    saved results JSON (resume on another machine); localStorage restore is
    automatic on open, with the newer of the two winning by `saved_at` when
    both exist (user is told which was loaded).
- **Results file format**:

  ```json
  {
    "packet_name": "...",
    "session_name": "...",
    "schema_module": "...",
    "saved_at": "ISO8601",
    "completed_files": ["document_id", ...],
    "results": {"document_id": {"<selection_key>": <same values as progress.json>}}
  }
  ```

## Component 4: Analysis import

- Analysis page gains an "Import packet results" section above the existing
  session analysis: `st.file_uploader(accept_multiple_files=True)` for
  `*_results.json` files (and an optional text input pointing at a folder to
  scan, default `results/`).
- Imported packets are matched to the selected session by `session_name` (a
  mismatch is a warning, not an error). Each packet's results are converted to
  the in-memory `progress`-shaped dict (`results` + `completed_files`) and fed
  through the existing `aggregate_metrics` / `format_metrics_summary` /
  `export_to_csv_string` with the session's selections.
- Display: per-packet metric tables plus a combined table (all packets pooled;
  a document validated in two packets contributes two rows, attributed by
  packet). CSV export includes a `packet` column for the combined view.

## Error handling

- Profile load with unknown fields/classes → warning listing skipped
  selections; the rest applies.
- Packet export with zero documents selected → disabled button + hint.
- `</script>`/HTML injection from clinical text → JSON embedded in a
  `type="application/json"` script tag with every `<` escaped as the JSON
  sequence `\u003c` (so `</script>` cannot terminate the tag), and all
  document/entity strings rendered into the DOM via `textContent` only, never
  `innerHTML`.
- `showSaveFilePicker` unavailable (older Edge, IE mode, permission denied) →
  automatic fallback to download; the save button reports which method was
  used.
- localStorage quota/blocked (rare on NHS builds) → non-fatal warning banner
  advising frequent manual saves.
- Corrupt/foreign results file on import (browser or Analysis page) →
  explicit error naming the file, other files still processed.

## Testing

- **pytest** (extends existing `tests/`):
  - `profile_manager`: save → list → load round-trip; loading a profile with
    a nonexistent field returns it in `skipped`.
  - `selection_resolver`: resolution parity — for the sample predictions in
    `predictions/test/`, resolver output matches what `validation_ui.py`
    displayed before the refactor (covers all four selection kinds).
  - `packet_builder`: built packet contains valid JSON for all selected
    documents; `</script>` in content is escaped; document picker list
    matches the session's valid files.
  - Analysis import: a synthetic results file produces identical metrics to
    the same values entered via `progress.json`.
- **Browser verification** (manual, via preview): open a generated packet from
  `file://`, validate a document end-to-end, save + reload restores state,
  jump-to-source hits exact/normalized/fuzzy/no-match cases.

## Out of scope

- Streamlit Validate page UX changes.
- Automatic document splitting or inter-rater overlap assignment.
- Any server/hosted deployment; authentication; editing of extractions.
