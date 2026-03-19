# MESA Validate (Web Edition)

A self-contained, browser-based human-in-the-loop (HITL) validation tool for LLM-extracted structured data. This is the web version of MESA Validate — no Python, server, or installation required. Just open `index.html` in your browser.

## Quick Start

1. Open `index.html` in Chrome, Firefox, or Edge
2. Go to the **Sessions** tab and create a new session
3. Select a schema, choose which fields to validate, and load your prediction JSON files
4. Validate documents in the **Validate** tab
5. View metrics in the **Analysis** tab

## How It Works

### Tabs

| Tab | Purpose |
|---|---|
| **Home** | Overview and instructions |
| **Sessions** | Create, load, delete, import, and export validation sessions |
| **Validate** | Two-pane interface: document text on the left, validation controls on the right |
| **Analysis** | Aggregate metrics (precision, recall, F1, accuracy) and CSV export |

### Creating a Session

The session wizard has 4 steps:

1. **Schema Selection** — Use the built-in default schema (`oncollamaschemav3`) or load a custom schema JSON file exported with `tools/export_schema.py`
2. **Field Selection** — Choose what to validate:
   - Entire BaseModel classes (validated as a single unit)
   - Individual fields within a class
   - Specific enum values (for list-context enums only)
3. **Prediction Files** — Select JSON files from your computer using the file picker. Optionally set a sample size to randomly subsample.
4. **Review & Create** — Name your session and confirm

### Prediction File Format

Each prediction JSON file must have two fields:

```json
{
  "content": "The original document text...",
  "output": {
    "field1": "value1",
    "nested": { ... }
  }
}
```

- `content` — The source document text displayed in the left pane
- `output` — The LLM extraction result, which should conform to the selected schema

### Validation Types

The tool automatically determines the validation approach based on how a field is used in the schema:

**Binary Validation** — Used when a field appears at most once (non-list context). Mark as:
- **Correct** — The extraction is accurate
- **Incorrect** — The extraction is wrong

The tool tracks whether the field value is present or absent and maps to: `PRESENT_CORRECT`, `ABSENT_CORRECT`, `PRESENT_INCORRECT`, `ABSENT_INCORRECT`. This enables TP/TN/FP/FN and accuracy calculations.

**List Validation** — Used when a field is part of a list or when validating specific enum values. For each extracted item, mark as correct or incorrect. Additionally, enter the count of items that appear in the document but were missed by the LLM.

### Metrics

**Binary metrics:** Precision, Recall, F1, Accuracy (from TP/TN/FP/FN counts)

**List metrics:** Precision = correct / total extracted, Recall = correct / (correct + missed), F1

### Data Storage

All data is stored locally in your browser using IndexedDB. Nothing is sent to any server. Data persists across page reloads but is tied to the browser profile.

Use **Export** and **Import** to back up sessions or share them with colleagues. Exported files are standard JSON containing the full session configuration, progress, and loaded prediction data.

## Adding Custom Schemas

The default `oncollamaschemav3` schema is embedded in the HTML file. To use a different Pydantic schema:

1. Ensure the schema's Python package is installed
2. Add it to `schemas.yaml` in the project root:
   ```yaml
   schemas:
     - module: your_schema_module
       root_class: YourRootModel
   ```
3. Run the export tool from the project root:
   ```
   python tools/export_schema.py
   ```
4. This produces a `.schema.json` file in `mesa-validate-web/schemas/`
5. In the session wizard, choose "Load custom schema JSON" and select the exported file

### What the Export Tool Does

`tools/export_schema.py` reads your Pydantic models and pre-computes all the metadata the web app needs:

- Class hierarchy and field types
- Which classes are used as list items (`List[ClassName]`)
- Paths from the root model to each class
- Enum container mappings
- Which enums appear only in list contexts

This avoids the need for runtime Python introspection in the browser.

## Browser Compatibility

Tested on modern versions of:
- Chrome / Edge (Chromium)
- Firefox
- Safari

Requires IndexedDB support (available in all modern browsers). Works with `file://` protocol — no web server needed.

## Relationship to the Python Version

This web edition is a standalone port of the Streamlit-based MESA Validate tool in the parent directory. Both versions produce compatible validation results. Sessions exported from the web version can be shared as JSON files, though the storage formats differ (IndexedDB vs filesystem).
