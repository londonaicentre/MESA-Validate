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
├── mesa_validate/
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
