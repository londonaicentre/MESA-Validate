"""
Home.py
"""

import streamlit as st

st.set_page_config(page_title="LLM Outputs Validation Tool", layout="wide")
st.logo("aic_logo.png")

if "active_session" not in st.session_state:
    st.session_state.active_session = None

if "progress" not in st.session_state:
    st.session_state.progress = None

st.title("MESA Validate")

st.markdown("""
This is a basic validation tool for LLM outputs generated via the MESA (Medical-concept Extraction with Schema Alignment) framework for fine-tuned, privacy first LLMs. 

### Workflow

1. **Sessions** - Manage or Create validation sessions
2. **Validate** - Human review of LLM outputs 
3. **Analysis** - View metrics and export results

### Getting Started

**1. Install Schemas**

- Schemas are Python packages installed via `requirements.txt`
- Configure available schemas in `schemas.yaml` with module and root class
- Example:
  ```yaml
  schemas:
    - module: oncollamaschemav3
      root_class: OncoLlamaModel
  ```

**2. Prepare Prediction Files**

- Place JSON prediction files subfolders in the `predictions/` directory (e.g. `predictions/project1/`)
- Preferred format assumes two documents with at least the respective fields: `"document_content"` for source text and `"document_inference"` for the LLM extraction result
- Legacy per-document files with `"content"` and `"output"` are still supported and are converted internally on load
- The contents of `"document_inference"` must be valid according to the selected schema and are validated on load

**3. Create a Session**

Go to the **Sessions** page to create a new validation session. Select your schema, choose which fields to validate, and specify which prediction folder to use.
            
**4. Validation Types**

There are two validation approaches which are selected automatically based on what fields are chosen to validate:

- **Binary validation** is automatically used when a chosen field can only appear a single time in a schema. It is validated on `correct` vs `incorrect`, and TP / TN / FP / FN / Precision / Recall / F1 are calculated depending on whether the field is populated.
- **List validation** is automatically used when a chosen field is part of a list or if an Enum value is chosen (in either case, the field can repeat multiple times). In this case, the validator can mark each occurrence as `correct` vs `incorrect` and indicate how many additional items appear in the document that may not have been extraction. This supports Precision / Recall / F1 score generation. 

""")
