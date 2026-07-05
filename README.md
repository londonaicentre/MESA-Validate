# MESA Validate

A Streamlit application for human-in-the-loop validation of LLM-extracted structured outputs against Pydantic schemas within the MESA (Medical-concept Extraction with Schema Alignment) framework.

## Repo Structure

```
presto-validate/
├── Home.py                   # Entry point
├── pages/
│   ├── 1_Sessions.py         # Session management
│   ├── 2_Validate.py         # Validation interface
│   └── 3_Analysis.py         # View results and metrics
├── utils/
│   ├── models.py             # Defining data models
│   ├── session_manager.py    # 'CRUD' functions
│   ├── schema_loader.py      # Schema config loading
│   ├── schema_inspector.py   # Schema introspection
│   ├── predictions_loader.py # File handling
│   ├── validation_ui.py      # UI generation
│   ├── metrics.py            # Calculating metrics
│   └── styles.py             # CSS styles
├── sessions/                 # Session data
├── predictions/              # JSON files in subfolders
├── schemas.yaml              # configuration schemas here
├── profiles/                 # reusable field-selection profiles
├── packets/                  # generated clinician packets (gitignored)
```

## Installation

1. **Install dependencies, including schema(s):**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure schemas** in `schemas.yaml`:
   ```yaml
   schemas:
     - module: your_schema_module_name
       root_class: YourRootClassName
   ```

3. **Add prediction files** to subdirectory in `predictions/`. For additional sample predictions run `git submodule update --init`.

## Launch

```bash
streamlit run Home.py
```

Default URL: http://localhost:8501

## Prediction File Format

The preferred format uses document-level fields.
Source content and inference output should be provided in separate aggregate JSON or JSONL files, with records sharing a `document_id`.

```json
[
  {
    "document_id": "doc-1",
    "document_content": "The original document text..."
  }
]
```

```json
{"document_id": "doc-1", "document_inference": {"field1": "value1", "field2": {}}}
```

- **`document_content`**: Original document text (string)
- **`document_inference`**: LLM extraction result (object matching your Pydantic schema; JSON-encoded strings are also accepted)
- **`document_id`**: Used to join split content and inference records

Legacy per-document files with `content` and `output` are still supported and are normalised internally.

## Field-selection profiles

Re-ticking the same fields for every session is avoidable. In the session
wizard (Step 2 — Field Selection):

- **Load a profile**: pick a saved profile and click **Apply profile** to
  tick its fields. You can still adjust the selection before continuing.
- **Save a profile**: after selecting fields, enter a name and click
  **Save profile**. It is written to `profiles/<name>.json` and offered in
  every future session that uses the same schema.

Profiles are plain JSON scoped to a schema module and are safe to commit and
share. A ready-made `profiles/mesa_protocol_v1.json` ships with the fields
from the [validation protocol](GUIDE.md). If a profile references a field that
no longer exists in the schema, that selection is skipped with a warning and
the rest still applies.

## Deploying to clinicians (validation packets)

Clinicians do not need Python, a server, or this app. A **validation packet**
is a single self-contained `.html` file (all data, styling, and logic inline —
no internet or CDN required) that runs from a file share in Edge/Chrome.

**Coordinator — generate packets:**

1. Create and load a session (schema + profile + predictions folder).
2. On the **Sessions** page, expand **Export validation packet**.
3. Enter a packet name (e.g. the clinician's name), choose which documents to
   include (all by default; paste a list to preselect a subset), and click
   **Generate packet**.
4. The file is written to `packets/<name>.html`. Copy it to the network drive.

**Clinician — validate:**

1. Double-click the packet's `.html` on the network drive; it opens in Edge.
2. For each document: the source text is on the left, the extracted entities
   (fully expanded — no clicking to reveal) on the right. Mark each field or
   item **Correct** / **Incorrect**, enter the count of any items the model
   **missed**, and tick **Mark document as fully validated** when done.
3. Click **🔎 locate** on any extracted excerpt to highlight and scroll to it
   in the document.
4. Click **Save results** and choose a location on the network drive (a
   `results/` folder is recommended). Progress also autosaves in the browser,
   so it survives an accidental close; **Load results file** resumes from a
   saved file on another machine.

## Importing results

On the **Analysis** page, select the matching session, then under **Import
packet results** upload one or more `*_results.json` files collected from
clinicians. Each packet's precision/recall/F1/accuracy is shown; uploading
several at once adds a combined table across all clinicians (a document
validated by two clinicians is counted once per clinician, enabling
inter-rater comparison).
